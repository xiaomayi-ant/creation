"""剧本生成 Agent 节点定义"""

import json
import logging
import re
from typing import Any, Literal, Optional

from langchain_community.chat_models import ChatTongyi
from langchain_core.messages import SystemMessage
from langchain_core.runnables import RunnableConfig
from langchain_core.language_models.chat_models import BaseChatModel
from langgraph.types import Command

from src.agent.prompts import SCRIPT_GENERATION_PROMPT
from src.novel.move_extractor import extract_moves_from_novel
from src.script.review_agent import run_review_subagent
from src.script.state import ScriptAgentState
from src.core.config import settings
from src.core.logger import get_logger

logger = get_logger(__name__)


def _to_text(content: Any) -> str:
    """Normalize LLM message content to text."""
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, (bytes, bytearray)):
        try:
            return content.decode("utf-8", errors="ignore")
        except Exception:
            return str(content)
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                parts.append(str(item.get("text") or item.get("content") or item.get("value") or ""))
            else:
                parts.append(str(item))
        return "\n".join(p for p in parts if p).strip()
    return str(content)


def _dbg(label: str, payload: Any, *, limit: int = 2000) -> None:
    """Debug logging controlled by env flags."""
    if not settings.debug_node_io:
        return
    try:
        text = payload if isinstance(payload, str) else json.dumps(payload, ensure_ascii=False)
    except Exception:
        text = str(payload)
    if limit and len(text) > limit:
        text = text[:limit] + "\n...(truncated)"
    logger.info(f"[DEBUG:{label}]\n{text}")


def _build_move_guidance_ir(
    *,
    user_input: str,
    move_codebook: Optional[dict[str, Any]],
    retrieval_results: Optional[list[dict[str, Any]]],
) -> tuple[dict[str, Any], str]:
    """构建供写作 LLM 参考的轻量 IR。"""
    ref_ids: list[str] = []
    if isinstance(retrieval_results, list):
        for r in retrieval_results:
            if not isinstance(r, dict):
                continue
            ref_ids.append(f"{r.get('novel_id', 'unknown')}#{r.get('node_id', 'unknown')}")

    moves_raw = move_codebook.get("moves", []) if isinstance(move_codebook, dict) else []
    move_guidance: list[dict[str, Any]] = []
    for idx, mv in enumerate(moves_raw):
        if not isinstance(mv, dict):
            continue
        refs: list[str] = []
        chapters = mv.get("chapters")
        if isinstance(chapters, list):
            for ch in chapters:
                try:
                    ch_idx = int(ch)
                except Exception:
                    continue
                # 如果 chapters 为检索结果序号，则映射到对应 ref_id
                if 1 <= ch_idx <= len(ref_ids):
                    rid = ref_ids[ch_idx - 1]
                    if rid not in refs:
                        refs.append(rid)
        if not refs and ref_ids:
            refs = ref_ids[: min(2, len(ref_ids))]

        move_guidance.append(
            {
                "move_id": mv.get("move_id"),
                "name": mv.get("name"),
                "description": mv.get("description"),
                "core_idea": mv.get("core_idea"),
                "emotional_beats": mv.get("emotional_beats") or [],
                "references": refs,
                "priority": "high" if idx < 3 else "medium",
            }
        )

    ir = {
        "narrative_intent": user_input,
        "move_guidance": move_guidance,
    }
    return ir, json.dumps(ir, ensure_ascii=False, indent=2)


def _json_text(payload: Any) -> str:
    """Render compact, readable JSON for prompt sections."""
    try:
        return json.dumps(payload, ensure_ascii=False, indent=2)
    except Exception:
        return str(payload)


def _parse_duration_seconds(raw: Any) -> float:
    """Parse values such as '3.0s', '30秒', or 4 into seconds."""
    if isinstance(raw, (int, float)):
        return float(raw)
    text = str(raw or "").strip().lower()
    if not text or text == "系统推荐":
        return 0.0
    match = re.search(r"(\d+(?:\.\d+)?)", text)
    if not match:
        return 0.0
    return float(match.group(1))


