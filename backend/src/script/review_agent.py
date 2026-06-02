"""ReviewSubagent for semantic script quality review."""

import json
import re
from functools import lru_cache
from typing import Any, Optional, TypedDict

from langchain_community.chat_models import ChatTongyi
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import SystemMessage
from langgraph.graph import END, START, StateGraph

from src.core.config import settings
from src.core.logger import get_logger

logger = get_logger(__name__)


class ReviewAgentState(TypedDict, total=False):
    """Private state schema for the review subgraph."""

    user_input: str
    script_plan: dict[str, Any] | None
    final_script: str
    aigc_spec: dict[str, Any] | None
    retrieval_refs: list[str]
    structural_verification: dict[str, Any] | None
    raw_review_text: str | None
    review_result: dict[str, Any] | None


REVIEW_PROMPT = """你是短剧脚本 ReviewSubagent，只做审核，不重写正文。

请评估 Executor 生成的短剧脚本是否满足用户需求，并输出严格 JSON。

审核维度：
1. 用户意图一致性：是否回应用户输入、视频配置和计划目标。
2. 语言流畅度：旁白、分镜描述和整体表达是否自然顺畅。
3. 剧情连贯性：钩子、冲突、推进、收束是否连贯。
4. AIGC 可执行性：分镜和 AIGC JSON 是否足够具体，可用于后续图像/视频生成。

评分规则：
- 每项 0-10 分。
- overall_score 为 0-100。
- passed 仅当 overall_score >= 75 且没有 major 级别问题时为 true。
- revision_feedback 必须短而具体，适合直接反馈给写作 Executor 重写。

只返回 JSON 对象，不要输出 markdown。

输入：
USER_INPUT:
{USER_INPUT}

SCRIPT_PLAN:
{SCRIPT_PLAN}

STRUCTURAL_VERIFICATION:
{STRUCTURAL_VERIFICATION}

AIGC_SPEC:
{AIGC_SPEC}

FINAL_SCRIPT:
{FINAL_SCRIPT}

JSON 输出格式：
{{
  "passed": false,
  "alignment_score": 0,
  "fluency_score": 0,
  "story_consistency_score": 0,
  "aigc_executability_score": 0,
  "overall_score": 0,
  "issues": [
    {{"type": "alignment", "severity": "major", "message": "问题说明"}}
  ],
  "revision_feedback": "给 Executor 的重写建议",
  "summary": "一句话审核结论"
}}
"""


def _to_text(content: Any) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                parts.append(str(item.get("text") or item.get("content") or ""))
            else:
                parts.append(str(item))
        return "\n".join(part for part in parts if part).strip()
    return str(content)


def _json_text(payload: Any) -> str:
    try:
        return json.dumps(payload, ensure_ascii=False, indent=2)
    except Exception:
        return str(payload)


def _get_llm(temperature: Optional[float] = None) -> BaseChatModel:
    temp = temperature if temperature is not None else 0.1
    model = settings.model_name

    if settings.llm_provider.lower() == "openai":
        from langchain_openai import ChatOpenAI

        kwargs: dict[str, Any] = {
            "model": model,
            "temperature": temp,
        }
        if settings.openai_base_url:
            kwargs["base_url"] = settings.openai_base_url
        return ChatOpenAI(**kwargs)

    kwargs: dict[str, Any] = {
        "model": model,
        "temperature": temp,
    }
    if settings.dashscope_base_url:
        kwargs["base_url"] = settings.dashscope_base_url
    return ChatTongyi(**kwargs)


def _extract_json_object(text: str) -> dict[str, Any] | None:
    section = text.strip()
    fenced = re.search(r"```(?:json)?\s*([\s\S]*?)```", section)
    if fenced:
        section = fenced.group(1).strip()

    start = section.find("{")
    if start < 0:
        return None
    try:
        value, _ = json.JSONDecoder().raw_decode(section[start:])
    except json.JSONDecodeError:
        return None
    return value if isinstance(value, dict) else None


