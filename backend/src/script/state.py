"""剧本生成 Agent 状态定义"""

from typing import TypedDict, Optional, Annotated
from langgraph.graph.message import add_messages
from langchain_core.messages import BaseMessage


class ScriptAgentState(TypedDict):
    """剧本生成 Agent 状态"""

    # ============ 用户输入 ============
    user_input: str  # 故事概念，e.g. "张三丰和张无忌在武当山大战"
    user_instructions: str  # 用户指令，包含视频配置
    target_duration_sec: Optional[int]  # 目标时长（秒）
    target_chapters: int  # 目标章节/场景数，默认 1

    # ============ 视频配置 ============
    script_config: Optional[dict]  # 视频配置（ratio, style, mood, density 等）
    thread_summary: Optional[str]  # 同 thread_id 的压缩上下文摘要
    previous_thread_memory: Optional[dict]  # 上一轮结构化 Thread Memory

    # ============ 参考数据 ============
    reference_novel_title: Optional[str]  # 参考小说的名称
    reference_novel_data: Optional[dict]  # 参考小说的完整内容
    retrieval_results: Optional[list[dict]]  # hybrid-search 检索结果

    # ============ Move 和 IR ============
    move_codebook: Optional[dict]  # 从参考小说提取的 Move 结构
    story_ir: Optional[dict]  # 故事规划 IR
    script_plan: Optional[dict]  # 轻量短剧执行计划（Planner 输出）

    # ============ 生成内容 ============
    plan_text: Optional[str]  # 故事规划文本
    draft_script: Optional[str]  # 生成的剧本草稿
    final_script: Optional[str]  # 最终剧本
    verification_result: Optional[dict]  # 规则审核结果
    quality_review_result: Optional[dict]  # ReviewSubagent 语义审核结果
    revision_feedback: Optional[str]  # 反馈给 Executor 的重写建议

    # ============ 元数据 ============
    iteration_count: int  # 迭代次数
    revision_count: int  # 规则审核触发的重写次数
    messages: Annotated[list[BaseMessage], add_messages]  # 对话历史
    error: Optional[str]  # 错误信息