def _extract_aigc_spec(final_script: str) -> dict[str, Any] | None:
    """Extract the AIGC JSON object from the generated markdown text."""
    if not final_script:
        return None
    marker = re.search(
        r"(?:^|\n)\s*(?:#{1,3}\s*)?AIGC执行规格(?:\s*\(JSON\)|\s*（JSON）)?\s*\n",
        final_script,
    )
    if not marker:
        return None

    section = final_script[marker.end():].strip()
    fenced = re.search(r"```(?:json)?\s*([\s\S]*?)```", section)
    if fenced:
        section = fenced.group(1).strip()

    decoder = json.JSONDecoder()
    start = section.find("{")
    if start < 0:
        return None
    try:
        value, _ = decoder.raw_decode(section[start:])
    except json.JSONDecodeError:
        return None
    return value if isinstance(value, dict) else None


def _retrieval_ref_ids(retrieval_results: Any) -> list[str]:
    refs: list[str] = []
    if not isinstance(retrieval_results, list):
        return refs
    for item in retrieval_results:
        if not isinstance(item, dict):
            continue
        ref_id = f"{item.get('novel_id', 'unknown')}#{item.get('node_id', 'unknown')}"
        if ref_id not in refs:
            refs.append(ref_id)
    return refs


def get_llm(temperature: Optional[float] = None) -> BaseChatModel:
    """获取 LLM 实例"""
    temp = temperature if temperature is not None else settings.model_temperature
    model = settings.model_name

    if settings.llm_provider.lower() == "openai":
        from langchain_openai import ChatOpenAI
        
        kwargs: dict[str, Any] = {
            "model": model,
            "temperature": temp,
        }
        if settings.openai_base_url:
            kwargs["base_url"] = settings.openai_base_url
        
        logger.info(f"使用 OpenAI LLM: model={model}")
        return ChatOpenAI(**kwargs)
    else:
        logger.info(f"使用 DashScope LLM: model={model}")
        kwargs: dict[str, Any] = {
            "model": model,
            "temperature": temp,
        }
        if settings.dashscope_base_url:
            kwargs["base_url"] = settings.dashscope_base_url
        return ChatTongyi(**kwargs)


def load_reference_node(state: ScriptAgentState) -> dict[str, Any]:
    """
    加载参考素材（通过 hybrid-search 语义检索）

    用用户输入作为 query 检索相关章节，提取 Move 结构，
    同时保留检索原文供 write_scenes_node 使用。
    检索服务不可用时降级为空结果，不阻断工作流。
    """
    logger.info("[Script] Load Reference Node")

    if not settings.enable_retrieval:
        logger.info("检索已禁用 (enable_retrieval=false)，直接使用 LLM 生成")
        return {
            "move_codebook": None,
            "retrieval_results": None,
            "reference_novel_data": None,
        }

    query = state.get("user_input", "")
    if not query:
        logger.info("无用户输入，跳过检索")
        return {
            "move_codebook": None,
            "retrieval_results": None,
            "reference_novel_data": None,
        }

    try:
        from src.retrieval.searcher import HybridSearcher

        searcher = HybridSearcher(settings)
        results = searcher.search(
            query,
            top_k=settings.retrieval_top_k,
            use_native=True,
            use_rerank=settings.retrieval_use_rerank,
            rerank_score_gap=settings.retrieval_rerank_gap,
        )

        # NOTE: RRF score 仅反映排名（1/(k+rank)），不适合做质量过滤。
        # 质量控制依赖 top_k 参数和后续 rerank（启用时）。

        if not results:
            logger.warning("检索未返回结果，直接使用 LLM 生成")
            return {
                "move_codebook": None,
                "retrieval_results": None,
                "reference_novel_data": None,
            }

        logger.info("检索到 %d 个相关章节", len(results))
        for idx, r in enumerate(results, start=1):
            novel_name = r.get("novel_name", "未知")
            novel_id = r.get("novel_id", "未知")
            node_id = r.get("node_id", "未知")
            chapter_title = r.get("tree_node", {}).get("title", "未知章节")
            logger.info(
                "检索命中[%d] novel=%s novel_id=%s node_id=%s title=%s",
                idx, novel_name, novel_id, node_id, chapter_title,
            )

        # 将检索结果转换为 novel_data 格式给 Move 提取器
        novel_data = {
            "title": "检索参考素材",
            "author": "多源",
            "chapters": [
                {
                    "chapter_num": i + 1,
                    "chapter_name": r.get("tree_node", {}).get("title", ""),
                    "content": r.get("content", ""),
                }
                for i, r in enumerate(results)
            ],
        }

        import asyncio

        move_codebook, codebook_id = asyncio.run(
            extract_moves_from_novel(novel_data)
        )

        if move_codebook:
            logger.info(
                "成功提取 Move 结构: %d 个 moves",
                len(move_codebook.get("moves", [])),
            )
        else:
            logger.warning("Move 提取失败，使用空的 move_codebook")

        return {
            "move_codebook": move_codebook,
            "retrieval_results": results,
            "reference_novel_data": novel_data,
        }

    except Exception as e:
        logger.warning("检索服务异常: %s，降级为空结果", e)
        return {
            "move_codebook": None,
            "retrieval_results": None,
            "reference_novel_data": None,
        }


