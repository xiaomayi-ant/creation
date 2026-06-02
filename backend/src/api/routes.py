"""API 路由定义"""

import json
import os
import uuid
from typing import AsyncGenerator

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import StreamingResponse

from src.script.graph import run_script_agent_stream
from src.api.schemas import (
    ChatRequest,
    ConfigSubmitRequest,
    CopywritingRequest,
    CopywritingResponse,
    HealthResponse,
    NovelGenerationRequest,
    NovelGenerationResponse,
    NovelStreamEvent,
)
from src.novel.graph import run_novel_agent, run_novel_agent_stream
from src.core.logger import get_logger
from src.core.config import settings
from src.core.artifacts import persist_run_artifacts
from src.script.memory import get_script_thread_memory, upsert_script_thread_memory

logger = get_logger(__name__)

router = APIRouter()


@router.get("/health", response_model=HealthResponse, tags=["系统"])
async def health_check():
    """健康检查接口"""
    return HealthResponse()


@router.post(
    "/generate",
    response_model=CopywritingResponse,
    tags=["文案生成"],
    summary="生成口播文案",
    description="根据用户输入的参考文案和指令，生成优质的口播文案",
)
async def generate_copywriting(request: CopywritingRequest):
    """
    生成口播文案（已废弃）
    
    此接口已废弃，请使用 /api/v1/chat/submit 接口进行剧本生成
    """
    raise HTTPException(
        status_code=status.HTTP_410_GONE,
        detail="此接口已废弃，请使用 /api/v1/chat/submit 接口进行剧本生成"
    )


@router.post(
    "/generate/stream",
    tags=["文案生成"],
    summary="流式生成口播文案",
    description="流式返回文案生成过程，支持实时显示",
)
async def generate_copywriting_stream(request: CopywritingRequest):
    """
    流式生成口播文案（已废弃）
    
    此接口已废弃，请使用 /api/v1/chat/submit 接口进行剧本生成
    """
    raise HTTPException(
        status_code=status.HTTP_410_GONE,
        detail="此接口已废弃，请使用 /api/v1/chat/submit 接口进行剧本生成"
    )


@router.post(
    "/analyze",
    response_model=CopywritingResponse,
    tags=["文案分析"],
    summary="分析文案结构",
    description="仅执行解析节点，对文案进行结构化拆解分析",
)
async def analyze_copywriting(request: CopywritingRequest):
    """
    分析文案结构（已废弃）
    
    此接口已废弃
    """
    raise HTTPException(
        status_code=status.HTTP_410_GONE,
        detail="此接口已废弃"
    )


# ============================================================================
# 对话式配置 API 路由
# ============================================================================


STYLE_LABELS = {
    "realistic": "写实风",
    "anime": "动漫风",
    "3d": "3D动画",
    "pixel": "像素风",
}

DENSITY_LABELS = {
    "cinematic": "cinematic",
    "balanced": "balanced",
    "strict": "strict",
}

RATIO_LABELS = {
    "16:9": "16:9横屏",
    "9:16": "9:16竖屏",
    "4:3": "4:3",
    "3:4": "3:4",
}


@router.post(
    "/chat",
    tags=["对话配置"],
    summary="发送对话消息",
    description="接收用户输入，返回配置表单（纯配置下发，不调用 LLM）",
)
async def chat(request: ChatRequest):
    """
    接收用户创作需求，返回配置表单供用户确认。
    纯配置下发，瞬时返回。
    """
    logger.info("收到对话请求, input_length=%d", len(request.user_input))

    thread_id = request.thread_id or str(uuid.uuid4())

    return {
        "type": "config_form",
        "data": {
            "thread_id": thread_id,
            "title": "创作配置确认",
            "fields": [
                {
                    "id": "target_duration",
                    "label": "1. 视频时长要求",
                    "options": [
                        {"label": "15秒内", "value": "15"},
                        {"label": "30秒内", "value": "30"},
                        {"label": "45秒内", "value": "45"},
                        {"label": "1分钟以上", "value": "60"},
                        {"label": "系统推荐时长", "value": "auto"},
                    ],
                    "default": "auto",
                },
                {
                    "id": "ratio",
                    "label": "2. 视频比例",
                    "options": [
                        {"label": "16:9横屏", "value": "16:9"},
                        {"label": "9:16竖屏", "value": "9:16"},
                        {"label": "4:3", "value": "4:3"},
                        {"label": "3:4", "value": "3:4"},
                    ],
                    "default": "16:9",
                },
                {
                    "id": "style",
                    "label": "3. 视频风格",
                    "options": [
                        {"label": "写实风", "value": "realistic"},
                        {"label": "动漫风", "value": "anime"},
                        {"label": "3D动画", "value": "3d"},
                        {"label": "像素风", "value": "pixel"},
                    ],
                    "default": "anime",
                },
                {
                    "id": "narrator",
                    "label": "4. 是否需要旁白",
                    "options": [
                        {"label": "需要旁白", "value": "yes"},
                        {"label": "不需要旁白", "value": "no"},
                    ],
                    "default": "yes",
                },
                {
                    "id": "mood",
                    "label": "5. 视频情绪基调",
                    "options": [
                        {"label": "史诗震撼", "value": "epic"},
                        {"label": "紧张刺激", "value": "intense"},
                        {"label": "怀旧感慨", "value": "nostalgic"},
                        {"label": "温馨感人", "value": "heartwarming"},
                    ],
                    "default": "heartwarming",
                },
                {
                    "id": "density",
                    "label": "6. AIGC指令密度",
                    "options": [
                        {"label": "电影化（意境优先）", "value": "cinematic"},
                        {"label": "均衡（推荐）", "value": "balanced"},
                        {"label": "严格工程化（执行优先）", "value": "strict"},
                    ],
                    "default": "balanced",
                },
            ],
        },
    }


