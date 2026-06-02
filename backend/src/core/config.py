"""环境变量与配置管理模块"""

import os
from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """应用配置类 - 从环境变量加载"""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
        env_file_dir=os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))), ""),
    )

    # LLM 提供商选择：dashscope | openai
    llm_provider: str = Field(
        default="dashscope",
        description="LLM 提供商: dashscope (通义千问) 或 openai",
    )

    # 通义千问配置
    dashscope_api_key: str = Field(
        default="", description="DashScope API Key"
    )
    dashscope_base_url: str = Field(
        default="", description="DashScope Base URL（如区域不同可自定义，默认 https://dashscope.aliyuncs.com）"
    )

    # OpenAI 配置
    openai_api_key: str = Field(
        default="", description="OpenAI API Key"
    )
    openai_base_url: str = Field(
        default="", description="OpenAI Base URL（可选，用于代理或兼容 API）"
    )

    # 模型配置（通用）
    model_name: str = Field(
        default="qwen-plus", description="模型名称（dashscope: qwen-plus / openai: gpt-4o-mini 等）"
    )
    model_temperature: float = Field(
        default=0.7, description="模型温度"
    )

    # 日志配置
    log_level: str = Field(default="INFO", description="日志级别")
    log_file_path: str = Field(
        default="logs/app.log", description="日志文件路径"
    )

    # API 配置
    api_host: str = Field(default="0.0.0.0", description="API 主机")
    api_port: int = Field(default=8000, description="API 端口")

    # Agent 配置
    max_iterations: int = Field(
        default=3, description="最大迭代次数"
    )

    # Move planner（动态步骤规划）
    enable_move_planner: bool = Field(
        default=True,
        description="是否启用 move_planner（让 LLM 动态选择/排序/融合 moves；关闭则使用固定裁剪）",
    )

    # 调试开关（开发环境建议开启，生产环境关闭）
    debug_node_io: bool = Field(
        default=False,
        description="是否打印节点输入/输出（开发用，生产建议关闭）",
    )
    debug_llm_io: bool = Field(
        default=False,
        description="是否打印 LLM 输入/输出原文（开发用，生产建议关闭）",
    )

    # ScriptView 结构化抽取（script_data）
    script_data_llm_enabled: bool = Field(
        default=True,
        description="是否启用 LLM 进行 ScriptView 信息抽取（角色/场景/道具/分镜），失败时自动回退规则抽取",
    )

    # 检索配置
    enable_retrieval: bool = Field(
        default=True, description="是否启用 hybrid-search 语义检索"
    )
    qdrant_host: str = Field(default="localhost", description="Qdrant 主机")
    qdrant_port: int = Field(default=6333, description="Qdrant 端口")
    qdrant_collection: str = Field(
        default="novel_nodes_hybrid", description="Qdrant 集合名称"
    )
    mongodb_uri: str = Field(
        default="mongodb://admin:susie2026@localhost:27017",
        description="MongoDB 连接 URI",
    )
    mongodb_database: str = Field(
        default="novels", description="MongoDB 数据库名称"
    )
    retrieval_top_k: int = Field(
        default=3, description="检索返回结果数量"
    )
    retrieval_use_rerank: bool = Field(
        default=False, description="是否使用 Rerank 重排序（需要下载 BAAI/bge-reranker-base 模型）"
    )
    retrieval_rerank_gap: float = Field(
        default=5.0, description="Rerank 分数差距阈值：与最佳结果差距超过此值的结果被裁掉"
    )

    # External enrichment tools
    enable_external_content_tools: bool = Field(
        default=True,
        description="是否启用外部内容增强工具（Web Search / Douyin Trends）",
    )
    external_enrichment_min_results: int = Field(
        default=1,
        description="内部 RAG 结果少于该数量时触发外部内容增强",
    )
    web_search_api_url: str = Field(
        default="",
        description="Web Search 供应商 API URL；为空时使用占位工具结果",
    )
    douyin_trend_api_url: str = Field(
        default="",
        description="抖音热榜供应商 API URL；为空时使用占位工具结果",
    )

    # AIGC 模型（通义万相）
    aigc_image_model: str = Field(
        default="wanx2.1-t2i-turbo", description="文生图模型 ID"
    )
    aigc_image_size: str = Field(
        default="1280*720", description="文生图输出尺寸"
    )
    aigc_video_model: str = Field(
        default="wanx2.1-i2v-plus", description="图生视频模型 ID"
    )
    aigc_video_poll_interval: int = Field(
        default=15, description="图生视频轮询间隔（秒）"
    )
    aigc_video_max_wait: int = Field(
        default=600, description="图生视频最大等待时间（秒）"
    )

    # Redis / Celery
    redis_url: str = Field(
        default="redis://localhost:6379/0", description="Redis URL（Celery broker/backend）"
    )
    celery_task_always_eager: bool = Field(
        default=False, description="Celery 同步模式（测试用）"
    )

    def ensure_api_keys_env(self) -> None:
        """确保 API Key 在环境变量中（LangChain 自动读取）"""
        # DashScope
        if not os.getenv("DASHSCOPE_API_KEY") and self.dashscope_api_key:
            os.environ["DASHSCOPE_API_KEY"] = self.dashscope_api_key
        # OpenAI
        if not os.getenv("OPENAI_API_KEY") and self.openai_api_key:
            os.environ["OPENAI_API_KEY"] = self.openai_api_key
        if not os.getenv("OPENAI_BASE_URL") and self.openai_base_url:
            os.environ["OPENAI_BASE_URL"] = self.openai_base_url


@lru_cache
def get_settings() -> Settings:
    """获取配置单例"""
    return Settings()


def load_settings() -> Settings:
    """加载配置并确保环境变量设置"""
    settings = get_settings()
    settings.ensure_api_keys_env()
    return settings


# 模块级别的 settings 实例
settings = load_settings()