def plan_story_node(state: ScriptAgentState, config: RunnableConfig) -> dict[str, Any]:
    """
    规划短剧执行计划。

    Planner 保持轻量、确定性：基于用户配置、检索引用和 Move 结果生成一个
    可审计的 script_plan，供 write_scenes_node 按计划执行。
    """
    logger.info("📝 [Script] Plan Story Node")

    user_input = state.get("user_input", "")
    script_config = state.get("script_config") or {}
    target_chapters = state.get("target_chapters", 1)
    move_codebook = state.get("move_codebook")
    retrieval_results = state.get("retrieval_results")

    ref_ids = _retrieval_ref_ids(retrieval_results)
    references: list[dict[str, Any]] = []
    if isinstance(retrieval_results, list):
        for item in retrieval_results:
            if not isinstance(item, dict):
                continue
            tree_node = item.get("tree_node")
            if not isinstance(tree_node, dict):
                tree_node = {}
            ref_id = f"{item.get('novel_id', 'unknown')}#{item.get('node_id', 'unknown')}"
            references.append(
                {
                    "ref_id": ref_id,
                    "title": tree_node.get("title") or "",
                    "summary": tree_node.get("summary") or "",
                    "use_hint": "参考其叙事节奏、冲突推进或镜头情绪，不直接复刻原文。",
                }
            )

    moves = move_codebook.get("moves", []) if isinstance(move_codebook, dict) else []
    move_hints = []
    for move in moves[:6]:
        if not isinstance(move, dict):
            continue
        move_hints.append(
            {
                "move_id": move.get("move_id"),
                "name": move.get("name"),
                "purpose": move.get("description") or move.get("core_idea") or "",
                "emotional_beats": move.get("emotional_beats") or [],
            }
        )

    duration_raw = script_config.get("duration") or state.get("target_duration_sec") or "系统推荐"
    duration_sec = _parse_duration_seconds(duration_raw)
    if duration_sec <= 0:
        duration_sec = 30.0

    shot_count = max(4, min(10, round(duration_sec / 4)))
    scene_plan: list[dict[str, Any]] = []
    purposes = [
        "开场钩子，快速建立主角、场景和核心悬念",
        "交代背景与人物关系，明确情绪基调",
        "引入冲突或反转，让观众形成期待",
        "升级行动与视觉张力，强化关键选择",
        "推向高潮，集中呈现最强动作或情绪",
        "收束结果，留下记忆点或余韵",
    ]
    for idx in range(shot_count):
        source_refs = [ref_ids[idx % len(ref_ids)]] if ref_ids else []
        move_hint = move_hints[idx % len(move_hints)] if move_hints else {}
        scene_plan.append(
            {
                "id": idx + 1,
                "purpose": purposes[min(idx, len(purposes) - 1)],
                "visual_goal": move_hint.get("purpose") or "画面主体、动作、运镜必须明确",
                "target_seconds": round(duration_sec / shot_count, 1),
                "source_refs": source_refs,
                "move_hint": move_hint.get("name") or "",
            }
        )

    script_plan = {
        "goal": user_input,
        "constraints": {
            "ratio": script_config.get("ratio", "16:9"),
            "style": script_config.get("style", "动漫风"),
            "duration": script_config.get("duration", "系统推荐"),
            "narrator": script_config.get("narrator", "需要旁白"),
            "mood": script_config.get("mood", "温馨感人"),
            "density": script_config.get("density", "balanced"),
            "target_chapters": target_chapters,
        },
        "references": references,
        "move_hints": move_hints,
        "scene_plan": scene_plan,
        "quality_bar": [
            "输出必须包含剧本概览、分镜设计、视觉风格、AIGC执行规格(JSON)",
            "AIGC JSON 中 shots 数量应与分镜设计一致，且每个镜头有 summary、visualDesc、duration",
            "若使用检索素材，shots.source_refs 必须来自 references.ref_id，并填写 source_reason",
            "reference_trace 必须总结素材使用与未使用原因",
        ],
    }

    return {
        "script_plan": script_plan,
        "plan_text": _json_text(script_plan),
    }