@router.get(
    "/chat/memory/{thread_id}",
    tags=["对话配置"],
    summary="读取短剧线程记忆",
    description="按 thread_id 返回后端保存的结构化 Thread Memory",
)
async def chat_memory(thread_id: str):
    memory = get_script_thread_memory(thread_id)
    if memory is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="未找到该 thread_id 的记忆记录",
        )
    return memory


@router.post(
    "/chat/submit",
    tags=["对话配置"],
    summary="提交配置并生成",
    description="接收用户配置选项，映射为 CopywritingRequest 参数并返回 SSE 流",
)
async def chat_submit(request: ConfigSubmitRequest):
    """
    接收配置表单提交，映射为 CopywritingRequest 参数，
    复用 run_agent_stream 返回 SSE 流。
    """
    logger.info(
        "收到配置提交, thread_id=%s, selections=%s",
        request.thread_id,
        request.selections,
    )

    # 映射 target_duration
    duration_val = request.selections.get("target_duration", "auto")
    target_duration_sec = None
    if duration_val != "auto":
        try:
            target_duration_sec = int(duration_val)
        except ValueError:
            pass

    # 映射 ratio + style → user_instructions
    ratio = request.selections.get("ratio", "16:9")
    style = request.selections.get("style", "anime")
    narrator = request.selections.get("narrator", "yes")
    mood = request.selections.get("mood", "heartwarming")
    density = request.selections.get("density", "balanced")
    
    ratio_label = RATIO_LABELS.get(ratio, ratio)
    style_label = STYLE_LABELS.get(style, style)
    density_label = DENSITY_LABELS.get(density, "balanced")
    
    # 构建剧本配置
    script_config = {
        "ratio": ratio_label,
        "style": style_label,
        "narrator": "需要旁白" if narrator == "yes" else "不需要旁白",
        "mood": mood,
        "duration": f"{target_duration_sec}秒" if target_duration_sec else "系统推荐",
        "density": density_label,
    }
    
    user_instructions = f"视频比例：{ratio_label}，视频风格：{style_label}"

    if target_duration_sec:
        user_instructions += f"，目标时长约{target_duration_sec}秒"

    async def event_generator() -> AsyncGenerator[str, None]:
        """生成 SSE 事件流"""
        artifact_payload: dict[str, object] = {
            "thread_id": request.thread_id,
            "user_input": request.user_input,
            "selections": request.selections,
            "script_config": script_config,
            "target_duration_sec": target_duration_sec,
            "retrieval_references": [],
            "move_codebook": None,
            "move_guidance_ir": None,
            "script_plan": None,
            "verification_result": None,
            "quality_review_result": None,
            "revision_count": 0,
            "llm_prompt_used": None,
            "final_result": None,
        }
        try:
            async for event in run_script_agent_stream(
                user_input=request.user_input,
                user_instructions=user_instructions,
                thread_id=request.thread_id,
                target_duration_sec=target_duration_sec,
                target_chapters=request.target_chapters,
                script_config=script_config,
                reference_novel_title=request.reference_novel_title,
            ):
                # 记录检索与 move 提取结果，便于复盘“给 LLM 的参考内容”
                if event.get("type") == "node_end" and event.get("node") == "load_reference":
                    output = event.get("output")
                    if isinstance(output, dict):
                        results = output.get("retrieval_results")
                        if isinstance(results, list):
                            refs: list[dict[str, object]] = []
                            for i, r in enumerate(results, start=1):
                                if not isinstance(r, dict):
                                    continue
                                tree_node = r.get("tree_node")
                                if not isinstance(tree_node, dict):
                                    tree_node = {}
                                full_text = str(r.get("content") or "")
                                refs.append(
                                    {
                                        "rank": i,
                                        "novel_name": r.get("novel_name"),
                                        "novel_id": r.get("novel_id"),
                                        "node_id": r.get("node_id"),
                                        "score": r.get("score"),
                                        "rerank_score": r.get("rerank_score"),
                                        "chapter_title": tree_node.get("title"),
                                        "chapter_summary": tree_node.get("summary"),
                                        # 传给写作 LLM 的是 content[:800]
                                        "llm_reference_excerpt": full_text[:800],
                                        # 原始章节文本（用于人工评估检索有效性）
                                        "chapter_content": full_text,
                                    }
                                )
                            artifact_payload["retrieval_references"] = refs

                        move_codebook = output.get("move_codebook")
                        if isinstance(move_codebook, dict):
                            artifact_payload["move_codebook"] = {
                                "story_framework": move_codebook.get("story_framework"),
                                "pacing": move_codebook.get("pacing"),
                                "moves": move_codebook.get("moves"),
                            }

                if event.get("type") == "node_end" and event.get("node") == "plan_story":
                    output = event.get("output")
                    if isinstance(output, dict):
                        script_plan = output.get("script_plan")
                        if isinstance(script_plan, dict):
                            artifact_payload["script_plan"] = script_plan

                if event.get("type") == "node_end" and event.get("node") == "write_scenes":
                    output = event.get("output")
                    if isinstance(output, dict):
                        if isinstance(output.get("prompt_used"), str):
                            artifact_payload["llm_prompt_used"] = output.get("prompt_used")
                        if isinstance(output.get("move_guidance_ir"), dict):
                            artifact_payload["move_guidance_ir"] = output.get("move_guidance_ir")
                        # 不把完整 prompt/IR 发给前端
                        event = {
                            **event,
                            "output": {
                                k: v for k, v in output.items()
                                if k not in {"prompt_used", "move_guidance_ir"}
                            },
                        }

                if event.get("type") == "node_end" and event.get("node") == "verify_script":
                    output = event.get("output")
                    if isinstance(output, dict):
                        verification_result = output.get("verification_result")
                        if isinstance(verification_result, dict):
                            artifact_payload["verification_result"] = verification_result
                        revision_count = output.get("revision_count")
                        if isinstance(revision_count, int):
                            artifact_payload["revision_count"] = revision_count

                if event.get("type") == "node_end" and event.get("node") == "review_script":
                    output = event.get("output")
                    if isinstance(output, dict):
                        quality_review_result = output.get("quality_review_result")
                        if isinstance(quality_review_result, dict):
                            artifact_payload["quality_review_result"] = quality_review_result
                        revision_count = output.get("revision_count")
                        if isinstance(revision_count, int):
                            artifact_payload["revision_count"] = revision_count

                if event.get("type") == "done":
                    artifact_payload["final_result"] = {
                        "content": event.get("content"),
                        "script_data": event.get("script_data"),
                    }
                    # 追踪 source_refs 是否真正落到了结构化结果
                    try:
                        script_data = event.get("script_data")
                        retrieval_refs = artifact_payload.get("retrieval_references") or []
                        retrieval_set = set()
                        if isinstance(retrieval_refs, list):
                            for r in retrieval_refs:
                                if isinstance(r, dict):
                                    rid = f"{r.get('novel_id', 'unknown')}#{r.get('node_id', 'unknown')}"
                                    retrieval_set.add(rid)

                        used_refs = set()
                        if isinstance(script_data, dict):
                            aigc_spec = script_data.get("aigcSpec")
                            if isinstance(aigc_spec, dict):
                                shots = aigc_spec.get("shots")
                                if isinstance(shots, list):
                                    for s in shots:
                                        if not isinstance(s, dict):
                                            continue
                                        refs = s.get("source_refs")
                                        if isinstance(refs, list):
                                            for ref in refs:
                                                ref_str = str(ref).strip()
                                                if ref_str:
                                                    used_refs.add(ref_str)

                        artifact_payload["source_ref_trace"] = {
                            "retrieval_ref_count": len(retrieval_set),
                            "used_ref_count": len(used_refs),
                            "retrieval_refs": sorted(retrieval_set),
                            "used_refs": sorted(used_refs),
                            "unused_refs": sorted(retrieval_set - used_refs),
                        }
                        if isinstance(script_data, dict):
                            aigc_spec = script_data.get("aigcSpec")
                            if isinstance(aigc_spec, dict):
                                model_trace = aigc_spec.get("reference_trace")
                                if isinstance(model_trace, dict):
                                    artifact_payload["model_reference_trace"] = model_trace
                    except Exception as trace_err:
                        logger.warning("source_ref_trace 统计失败: %s", trace_err)

                event_data = json.dumps(event, ensure_ascii=False)
                yield f"data: {event_data}\n\n"

            # 请求结束后落盘一次产物
            try:
                backend_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
                try:
                    memory = upsert_script_thread_memory(
                        request.thread_id,
                        artifact_payload,  # type: ignore[arg-type]
                    )
                    artifact_payload["thread_memory_summary"] = memory.get("thread_summary")
                    logger.info("已更新 Thread Memory: thread_id=%s", request.thread_id)
                except Exception as memory_err:
                    logger.warning("写入 Thread Memory 失败: %s", memory_err)

                paths = persist_run_artifacts(
                    project_root=backend_root,
                    thread_id=request.thread_id,
                    payload=artifact_payload,  # type: ignore[arg-type]
                )
                logger.info("已写入运行产物: %s", paths.run_json)
            except Exception as artifact_err:
                logger.warning("写入运行产物失败: %s", artifact_err)
        except Exception as e:
            logger.exception("配置提交流式生成异常: %s", e)
            error_event = json.dumps(
                {"type": "error", "error": str(e)}, ensure_ascii=False
            )
            yield f"data: {error_event}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ============================================================================
