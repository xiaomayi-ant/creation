"""script_data → Episode + Storyboard 桥接转换"""

import json
import logging
from typing import Any

from sqlalchemy.orm import Session

from src.core.database import EpisodeDB, StoryboardDB

logger = logging.getLogger(__name__)


def script_data_to_episode(
    session: Session,
    script_data: dict[str, Any],
    thread_id: str,
    title: str | None = None,
) -> EpisodeDB:
    """将 build_script_data 产出的结构转换为 Episode + Storyboard 记录。

    Parameters
    ----------
    session : SQLAlchemy session
    script_data : build_script_data() 返回的字典
    thread_id : 会话线程 ID
    title : 剧集标题（缺省使用 script_data["title"]）

    Returns
    -------
    EpisodeDB  已 commit 的 Episode 对象（含 storyboards 关系）
    """
    ep_title = title or script_data.get("title", "未命名剧集")
    script_content = json.dumps(script_data, ensure_ascii=False)

    episode = EpisodeDB(
        title=ep_title,
        script_content=script_content,
        thread_id=thread_id,
        duration=0,
    )
    session.add(episode)
    session.flush()  # 获取 episode.id

    shots = script_data.get("shots", [])
    aigc_spec = script_data.get("aigcSpec") or {}
    aigc_shots = {s.get("id"): s for s in (aigc_spec.get("shots") or []) if isinstance(s, dict)}

    total_duration = 0
    for idx, shot in enumerate(shots, start=1):
        if not isinstance(shot, dict):
            continue

        shot_id = shot.get("id", idx)
        aigc_shot = aigc_shots.get(shot_id, {})
        render_spec = aigc_shot.get("render_spec", {}) if isinstance(aigc_shot, dict) else {}

        duration_raw = shot.get("duration", "3.0s")
        duration_sec = _parse_duration(duration_raw)
        total_duration += duration_sec

        location = str(render_spec.get("location", "")).strip()
        shot_type = str(render_spec.get("shot_type", "")).strip()
        angle = str(render_spec.get("angle", "")).strip()
        movement = str(render_spec.get("movement", "")).strip()

        visual_desc = str(shot.get("visualDesc", "")).strip()
        narration = str(shot.get("narration", "")).strip()
        shot_name = str(shot.get("shotName", f"镜头{idx}")).strip()

        image_prompt = build_image_prompt(location, visual_desc)
        video_prompt = build_video_prompt(visual_desc, narration, movement, shot_type, angle, location)

        sb = StoryboardDB(
            episode_id=episode.id,
            storyboard_number=idx,
            title=shot_name,
            location=location,
            shot_type=shot_type,
            angle=angle,
            movement=movement,
            action=visual_desc,
            dialogue=narration,
            duration=duration_sec,
            image_prompt=image_prompt,
            video_prompt=video_prompt,
            render_spec=render_spec,
        )
        session.add(sb)

    episode.duration = total_duration
    session.commit()
    logger.info("bridge: 创建 Episode %d (%s), %d 条分镜, 总时长 %ds",
                episode.id, ep_title, len(shots), total_duration)
    return episode


def _parse_duration(raw: Any) -> int:
    """将 '3.0s' / '5s' / 3 等格式转为整数秒。"""
    if isinstance(raw, (int, float)):
        return max(1, int(raw))
    s = str(raw).strip().lower().rstrip("s")
    try:
        return max(1, int(float(s)))
    except (ValueError, TypeError):
        return 3


def build_image_prompt(location: str, visual_desc: str) -> str:
    parts = [p for p in [location, visual_desc] if p]
    base = ", ".join(parts) if parts else "scene"
    return f"{base}, anime style, first frame"


def build_video_prompt(
    visual_desc: str,
    narration: str,
    movement: str,
    shot_type: str,
    angle: str,
    location: str,
) -> str:
    segments = []
    if visual_desc:
        segments.append(f"Action: {visual_desc}")
    if narration:
        segments.append(f"Dialogue: {narration}")
    if movement:
        segments.append(f"Camera movement: {movement}")
    if shot_type:
        segments.append(f"Shot type: {shot_type}")
    if angle:
        segments.append(f"Camera angle: {angle}")
    if location:
        segments.append(f"Scene: {location}")
    return ". ".join(segments)