def write_scenes_node(state: ScriptAgentState, config: RunnableConfig) -> dict[str, Any]:
    """
    生成剧本内容

    调用 SCRIPT_GENERATION_PROMPT 生成剧本
    """
    logger.info("✍️ [Script] Write Scenes Node")

    user_input = state.get("user_input", "")
    script_config = state.get("script_config", {})
    target_chapters = state.get("target_chapters", 1)
    move_codebook = state.get("move_codebook")
    script_plan = state.get("script_plan")
    revision_feedback = state.get("revision_feedback") or "（无，本次为首次生成或上一轮已通过）"

    try:
        llm = get_llm()

        # 构建剧本生成 Prompt
        ratio = script_config.get("ratio", "16:9")
        style = script_config.get("style", "动漫风")
        duration = script_config.get("duration", "系统推荐")
        narrator = script_config.get("narrator", "需要旁白")
        mood = script_config.get("mood", "温馨感人")
        density = script_config.get("density", "balanced")

        # 如果有多章/多场景需求，可以在 prompt 中说明
        chapters_hint = ""
        if target_chapters > 1:
            chapters_hint = f"\n注意：本剧本分为 {target_chapters} 个章节/场景，请为每个章节设计相应的分镜。"

        # 格式化检索结果为参考素材
        reference_text = ""
        retrieval_results = state.get("retrieval_results")
        if retrieval_results:
            parts = []
            for r in retrieval_results:
                title = r.get("tree_node", {}).get("title", "未知")
                novel = r.get("novel_name", "未知")
                summary = r.get("tree_node", {}).get("summary", "")
                content = r.get("content", "")[:800]
                ref_id = f"{r.get('novel_id', 'unknown')}#{r.get('node_id', 'unknown')}"
                parts.append(
                    f"【{novel} - {title}】\nref_id: {ref_id}\n摘要：{summary}\n内容片段：{content}"
                )
            reference_text = "\n\n".join(parts)

        move_guidance_ir_obj, move_guidance_ir_text = _build_move_guidance_ir(
            user_input=user_input,
            move_codebook=move_codebook if isinstance(move_codebook, dict) else None,
            retrieval_results=retrieval_results if isinstance(retrieval_results, list) else None,
        )

        script_prompt = SCRIPT_GENERATION_PROMPT.format(
            RATIO=ratio,
            STYLE=style,
            DURATION=duration,
            NARRATOR=narrator,
            MOOD=mood,
            DENSITY=density,
            USER_INPUT=user_input + chapters_hint,
            REFERENCE_MATERIALS=reference_text,
            MOVE_GUIDANCE_IR=move_guidance_ir_text,
            SCRIPT_PLAN=_json_text(script_plan or {}),
            REVISION_FEEDBACK=revision_feedback,
        )

        if settings.debug_llm_io:
            _dbg("script_writing.input", script_prompt[:2000])

        # 使用流式调用，让 LangGraph astream_events 能捕获 on_chat_model_stream
        chunks = []
        for chunk in llm.stream(
            [SystemMessage(content=script_prompt)],
            config=config,
        ):
            chunk_text = _to_text(getattr(chunk, "content", chunk))
            if chunk_text:
                chunks.append(chunk_text)

        raw_text = "".join(chunks)

        if settings.debug_llm_io:
            _dbg("script_writing.raw", raw_text[:3000])

        logger.info(f"剧本生成完成，长度: {len(raw_text)} 字符")

        return {
            "draft_script": raw_text,
            "final_script": raw_text,
            "iteration_count": state.get("iteration_count", 0) + 1,
            "prompt_used": script_prompt,
            "move_guidance_ir": move_guidance_ir_obj,
        }

    except Exception as e:
        logger.exception(f"❌ 剧本生成失败: {e}")
        return {
            "draft_script": None,
            "final_script": None,
            "error": str(e),
            "iteration_count": state.get("iteration_count", 0) + 1,
        }


