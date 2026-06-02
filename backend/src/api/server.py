"""FastAPI 应用实例与配置"""

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from src.api.routes import router
from src.api.storyboard_routes import router as storyboard_router
from src.core.config import settings
from src.core.logger import get_logger

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    logger.info("短剧脚本 Agent API 服务启动")
    logger.info(f"模型: {settings.model_name}")
    yield
    logger.info("短剧脚本 Agent API 服务关闭")


app = FastAPI(
    title="短剧脚本 Agent API",
    description="基于 LangGraph 的短剧脚本生成、分镜审核与 AIGC 工作流 API",
    version="0.1.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# 前端静态文件（最小 UI）
PROJECT_ROOT = Path(__file__).resolve().parents[2]
FRONT_DIR = PROJECT_ROOT / "fronter"
if FRONT_DIR.exists():
    app.mount(
        "/fronter",
        StaticFiles(directory=str(FRONT_DIR), html=True),
        name="fronter",
    )

# CORS 配置
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册路由
app.include_router(router, prefix="/api/v1")
app.include_router(storyboard_router, prefix="/api/v1/storyboard")


@app.get("/", include_in_schema=False)
async def root():
    """根路径：跳转到静态前端（/fronter/）"""
    index_file = FRONT_DIR / "index.html"
    if index_file.exists():
        return RedirectResponse(url="/fronter/", status_code=302)
    return {
        "name": "短剧脚本 Agent API",
        "version": "0.1.0",
        "docs": "/docs",
        "hint": "前端目录缺失：请先将前端 build 产物复制到项目根目录的 fronter/（需要包含 index.html 与 assets/）",
    }