# 小说生成 API 路由
# ============================================================================


@router.post(
    "/novel/generate",
    response_model=NovelGenerationResponse,
    tags=["小说生成"],
    summary="生成小说/短故事",
    description="根据用户的故事概念和参考小说，生成完整的多章节故事",
)
async def generate_novel(request: NovelGenerationRequest):
    """
    生成小说/短故事（同步接口）

    工作流程：
    1. 加载参考小说 + 提取 Move Codebook
    2. 规划故事框架（章节数、标题、核心思想）
    3. 逐章生成内容
    4. 验证每章的流畅性
    5. 根据需要重新生成或继续下一章
    6. 合并所有章节为最终故事
    """
    logger.info(
        f"收到小说生成请求: "
        f"concept={request.user_input[:50]}..., "
        f"reference={request.reference_novel_title}, "
        f"chapters={request.target_chapters}"
    )

    # 生成线程 ID
    thread_id = request.thread_id or f"novel_{uuid.uuid4().hex[:8]}"

    try:
        result = await run_novel_agent(
            user_input=request.user_input,
            reference_novel_title=request.reference_novel_title,
            user_style=request.user_style,
            target_chapters=request.target_chapters,
            thread_id=thread_id,
        )

        if result["success"]:
            logger.info(
                f"小说生成成功: "
                f"title={result['story_title']}, "
                f"chapters={result['chapters_count']}, "
                f"iterations={result['iterations']}, "
                f"thread_id={thread_id}"
            )
        else:
            logger.warning(f"小说生成失败: {result.get('error')}")

        return NovelGenerationResponse(**result)

    except Exception as e:
        logger.exception(f"小说生成 API 处理异常: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        )


@router.post(
    "/novel/generate/stream",
    tags=["小说生成"],
    summary="流式生成小说/短故事",
    description="流式返回小说生成过程，支持实时显示进度",
)
async def generate_novel_stream(request: NovelGenerationRequest):
    """
    流式生成小说/短故事

    返回 Server-Sent Events (SSE) 格式的流式响应：
    - type: node_start - 节点开始执行
    - type: node_end - 节点执行完成
    - type: progress - 章节生成进度
    - type: token - LLM 输出的 token（如有）
    - type: done - 生成完成
    - type: error - 发生错误
    """
    logger.info(
        f"收到流式小说生成请求: "
        f"concept={request.user_input[:50]}..., "
        f"reference={request.reference_novel_title}, "
        f"chapters={request.target_chapters}"
    )

    # 生成线程 ID
    thread_id = request.thread_id or f"novel_{uuid.uuid4().hex[:8]}"

    async def novel_event_generator() -> AsyncGenerator[str, None]:
        """生成小说生成的 SSE 事件流"""
        try:
            async for event in run_novel_agent_stream(
                user_input=request.user_input,
                reference_novel_title=request.reference_novel_title,
                user_style=request.user_style,
                target_chapters=request.target_chapters,
                thread_id=thread_id,
            ):
                # 格式化为 SSE
                event_data = json.dumps(event, ensure_ascii=False)
                yield f"data: {event_data}\n\n"
                logger.debug(f"发送事件: {event.get('type')}")

        except Exception as e:
            logger.exception(f"流式小说生成异常: {e}")
            error_event = json.dumps(
                {"type": "error", "error": str(e)}, ensure_ascii=False
            )
            yield f"data: {error_event}\n\n"

    return StreamingResponse(
        novel_event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # 禁用 nginx 缓冲
        },
    )