def verify_script_node(state: ScriptAgentState) -> dict[str, Any]:
    """
    确定性审核 Executor 产出的剧本与 AIGC JSON。

    该节点不调用 LLM，只做结构、引用、镜头与时长约束检查，并生成给下一轮
    write_scenes_node 使用的 revision_feedback。
    """
    logger.info("🔎 [Script] Verify Script Node")

    final_script = state.get("final_script") or ""
    retrieval_ref_set = set(_retrieval_ref_ids(state.get("retrieval_results")))
    critical_issues: list[str] = []
    issues: list[str] = []

    if "## 剧本概览" not in final_script:
        issues.append("缺少 ## 剧本概览 段落")
    if "## 分镜设计" not in final_script:
        issues.append("缺少 ## 分镜设计 段落")
    if "## 视觉风格" not in final_script:
        issues.append("缺少 ## 视觉风格 段落")

    aigc_spec = _extract_aigc_spec(final_script)
    if not aigc_spec:
        critical_issues.append("缺少可解析的 ## AIGC执行规格(JSON)")
        verification_result = {
            "passed": False,
            "score": 0,
            "critical_issues": critical_issues,
            "issues": issues,
            "revision_feedback": "请严格补齐 ## AIGC执行规格(JSON)，并确保 JSON 对象可被解析。",
        }
        return {
            "verification_result": verification_result,
            "revision_feedback": verification_result["revision_feedback"],
            "revision_count": state.get("revision_count", 0) + 1,
        }

    shots = aigc_spec.get("shots")
    if not isinstance(shots, list) or not shots:
        critical_issues.append("AIGC JSON 中 shots 必须是非空数组")
        shots = []

    if shots and not (4 <= len(shots) <= 12):
        issues.append(f"shots 数量为 {len(shots)}，建议控制在 4-12 个镜头")

    total_duration = 0.0
    used_refs: set[str] = set()
    invalid_refs: set[str] = set()
    for idx, shot in enumerate(shots, start=1):
        if not isinstance(shot, dict):
            critical_issues.append(f"第 {idx} 个 shot 不是 JSON 对象")
            continue

        if not str(shot.get("summary") or "").strip():
            issues.append(f"第 {idx} 个 shot 缺少 summary")
        if not str(shot.get("visualDesc") or shot.get("director_brief") or "").strip():
            critical_issues.append(f"第 {idx} 个 shot 缺少 visualDesc/director_brief")
        duration_sec = _parse_duration_seconds(shot.get("duration"))
        if duration_sec <= 0:
            issues.append(f"第 {idx} 个 shot 缺少有效 duration")
        total_duration += duration_sec

        source_refs_raw = shot.get("source_refs")
        if isinstance(source_refs_raw, list):
            source_refs = source_refs_raw
            for ref in source_refs:
                ref_text = str(ref).strip()
                if not ref_text:
                    continue
                used_refs.add(ref_text)
                if retrieval_ref_set and ref_text not in retrieval_ref_set:
                    invalid_refs.add(ref_text)
        else:
            source_refs = []
            issues.append(f"第 {idx} 个 shot 的 source_refs 应为数组")
        if source_refs and not str(shot.get("source_reason") or "").strip():
            issues.append(f"第 {idx} 个 shot 使用 source_refs 但缺少 source_reason")
        if not source_refs and not str(shot.get("no_source_reason") or "").strip():
            issues.append(f"第 {idx} 个 shot 未使用 source_refs 但缺少 no_source_reason")

    if invalid_refs:
        critical_issues.append(
            "存在未命中检索集合的 source_refs: " + ", ".join(sorted(invalid_refs))
        )

    reference_trace = aigc_spec.get("reference_trace")
    if not isinstance(reference_trace, dict):
        issues.append("AIGC JSON 缺少 reference_trace")
    elif retrieval_ref_set:
        trace_refs = reference_trace.get("retrieval_refs")
        if not isinstance(trace_refs, list) or not trace_refs:
            issues.append("reference_trace.retrieval_refs 为空，无法追踪检索素材")

    target_duration = state.get("target_duration_sec") or _parse_duration_seconds(
        (state.get("script_config") or {}).get("duration")
    )
    if target_duration and total_duration:
        lower = float(target_duration) * 0.65
        upper = float(target_duration) * 1.45
        if total_duration < lower or total_duration > upper:
            issues.append(
                f"shots 总时长约 {total_duration:.1f}s，与目标 {float(target_duration):.1f}s 偏差较大"
            )

    if retrieval_ref_set and not used_refs:
        issues.append("已有检索参考素材，但 shots.source_refs 没有使用任何 ref_id")

    score = max(0, 100 - len(critical_issues) * 35 - len(issues) * 8)
    passed = not critical_issues and score >= 72
    feedback_items = critical_issues + issues
    if passed:
        revision_feedback = ""
    else:
        revision_feedback = "请修复以下问题后重写剧本和 AIGC JSON：\n" + "\n".join(
            f"- {item}" for item in feedback_items[:8]
        )

    verification_result = {
        "passed": passed,
        "score": score,
        "critical_issues": critical_issues,
        "issues": issues,
        "used_refs": sorted(used_refs),
        "retrieval_refs": sorted(retrieval_ref_set),
        "estimated_duration_sec": round(total_duration, 1),
        "revision_feedback": revision_feedback,
    }

    return {
        "verification_result": verification_result,
        "revision_feedback": revision_feedback,
        "revision_count": state.get("revision_count", 0) + (0 if passed else 1),
    }


