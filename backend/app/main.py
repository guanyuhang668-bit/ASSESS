"""FastAPI 应用入口。"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .api import router as api_router
from .core.config import get_settings
from .core.db import dispose_engine, init_db
from .services.llm.factory import get_llm_pool


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    logger.info("starting %s (env=%s)", settings.app_name, settings.app_env)

    # 安全检查：生产环境禁止使用默认 JWT secret
    if settings.app_env != "development" and settings.jwt_secret == "dev-secret-change-me":
        raise RuntimeError(
            "生产环境必须设置 JWT_SECRET 环境变量，当前使用默认值不安全！"
        )
    # 开发期自动建表（生产请用 alembic）
    if settings.auto_create_tables:
        try:
            await init_db()
            logger.info("auto-created tables via SQLAlchemy metadata")
        except Exception as e:  # noqa: BLE001
            logger.warning("init_db failed: %s", e)
    # 预加载 LLM 池，失败不阻塞启动
    try:
        pool = await get_llm_pool()
        logger.info("LLM pool: %s", list(pool.keys()))
    except Exception as e:  # noqa: BLE001
        logger.warning("LLM pool init failed: %s", e)
    # MinIO 使用懒初始化，首次上传时才连接，避免启动阻塞
    yield
    await dispose_engine()


def create_app() -> FastAPI:
    settings = get_settings()
    is_dev = settings.app_env == "development"
    app = FastAPI(
        title=settings.app_name,
        version="0.2.0",
        lifespan=lifespan,
        docs_url="/docs" if is_dev else None,
        redoc_url="/redoc" if is_dev else None,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(api_router, prefix=settings.api_prefix)

    # 静态文件：上传的图片
    settings.uploads_dir.mkdir(parents=True, exist_ok=True)
    app.mount("/uploads", StaticFiles(directory=str(settings.uploads_dir)), name="uploads")

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    return app


app = create_app()
