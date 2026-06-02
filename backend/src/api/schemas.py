"""API 请求/响应 Pydantic 模型"""

from typing import Any, Optional

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    """健康检查响应"""

    status: str = Field(default="ok")
    version: str = Field(default="0.1.0")


class ChatRequest(BaseModel):
    """对话请求（用于配置下发）"""

    model_config = {"str_strip_whitespace": True}

    user_input: str = Field(
        ...,
        min_length=1,
        description="用户输入的创作需求",
    )
    thread_id: Optional[str] = Field(
        default=None,
        description="会话线程 ID",
    )


class ConfigSubmitRequest(BaseModel):
    """配置表单提交请求"""

    model_config = {"str_strip_whitespace": True}

    thread_id: str = Field(
        ...,
        description="会话线程 ID",
    )
    user_input: str = Field(
        ...,
        min_length=1,
        description="用户原始输入",
    )
    selections: dict[str, str] = Field(
        ...,
        description="用户选择的配置项，如 {'target_duration': '30', 'ratio': '16:9', 'style': 'anime'}",
    )
    reference_novel_title: Optional[str] = Field(
        default=None,
        description="参考小说名称，用于提取 Move 结构",
    )
    target_chapters: int = Field(
        default=1,
        description="目标章节/场景数，默认 1",
    )


# ============================================================================
# 分镜板 API 模型
# ============================================================================


class CreateEpisodeRequest(BaseModel):
    """手动创建剧集"""
    title: str = Field(..., min_length=1, description="剧集标题")
    script_content: str = Field(default="", description="剧本文本内容")


class CreateEpisodeResponse(BaseModel):
    """创建剧集响应"""
    episode_id: int
    title: str


class EpisodeFromScriptRequest(BaseModel):
    """从 script_data 创建 Episode"""
    script_data: dict[str, Any] = Field(..., description="build_script_data() 返回的结构化数据")
    thread_id: str = Field(..., description="会话线程 ID")
    title: Optional[str] = Field(default=None, description="剧集标题（缺省用 script_data.title）")


class GenerateStoryboardRequest(BaseModel):
    """触发异步分镜生成"""
    episode_id: int = Field(..., description="剧集 ID")


class GenerateStoryboardResponse(BaseModel):
    """异步分镜生成响应"""
    task_id: str
    status: str
    message: str


class TaskStatusResponse(BaseModel):
    """异步任务状态"""
    task_id: str
    type: str
    status: str
    progress: int
    message: str
    result: str
    error: str


class GenerateAigcResponse(BaseModel):
    """AIGC 生成任务响应"""
    task_id: str
    status: str
    message: str


class ManualEditCharacter(BaseModel):
    """Character edits from the storyboard review UI."""
    id: str
    name: str = ""
    voice: str = ""
    appearance: str = ""


class ManualEditShot(BaseModel):
    """Storyboard edits from the storyboard review UI."""
    storyboard_number: int = Field(..., ge=1)
    summary: str = ""
    visual_desc: str = ""
    narration: str = ""
    tags: list[str] = Field(default_factory=list)
    duration_seconds: float = Field(default=0.0, ge=0.0)
    start_frame_url: Optional[str] = None
    end_frame_url: Optional[str] = None
    keyframe_urls: list[str] | None = None


class SaveManualEditsRequest(BaseModel):
    """Manual storyboard edits to persist before AIGC execution."""
    characters: list[ManualEditCharacter] = Field(default_factory=list)
    shots: list[ManualEditShot] = Field(default_factory=list)


class SaveManualEditsResponse(BaseModel):
    """Manual storyboard edit persistence result."""
    episode_id: int
    updated_storyboards: int
    updated_characters: int
    status: str
    message: str


class TransitionConfigSchema(BaseModel):
    """转场配置"""
    type: str = Field(default="none", description="转场类型: none/fade/dissolve/wipeleft/wiperight/slideleft/slideright")
    duration: float = Field(default=1.0, ge=0.0, le=5.0, description="转场时长（秒）")


class VideoClipRequest(BaseModel):
    """视频片段"""
    video_url: str = Field(..., description="视频 URL 或本地路径")
    duration: float = Field(default=0.0, ge=0.0)
    start_time: float = Field(default=0.0, ge=0.0)
    end_time: float = Field(default=0.0, ge=0.0)
    transition: Optional[TransitionConfigSchema] = None


class VideoMergeRequest(BaseModel):
    """视频合成请求"""
    clips: list[VideoClipRequest] = Field(..., min_length=1, description="视频片段列表")
    output_file: str = Field(default="outputs/merged_output.mp4", description="输出文件路径")


class VideoMergeResponse(BaseModel):
    """视频合成响应"""
    task_id: str
    status: str
    message: str


class VideoMergePrecheckClipDetail(BaseModel):
    """预检片段详情"""
    index: int
    source_url: str
    source_duration: float
    requested_start: float
    requested_end: float
    applied_start: float
    applied_end: float
    effective_duration: float
    width: int
    height: int
    has_audio: bool
    transition_type: str
    transition_duration: float


class VideoMergePrecheckResponse(BaseModel):
    """视频合成预检响应"""
    clips_count: int
    estimated_output_duration: float
    target_width: int
    target_height: int
    has_any_audio: bool
    clips: list[VideoMergePrecheckClipDetail]
    warnings: list[str]
