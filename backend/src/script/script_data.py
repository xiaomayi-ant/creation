"""Script detail parser for frontend ScriptView data.

从 LLM 生成的剧本文本中解析 AIGC JSON 块，映射为前端 ScriptData 结构。
不再调用 LLM 做二次提取，纯解析操作（毫秒级）。
"""

from __future__ import annotations

import json
import re
from typing import Any

from src.core.logger import get_logger

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# 工具函数
# ---------------------------------------------------------------------------

def _clean_markdown(text: str) -> str:
    cleaned = re.sub(r"^```[^\n]*\n?", "", text, flags=re.MULTILINE)
    cleaned = re.sub(r"```$", "", cleaned, flags=re.MULTILINE)
    return cleaned.strip()


def _decode_json_value(text: str) -> Any:
    """从文本中提取第一个 JSON 对象或数组。"""
    raw = text.strip()
    if not raw:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass

    fenced_blocks = re.findall(r"```(?:json)?\s*([\s\S]*?)```", raw)
    for block in fenced_blocks:
        candidate = block.strip()
        if not candidate:
            continue
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            continue

    decoder = json.JSONDecoder()
    starts = [i for i in (raw.find("{"), raw.find("[")) if i >= 0]
    if not starts:
        return None
    start = min(starts)
    try:
        value, _ = decoder.raw_decode(raw[start:])
        return value
    except Exception:
        return None


def _split_sections(text: str) -> tuple[str, str, str]:
    """从剧本文本中切分出 synopsis / shots_text / style_text 三段。"""
    normalized = _clean_markdown(text)
    shot_match = re.search(r"(?:^|\n)\s*(?:#{1,3}\s*)?分镜设计", normalized)
    style_match = re.search(r"(?:^|\n)\s*(?:#{1,3}\s*)?视觉风格", normalized)
    aigc_match = re.search(r"(?:^|\n)\s*(?:#{1,3}\s*)?AIGC执行规格", normalized)

    shot_idx = shot_match.start() if shot_match else -1
    style_idx = style_match.start() if style_match else -1
    aigc_idx = aigc_match.start() if aigc_match else -1

    # 确定视觉风格段的结束位置（AIGC 段开始处，或文本末尾）
    style_end = aigc_idx if aigc_idx != -1 else len(normalized)

    synopsis = ""
    shots = ""
    style = ""
    if shot_idx != -1 and style_idx != -1:
        synopsis = normalized[:shot_idx].strip()
        shots = normalized[shot_idx:style_idx].strip()
        style = normalized[style_idx:style_end].strip()
    elif shot_idx != -1:
        synopsis = normalized[:shot_idx].strip()
        shots = normalized[shot_idx:style_end].strip()
    elif style_idx != -1:
        synopsis = normalized[:style_idx].strip()
        style = normalized[style_idx:style_end].strip()
    else:
        synopsis = normalized

    synopsis = re.sub(r"^(?:#{1,3}\s*)?剧本概览\s*", "", synopsis, flags=re.MULTILINE)
    synopsis = re.sub(r"^故事核心[：:]\s*", "", synopsis, flags=re.MULTILINE)
    shots = re.sub(r"^(?:#{1,3}\s*)?分镜设计\s*", "", shots, flags=re.MULTILINE).strip()
    style = re.sub(r"^(?:#{1,3}\s*)?视觉风格\s*", "", style, flags=re.MULTILINE).strip()
    return synopsis.strip(), shots, style


# ---------------------------------------------------------------------------
# AIGC JSON 提取与解析
# ---------------------------------------------------------------------------

def _extract_aigc_json(final_copy: str) -> dict[str, Any] | None:
    """从剧本 markdown 原文中提取 ## AIGC执行规格(JSON) 段并解析。"""
    normalized = _clean_markdown(final_copy)
    section = re.search(
        r"(?:^|\n)\s*(?:#{1,3}\s*)?AIGC执行规格(?:\s*\(JSON\)|\s*（JSON）)?\s*\n([\s\S]*?)(?=\n\s*#{1,3}\s+\S|\Z)",
        normalized,
    )
    if not section:
        logger.warning("未找到 AIGC执行规格 JSON 段")
        return None
    value = _decode_json_value(section.group(1))
    if isinstance(value, dict):
        return value
    if isinstance(value, list):
        return {"shots": value}
    logger.warning("AIGC JSON 解析失败")
    return None


# ---------------------------------------------------------------------------
# 结构标准化
# ---------------------------------------------------------------------------

