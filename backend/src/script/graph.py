"""剧本生成 Agent 工作流定义"""

import logging
from typing import AsyncGenerator, Optional

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph

from src.script.state import ScriptAgentState
from src.script.nodes import (
    load_reference_node,
    plan_story_node,
    write_scenes_node,
    verify_script_node,
    review_script_node,
    finalize_node,
)
from src.agent.script_data import build_script_data
from src.core.config import settings
from src.core.logger import get_logger

logger = get_logger(__name__)


def create_script_graph(with_memory: bool = True):
    """
    创建剧本生成工作流

    工作流程：
    1. load_reference: 加载参考小说 + 提取 Move（可选）
    2. plan_story: 规划故事结构（可选）
    3. write_scenes: 按计划生成剧本内容 + AIGC 分镜规格
    4. verify_script: 确定性规则审核
    5. review_script: ReviewSubagent 语义审核 + Command 动态路由
    6. [条件] 不通过且未达上限则重写，否则 finalize

    Args:
        with_memory: 是否启用记忆功能（会话持久化）

    Returns:
        编译后的 Agent 工作流
    """

    logger.info("创建剧本生成工作流")

    # 创建状态图
    workflow = StateGraph(ScriptAgentState)

    # 添加节点
    workflow.add_node("load_reference", load_reference_node)
    workflow.add_node("plan_story", plan_story_node)
    workflow.add_node("write_scenes", write_scenes_node)
    workflow.add_node("verify_script", verify_script_node)
    workflow.add_node("review_script", review_script_node)
    workflow.add_node("finalize", finalize_node)

    # 设置入口点
    workflow.set_entry_point("load_reference")

    # 添加边
    workflow.add_edge("load_reference", "plan_story")
    workflow.add_edge("plan_story", "write_scenes")
    workflow.add_edge("write_scenes", "verify_script")
    workflow.add_edge("verify_script", "review_script")
    workflow.add_edge("finalize", END)

    # 编译工作流
    if with_memory:
        memory = MemorySaver()
        graph = workflow.compile(checkpointer=memory)
        logger.info("✅ 剧本工作流创建完成 (with memory)")
    else:
        graph = workflow.compile()
        logger.info("✅ 剧本工作流创建完成 (without memory)")

    return graph


async def run_script_agent_stream(
    user_input: str,
    user_instructions: str | None = None,
    thread_id: str = "default",
    target_duration_sec: int | None = None,
    target_chapters: int = 1,
    script_config: dict | None = None,
    reference_novel_title: str | None = None,
) -> AsyncGenerator[dict, None]:
    """
    异步流式运行剧本生成 Agent

    Args:
        user_input: 用户输入（故事概念）
        user_instructions: 用户指令（视频配置等）
        thread_id: 会话 ID
        target_duration_sec: 目标时长
        target_chapters: 目标章节数
        script_config: 视频配置
        reference_novel_title: 参考小说名称

    Yields:
        SSE 事件
    """
    logger.info(f"运行剧本生成 Agent, thread_id={thread_id}")

    # 创建 Agent
    graph = create_script_graph(with_memory=True)

    # 初始状态
    initial_state: ScriptAgentState = {
        "user_input": user_input,
        "user_instructions": user_instructions or "",
        "target_duration_sec": target_duration_sec,
        "target_chapters": target_chapters,
        "script_config": script_config,
        "reference_novel_title": reference_novel_title,
        "move_codebook": None,
        "reference_novel_data": None,
        "story_ir": None,
        "script_plan": None,
        "plan_text": None,
        "draft_script": None,
        "final_script": None,
        "verification_result": None,
        "quality_review_result": None,
        "revision_feedback": None,
        "iteration_count": 0,
        "revision_count": 0,
        "messages": [],
        "error": None,
    }

    # 配置
    config = {
        "configurable": {"thread_id": thread_id},
        "recursion_limit": 50,
    }

    final_script = None
    try:
        # 使用 astream_events 获取流式事件
        async for event in graph.astream_events(initial_state, config, version="v2"):
            event_kind = event.get("event")

            # 节点开始
            if event_kind == "on_chain_start":
                node_name = event.get("name", "")
                if node_name in [
                    "load_reference",
                    "plan_story",
                    "write_scenes",
                    "verify_script",
                    "review_script",
                    "finalize",
                ]:
                    yield {
                        "type": "node_start",
                        "node": node_name,
                    }

            # 节点结束
            elif event_kind == "on_chain_end":
                node_name = event.get("name", "")
                if node_name in [
                    "load_reference",
                    "plan_story",
                    "write_scenes",
                    "verify_script",
                    "review_script",
                    "finalize",
                ]:
                    output = event.get("data", {}).get("output", {})
                    if isinstance(output, dict):
                        if output.get("final_script"):
                            final_script = output["final_script"]
                    yield {
                        "type": "node_end",
                        "node": node_name,
                        "output": output,
                    }

            # 方案A：不发送 token，等待全量生成完成后一次性返回 done
            elif event_kind == "on_chat_model_stream":
                continue

        # 截断发送给前端的内容：只保留到 ## 视觉风格 部分，去掉 ## AIGC执行规格
        display_script = final_script
        if final_script:
            aigc_marker = "## AIGC执行规格"
            marker_pos = final_script.find(aigc_marker)
            if marker_pos != -1:
                display_script = final_script[:marker_pos].rstrip()

        # 从 AIGC JSON 解析结构化数据（纯解析，毫秒级）
        script_data = None
        if final_script and final_script.strip():
            style_name = None
            if isinstance(script_config, dict):
                style_raw = script_config.get("style")
                if isinstance(style_raw, str):
                    style_name = style_raw

            script_data = build_script_data(
                final_copy=final_script,
                user_input=user_input,
                title=None,
                duration_sec=target_duration_sec,
                style_name=style_name,
            )

        logger.info("剧本生成完成, final_script=%s", bool(final_script))
        yield {"type": "done", "content": display_script, "script_data": script_data}

    except Exception as e:
        logger.exception(f"剧本生成流式执行失败: {e}")
        yield {
            "type": "error",
            "error": str(e),
        }
