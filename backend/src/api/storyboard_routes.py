"""分镜板 API 路由"""

import logging

from fastapi import APIRouter, HTTPException

from src.api.schemas import (
    CreateEpisodeRequest,
    CreateEpisodeResponse,
    EpisodeFromScriptRequest,
    GenerateAigcResponse,
    GenerateStoryboardRequest,
    GenerateStoryboardResponse,
    SaveManualEditsRequest,
    SaveManualEditsResponse,
    TaskStatusResponse,
    VideoMergePrecheckResponse,
    VideoMergeRequest,
    VideoMergeResponse,
)
from src.core.database import AsyncTaskDB, EpisodeDB, get_database
from src.storyboard.bridge import script_data_to_episode
from src.storyboard.services import storyboard_service, task_service
from src.storyboard.tasks.aigc_tasks import generate_aigc_task
from src.storyboard.tasks.storyboard_tasks import generate_storyboard_task
from src.storyboard.tasks.video_tasks import merge_episode_videos_task
from src.storyboard.utils.ffmpeg_runner import (
    TransitionConfig,
    VideoClip,
    precheck_merge,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["分镜板"])


@router.post("/episodes", response_model=CreateEpisodeResponse)
def create_episode(req: CreateEpisodeRequest):
    """手动创建剧集"""
    db = get_database()
    session = db.get_session()
    try:
        episode = EpisodeDB(title=req.title, script_content=req.script_content)
        session.add(episode)
        session.commit()
        session.refresh(episode)
        return CreateEpisodeResponse(episode_id=episode.id, title=episode.title)
    finally:
        session.close()


@router.post("/episodes/from-script", response_model=CreateEpisodeResponse)
def create_episode_from_script(req: EpisodeFromScriptRequest):
    """从 script_data 创建 Episode + Storyboard"""
    db = get_database()
    session = db.get_session()
    try:
        episode = script_data_to_episode(
            session=session,
            script_data=req.script_data,
            thread_id=req.thread_id,
            title=req.title,
        )
        return CreateEpisodeResponse(episode_id=episode.id, title=episode.title)
    except Exception as exc:
        logger.error("create_episode_from_script failed: %s", exc)
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    finally:
        session.close()


@router.post("/episodes/storyboards", response_model=GenerateStoryboardResponse)
def generate_storyboard(req: GenerateStoryboardRequest):
    """触发异步分镜生成任务"""
    db = get_database()
    session = db.get_session()
    try:
        try:
            storyboard_service.get_episode_or_raise(session, req.episode_id)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

        task = task_service.create_task(session, "storyboard_generation", str(req.episode_id))
        generate_storyboard_task.delay(task.id, req.episode_id)

        return GenerateStoryboardResponse(
            task_id=task.id,
            status="pending",
            message="分镜生成任务已创建，正在后台处理",
        )
    finally:
        session.close()


@router.post("/episodes/{episode_id}/generate-aigc", response_model=GenerateAigcResponse)
def generate_aigc(episode_id: int):
    """触发 AIGC 图片/视频生成任务（文生图 + 图生视频）"""
    db = get_database()
    session = db.get_session()
    try:
        try:
            storyboard_service.get_episode_or_raise(session, episode_id)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

        task = task_service.create_task(session, "aigc_generation", str(episode_id))
        generate_aigc_task.delay(task.id, episode_id)

        return GenerateAigcResponse(
            task_id=task.id,
            status="pending",
            message="AIGC 生成任务已创建，正在后台处理",
        )
    finally:
        session.close()


@router.put("/episodes/{episode_id}/manual-edits", response_model=SaveManualEditsResponse)
def save_manual_edits(episode_id: int, req: SaveManualEditsRequest):
    """Persist human storyboard edits before AIGC generation."""
    db = get_database()
    session = db.get_session()
    try:
        try:
            result = storyboard_service.save_episode_manual_edits(
                session=session,
                episode_id=episode_id,
                characters=[item.model_dump() for item in req.characters],
                shots=[item.model_dump() for item in req.shots],
            )
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return SaveManualEditsResponse(**result)
    finally:
        session.close()


@router.get("/tasks/{task_id}", response_model=TaskStatusResponse)
def get_task_status(task_id: str):
    """查询异步任务状态"""
    db = get_database()
    session = db.get_session()
    try:
        task = session.get(AsyncTaskDB, task_id)
        if not task:
            raise HTTPException(status_code=404, detail=f"task {task_id} not found")
        return TaskStatusResponse(
            task_id=task.id,
            type=task.type,
            status=task.status,
            progress=task.progress,
            message=task.message,
            result=task.result,
            error=task.error,
        )
    finally:
        session.close()


@router.post("/videos/merge", response_model=VideoMergeResponse)
def merge_videos(req: VideoMergeRequest):
    """提交视频合成任务（异步）"""
    db = get_database()
    session = db.get_session()
    try:
        task = task_service.create_task(session, "video_merge", "video_merge")
        payload = [clip.model_dump() for clip in req.clips]
        merge_episode_videos_task.delay(task.id, payload, req.output_file)

        return VideoMergeResponse(
            task_id=task.id,
            status="pending",
            message="视频合成任务已创建，正在后台处理",
        )
    finally:
        session.close()


@router.post("/videos/merge/precheck", response_model=VideoMergePrecheckResponse)
def precheck_video_merge(req: VideoMergeRequest):
    """同步预检视频合成参数"""
    try:
        clips = []
        for item in req.clips:
            transition = None
            if item.transition:
                transition = TransitionConfig(
                    type=item.transition.type,
                    duration=item.transition.duration,
                )
            clips.append(
                VideoClip(
                    url=item.video_url,
                    duration=item.duration,
                    start_time=item.start_time,
                    end_time=item.end_time,
                    transition=transition,
                )
            )
        result = precheck_merge(clips)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return VideoMergePrecheckResponse(
        clips_count=result.clips_count,
        estimated_output_duration=result.estimated_output_duration,
        target_width=result.target_width,
        target_height=result.target_height,
        has_any_audio=result.has_any_audio,
        clips=[
            {
                "index": d.index,
                "source_url": d.source_url,
                "source_duration": d.source_duration,
                "requested_start": d.requested_start,
                "requested_end": d.requested_end,
                "applied_start": d.applied_start,
                "applied_end": d.applied_end,
                "effective_duration": d.effective_duration,
                "width": d.width,
                "height": d.height,
                "has_audio": d.has_audio,
                "transition_type": d.transition_type,
                "transition_duration": d.transition_duration,
            }
            for d in result.clips
        ],
        warnings=result.warnings,
    )