def _normalize_characters(raw: Any) -> list[dict[str, Any]]:
    """标准化 characters 数组。"""
    if not isinstance(raw, list):
        return []
    characters: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in raw:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        if not name or name in seen:
            continue
        seen.add(name)

        app_raw = item.get("appearance")
        if isinstance(app_raw, dict):
            appearance = {
                "age": str(app_raw.get("age") or "").strip(),
                "identity": str(app_raw.get("identity") or "").strip(),
                "features": str(app_raw.get("features") or "").strip(),
            }
        else:
            appearance = {"age": "", "identity": "", "features": ""}

        role = str(item.get("role") or "配角").strip()
        if role not in ("主角", "配角", "功能性角色"):
            role = "配角"

        characters.append({
            "id": str(len(characters) + 1),
            "name": name,
            "role": role,
            "appearance": appearance,
            "voice": str(item.get("voice") or "").strip(),
            "description": str(item.get("description") or "").strip(),
        })
    return characters


def _normalize_scenes(raw: Any) -> list[dict[str, str]]:
    """标准化 scenes 数组。"""
    if not isinstance(raw, list):
        return []
    scenes: list[dict[str, str]] = []
    seen: set[str] = set()
    for item in raw:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        if not name or name in seen:
            continue
        seen.add(name)
        scenes.append({
            "id": str(len(scenes) + 1),
            "name": name,
            "description": str(item.get("description") or "").strip(),
        })
    return scenes


def _normalize_props(raw: Any) -> list[dict[str, str]]:
    """标准化 props 数组。"""
    if not isinstance(raw, list):
        return []
    props: list[dict[str, str]] = []
    seen: set[str] = set()
    for item in raw:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        if not name or name in seen:
            continue
        seen.add(name)
        ptype = str(item.get("type") or "普通道具").strip()
        if ptype not in ("关键道具", "普通道具"):
            ptype = "普通道具"
        props.append({
            "id": str(len(props) + 1),
            "name": name,
            "type": ptype,
        })
    return props


def _opening_narration(synopsis: str) -> str:
    sentences = [s.strip() for s in re.split(r"[。！？]", synopsis) if s.strip()]
    if not sentences:
        return ""
    return "，".join(sentences[:2]).rstrip("，") + "！"


def _normalize_shots(raw: Any, synopsis: str) -> list[dict[str, Any]]:
    """标准化 shots 数组。"""
    if not isinstance(raw, list):
        return []

    opening = _opening_narration(synopsis)
    shots: list[dict[str, Any]] = []
    for idx, item in enumerate(raw, start=1):
        if not isinstance(item, dict):
            continue
        shot_name = str(item.get("shotName") or item.get("name") or "").strip()
        visual_desc = str(item.get("visualDesc") or item.get("director_brief") or "").strip()
        summary = str(item.get("summary") or "").strip()
        if not summary:
            first_sentence = re.split(r"[。；\n]", visual_desc)[0].strip() if visual_desc else ""
            summary = first_sentence[:80] if first_sentence else visual_desc[:80]
        if not shot_name and not visual_desc:
            continue

        narration = str(item.get("narration") or "").strip()
        has_narration = bool(item.get("hasNarration"))
        if idx == 1 and not narration and opening:
            narration = opening
            has_narration = True
        source_refs_raw = item.get("source_refs")
        if isinstance(source_refs_raw, list):
            source_refs = [str(x).strip() for x in source_refs_raw if str(x).strip()]
        else:
            source_refs = []
        source_reason = str(item.get("source_reason") or "").strip()
        no_source_reason = str(item.get("no_source_reason") or "").strip()

        shots.append({
            "id": idx,
            "duration": str(item.get("duration") or "3.0s").strip() or "3.0s",
            "summary": summary,
            "narration": narration,
            "hasNarration": has_narration,
            "source_refs": source_refs,
            "source_reason": source_reason,
            "no_source_reason": no_source_reason,
            "visualDesc": visual_desc,
            "shotName": shot_name or f"镜头{idx}",
        })
    return shots


def _normalize_aigc_spec(aigc_data: dict[str, Any]) -> dict[str, Any] | None:
    """提取 aigcSpec 用于前端渲染（仅 render_spec 部分）。"""
    shots_raw = aigc_data.get("shots")
    if not isinstance(shots_raw, list):
        return None

    spec_shots: list[dict[str, Any]] = []
    for idx, shot in enumerate(shots_raw, start=1):
        if not isinstance(shot, dict):
            continue
        render_spec = shot.get("render_spec")
        if not isinstance(render_spec, dict):
            render_spec = {}
        sid = shot.get("id")
        try:
            shot_id = int(sid)
        except Exception:
            shot_id = idx
        spec_shots.append({
            "id": shot_id,
            "name": str(shot.get("name") or shot.get("shotName") or "").strip() or f"镜头{idx}",
            "director_brief": str(shot.get("director_brief") or "").strip(),
            "source_refs": [
                str(x).strip() for x in (shot.get("source_refs") or [])
                if str(x).strip()
            ] if isinstance(shot.get("source_refs"), list) else [],
            "source_reason": str(shot.get("source_reason") or "").strip(),
            "no_source_reason": str(shot.get("no_source_reason") or "").strip(),
            "render_spec": render_spec,
        })

    global_negative = aigc_data.get("global_negative")
    if not isinstance(global_negative, list):
        global_negative = []

    reference_trace = aigc_data.get("reference_trace")
    if not isinstance(reference_trace, dict):
        reference_trace = {
            "retrieval_refs": [],
            "used_refs": [],
            "unused_refs": [],
            "unused_reasons": [],
            "overall_reason": "",
        }
    else:
        retrieval_refs = reference_trace.get("retrieval_refs")
        used_refs = reference_trace.get("used_refs")
        unused_refs = reference_trace.get("unused_refs")
        unused_reasons = reference_trace.get("unused_reasons")
        reference_trace = {
            "retrieval_refs": [str(x).strip() for x in retrieval_refs if str(x).strip()] if isinstance(retrieval_refs, list) else [],
            "used_refs": [str(x).strip() for x in used_refs if str(x).strip()] if isinstance(used_refs, list) else [],
            "unused_refs": [str(x).strip() for x in unused_refs if str(x).strip()] if isinstance(unused_refs, list) else [],
            "unused_reasons": unused_reasons if isinstance(unused_reasons, list) else [],
            "overall_reason": str(reference_trace.get("overall_reason") or "").strip(),
        }

    return {
        "density": str(aigc_data.get("density") or "balanced").strip() or "balanced",
        "global_negative": [str(x).strip() for x in global_negative if str(x).strip()],
        "shots": spec_shots,
        "reference_trace": reference_trace,
    }