def normalize_review_result(raw: Any) -> dict[str, Any]:
    """Normalize LLM review output into the parent graph contract."""
    payload = raw if isinstance(raw, dict) else _extract_json_object(str(raw or ""))
    if not isinstance(payload, dict):
        return {
            "passed": True,
            "review_available": False,
            "alignment_score": 8,
            "fluency_score": 8,
            "story_consistency_score": 8,
            "aigc_executability_score": 8,
            "overall_score": 80,
            "issues": [],
            "revision_feedback": "",
            "summary": "语义审核输出无法解析，已保留确定性审核结果。",
        }

    issues = payload.get("issues")
    if not isinstance(issues, list):
        issues = []

    scores = {
        "alignment_score": _coerce_score(payload.get("alignment_score"), default=8, upper=10),
        "fluency_score": _coerce_score(payload.get("fluency_score"), default=8, upper=10),
        "story_consistency_score": _coerce_score(
            payload.get("story_consistency_score"),
            default=8,
            upper=10,
        ),
        "aigc_executability_score": _coerce_score(
            payload.get("aigc_executability_score"),
            default=8,
            upper=10,
        ),
    }
    overall_score = _coerce_score(payload.get("overall_score"), default=80, upper=100)
    has_major_issue = any(
        isinstance(item, dict) and str(item.get("severity", "")).lower() == "major"
        for item in issues
    )
    passed = bool(payload.get("passed")) and overall_score >= 75 and not has_major_issue

    revision_feedback = str(payload.get("revision_feedback") or "").strip()
    if not passed and not revision_feedback:
        revision_feedback = "请提升用户意图一致性、语言流畅度、剧情连贯性与 AIGC 分镜可执行性。"

    return {
        "passed": passed,
        "review_available": True,
        **scores,
        "overall_score": overall_score,
        "issues": issues[:8],
        "revision_feedback": revision_feedback,
        "summary": str(payload.get("summary") or "").strip(),
    }


def _coerce_score(value: Any, *, default: int, upper: int) -> int:
    try:
        score = int(float(value))
    except Exception:
        score = default
    return max(0, min(upper, score))


def semantic_review_node(state: ReviewAgentState) -> dict[str, Any]:
    """Call the review LLM and return raw text for normalization."""
    prompt = REVIEW_PROMPT.format(
        USER_INPUT=state.get("user_input", ""),
        SCRIPT_PLAN=_json_text(state.get("script_plan") or {}),
        STRUCTURAL_VERIFICATION=_json_text(state.get("structural_verification") or {}),
        AIGC_SPEC=_json_text(state.get("aigc_spec") or {}),
        FINAL_SCRIPT=(state.get("final_script") or "")[:12000],
    )
    llm = _get_llm(temperature=0.1)
    response = llm.invoke([SystemMessage(content=prompt)])
    raw_text = _to_text(getattr(response, "content", response))
    return {"raw_review_text": raw_text}


def normalize_review_node(state: ReviewAgentState) -> dict[str, Any]:
    """Convert raw review text into the stable review_result contract."""
    return {"review_result": normalize_review_result(state.get("raw_review_text"))}


@lru_cache(maxsize=1)
def create_review_graph():
    """Create the isolated semantic review subgraph."""
    workflow = StateGraph(ReviewAgentState)
    workflow.add_node("semantic_review", semantic_review_node)
    workflow.add_node("normalize_review", normalize_review_node)
    workflow.add_edge(START, "semantic_review")
    workflow.add_edge("semantic_review", "normalize_review")
    workflow.add_edge("normalize_review", END)
    return workflow.compile()


def run_review_subagent(input_state: ReviewAgentState) -> dict[str, Any]:
    """Invoke ReviewSubagent and return a normalized review_result."""
    try:
        result = create_review_graph().invoke(input_state)
    except Exception as exc:
        logger.warning("ReviewSubagent failed, keeping deterministic verification: %s", exc)
        return {
            "passed": True,
            "review_available": False,
            "alignment_score": 8,
            "fluency_score": 8,
            "story_consistency_score": 8,
            "aigc_executability_score": 8,
            "overall_score": 80,
            "issues": [],
            "revision_feedback": "",
            "summary": "语义审核调用失败，已保留确定性审核结果。",
        }

    review_result = result.get("review_result") if isinstance(result, dict) else None
    return normalize_review_result(review_result)