def review_script_node(state: ScriptAgentState) -> Command[Literal["write_scenes", "finalize"]]:
    """
    Run semantic ReviewSubagent and route with Command.

    The wrapper owns parent-state mapping and bounded rewrite policy. The subagent
    only reviews a compact input and returns a structured review result.
    """
    logger.info("🧑‍⚖️ [Script] Review Script Node")

    verification_result = state.get("verification_result") or {}
    revision_count = state.get("revision_count", 0)

    if not verification_result.get("passed"):
        structural_issues = (
            verification_result.get("critical_issues") or []
        ) + (verification_result.get("issues") or [])
        revision_feedback = (
            verification_result.get("revision_feedback")
            or state.get("revision_feedback")
            or "请先修复结构化审核问题。"
        )
        quality_review_result = {
            "passed": False,
            "review_available": False,
            "review_skipped": True,
            "alignment_score": 0,
            "fluency_score": 0,
            "story_consistency_score": 0,
            "aigc_executability_score": 0,
            "overall_score": int(verification_result.get("score") or 0),
            "issues": [
                {
                    "type": "structural",
                    "severity": "major",
                    "message": str(issue),
                }
                for issue in structural_issues[:8]
            ],
            "revision_feedback": revision_feedback,
            "summary": "结构化规则未通过，跳过语义审核并进入有界重写。",
        }
        goto: Literal["write_scenes", "finalize"] = (
            "write_scenes" if revision_count < 2 else "finalize"
        )
        return Command(
            update={
                "quality_review_result": quality_review_result,
                "revision_feedback": revision_feedback,
            },
            goto=goto,
        )

    review_result = run_review_subagent(
        {
            "user_input": state.get("user_input", ""),
            "script_plan": state.get("script_plan"),
            "final_script": state.get("final_script") or "",
            "aigc_spec": _extract_aigc_spec(state.get("final_script") or ""),
            "retrieval_refs": _retrieval_ref_ids(state.get("retrieval_results")),
            "structural_verification": verification_result,
        }
    )
    review_passed = bool(review_result.get("passed"))
    revision_feedback = ""
    if not review_passed:
        revision_feedback = (
            str(review_result.get("revision_feedback") or "").strip()
            or "请根据 ReviewSubagent 审核意见提升用户意图一致性、语言流畅度、剧情连贯性和 AIGC 可执行性。"
        )

    next_revision_count = revision_count + (0 if review_passed else 1)
    goto = "finalize" if review_passed or next_revision_count >= 2 else "write_scenes"

    return Command(
        update={
            "quality_review_result": review_result,
            "revision_feedback": revision_feedback,
            "revision_count": next_revision_count,
        },
        goto=goto,
    )


def finalize_node(state: ScriptAgentState) -> dict[str, Any]:
    """
    整理最终输出

    直接返回已有的 final_script
    """
    logger.info("✅ [Script] Finalize Node")

    final_script = state.get("final_script")
    if not final_script:
        return {
            "final_script": "抱歉，剧本生成失败",
        }

    return {
        "final_script": final_script,
    }