# ---------------------------------------------------------------------------
# Regex 兜底提取（AIGC JSON 解析失败时使用）
# ---------------------------------------------------------------------------

def _regex_extract_shots(shots_text: str, synopsis: str) -> list[dict[str, Any]]:
    """从分镜设计 markdown 文本中用 regex 提取 shots。"""
    shot_items: list[tuple[str, str]] = []
    for line in [ln.strip() for ln in shots_text.splitlines() if ln.strip()]:
        bullet_match = re.match(r"^[-*]\s*\*\*([^*]+)\*\*\s*[-：:]\s*(.+)$", line)
        if bullet_match:
            shot_items.append((bullet_match.group(1).strip(), bullet_match.group(2).strip()))
            continue
        bracket_match = re.match(r"^【(.+?)】\s*(.+)$", line)
        if bracket_match:
            shot_items.append((bracket_match.group(1).strip(), bracket_match.group(2).strip()))
            continue
    if not shot_items:
        return []

    opening = _opening_narration(synopsis)
    shots: list[dict[str, Any]] = []
    for idx, (shot_name, body) in enumerate(shot_items, start=1):
        first_sentence = re.split(r"[。；\n]", body)[0].strip() if body else ""
        summary = first_sentence[:80] if first_sentence else body[:80]
        shots.append({
            "id": idx,
            "duration": "3.0s",
            "summary": summary,
            "narration": opening if idx == 1 else "",
            "hasNarration": bool(idx == 1 and opening),
            "visualDesc": body,
            "shotName": shot_name,
        })
    return shots


# ---------------------------------------------------------------------------
# 主入口
# ---------------------------------------------------------------------------

def build_script_data(
    *,
    final_copy: str,
    user_input: str,
    title: str | None = None,
    duration_sec: int | None = None,
    style_name: str | None = None,
) -> dict[str, Any]:
    """Convert script markdown text to UI-friendly structured data.

    策略：从 AIGC JSON 段直接解析（毫秒级），regex 仅在解析失败时兜底。
    """
    synopsis, shots_text, style_text = _split_sections(final_copy)

    # ---- 优先从 AIGC JSON 提取 ----
    aigc_data = _extract_aigc_json(final_copy)

    if aigc_data:
        logger.info("script_data: 从 AIGC JSON 解析结构化数据")
        characters = _normalize_characters(aigc_data.get("characters"))
        scenes = _normalize_scenes(aigc_data.get("scenes"))
        props = _normalize_props(aigc_data.get("props"))
        shot_list = _normalize_shots(aigc_data.get("shots"), synopsis)
        aigc_spec = _normalize_aigc_spec(aigc_data)
    else:
        # ---- AIGC JSON 解析失败，回退 regex ----
        logger.warning("script_data: AIGC JSON 解析失败，回退 regex 兜底")
        characters = []
        scenes = []
        props = []
        shot_list = _regex_extract_shots(shots_text, synopsis)
        aigc_spec = None

    shot_count = len(shot_list)
    duration_label = (
        f"{duration_sec} 秒"
        if duration_sec
        else (f"{shot_count * 3} 秒" if shot_count else "24 秒")
    )

    return {
        "title": title or user_input[:20] or "剧本创作",
        "totalShots": shot_count or 8,
        "totalDuration": duration_label,
        "style": style_name or "日漫 电影质感",
        "requirements": user_input,
        "synopsis": synopsis or "暂无故事梗概",
        "packagingStyle": style_text or "暂无包装风格描述",
        "characters": characters,
        "scenes": scenes,
        "props": props,
        "shots": shot_list,
        "aigcSpec": aigc_spec,
    }
