"""Episode / Storyboard 查询服务"""

import json
import logging
from collections.abc import Mapping
from typing import Any

from sqlalchemy.orm import Session

from src.core.database import EpisodeDB, StoryboardDB
from src.storyboard.bridge import build_image_prompt, build_video_prompt

logger = logging.getLogger(__name__)


def get_episode_or_raise(session: Session, episode_id: int) -> EpisodeDB:
    """按 ID 查询 Episode，不存在则抛出 ValueError。"""
    episode = session.get(EpisodeDB, episode_id)
    if not episode:
        raise ValueError(f"episode {episode_id} not found")
    return episode


def get_episode_by_thread(session: Session, thread_id: str) -> EpisodeDB | None:
    """按 thread_id 查询最新 Episode。"""
    return (
        session.query(EpisodeDB)
        .filter(EpisodeDB.thread_id == thread_id)
        .order_by(EpisodeDB.created_at.desc())
        .first()
    )


def list_storyboards(session: Session, episode_id: int) -> list[StoryboardDB]:
    """按 storyboard_number 排序返回分镜列表。"""
    return (
        session.query(StoryboardDB)
        .filter(StoryboardDB.episode_id == episode_id)
        .order_by(StoryboardDB.storyboard_number)
        .all()
    )


def save_episode_manual_edits(
    session: Session,
    episode_id: int,
    characters: list[Mapping[str, Any]],
    shots: list[Mapping[str, Any]],
) -> dict[str, Any]:
    """Persist human storyboard edits before downstream AIGC generation."""
    episode = get_episode_or_raise(session, episode_id)
    storyboards = {sb.storyboard_number: sb for sb in list_storyboards(session, episode_id)}
    script_data = _load_script_data(episode.script_content)

    updated_characters = _apply_character_edits(script_data, characters)
    updated_storyboards = 0

    for edit in shots:
        storyboard_number = _to_int(edit.get("storyboard_number"), default=0)
        sb = storyboards.get(storyboard_number)
        if not sb:
            continue

        summary = str(edit.get("summary") or "").strip()
        visual_desc = str(edit.get("visual_desc") or "").strip()
        narration = str(edit.get("narration") or "").strip()
        duration_seconds = _duration_seconds(edit.get("duration_seconds"), fallback=sb.duration)
        tags = [str(tag).strip() for tag in (edit.get("tags") or []) if str(tag).strip()]

        if summary:
            sb.title = summary[:255]
        sb.action = visual_desc
        sb.dialogue = narration
        sb.duration = max(1, int(duration_seconds + 0.5))

        render_spec = dict(sb.render_spec or {})
        render_spec["manual_summary"] = summary
        render_spec["manual_tags"] = tags
        render_spec["human_reviewed"] = True
        render_spec["manual_media"] = {
            "start_frame_url": edit.get("start_frame_url") or "",
            "end_frame_url": edit.get("end_frame_url") or "",
            "keyframe_urls": [url for url in (edit.get("keyframe_urls") or []) if url],
        }
        sb.render_spec = render_spec

        if edit.get("start_frame_url"):
            sb.image_url = str(edit["start_frame_url"])

        sb.image_prompt = build_image_prompt(sb.location, visual_desc)
        sb.video_prompt = build_video_prompt(
            visual_desc,
            narration,
            sb.movement,
            sb.shot_type,
            sb.angle,
            sb.location,
        )

        _apply_shot_edit_to_script(script_data, storyboard_number, edit, duration_seconds)
        updated_storyboards += 1

    if updated_storyboards:
        episode.duration = sum(sb.duration for sb in storyboards.values())
    episode.script_content = json.dumps(script_data, ensure_ascii=False)

    session.commit()
    logger.info(
        "manual edits saved: episode=%d storyboards=%d characters=%d",
        episode_id,
        updated_storyboards,
        updated_characters,
    )

    return {
        "episode_id": episode_id,
        "updated_storyboards": updated_storyboards,
        "updated_characters": updated_characters,
        "status": "saved",
        "message": "人工分镜修改已保存，后续 AIGC 将使用更新后的分镜提示词",
    }


def _load_script_data(script_content: str) -> dict[str, Any]:
    try:
        loaded = json.loads(script_content or "{}")
    except json.JSONDecodeError:
        return {}
    return loaded if isinstance(loaded, dict) else {}


def _apply_character_edits(script_data: dict[str, Any], characters: list[Mapping[str, Any]]) -> int:
    existing = script_data.get("characters")
    if not isinstance(existing, list):
        return 0

    patches = {str(item.get("id")): item for item in characters if item.get("id") is not None}
    updated = 0
    for character in existing:
        if not isinstance(character, dict):
            continue
        patch = patches.get(str(character.get("id")))
        if not patch:
            continue

        if patch.get("name"):
            character["name"] = str(patch["name"])
        if patch.get("voice"):
            character["voice"] = str(patch["voice"])
        if patch.get("appearance"):
            appearance = character.get("appearance")
            if isinstance(appearance, dict):
                appearance["features"] = str(patch["appearance"])
                character["appearance"] = appearance
            else:
                character["appearance"] = {"features": str(patch["appearance"])}
        updated += 1

    return updated


def _apply_shot_edit_to_script(
    script_data: dict[str, Any],
    storyboard_number: int,
    edit: Mapping[str, Any],
    duration_seconds: float,
) -> None:
    shots = script_data.get("shots")
    if not isinstance(shots, list):
        return

    for index, shot in enumerate(shots, start=1):
        if not isinstance(shot, dict):
            continue
        shot_id = _to_int(shot.get("id"), default=index)
        if shot_id != storyboard_number:
            continue

        shot["summary"] = str(edit.get("summary") or shot.get("summary") or "")
        shot["visualDesc"] = str(edit.get("visual_desc") or shot.get("visualDesc") or "")
        narration = str(edit.get("narration") or "")
        shot["narration"] = narration
        shot["hasNarration"] = bool(narration.strip())
        shot["duration"] = f"{duration_seconds:.1f}s"
        break

    total = 0.0
    for shot in shots:
        if isinstance(shot, dict):
            total += _duration_seconds(shot.get("duration"), fallback=0)
    if total > 0:
        script_data["totalDuration"] = f"{total:.1f} 秒"


def _duration_seconds(value: Any, fallback: float = 0.0) -> float:
    if isinstance(value, int | float):
        return float(value) if value > 0 else fallback
    text = str(value or "").strip().lower().replace("秒", "").rstrip("s")
    try:
        parsed = float(text)
    except (TypeError, ValueError):
        return fallback
    return parsed if parsed > 0 else fallback


def _to_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default
