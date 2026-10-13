"""集中式配置。通过 pydantic-settings 从环境变量 / .env 读取。"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict


BACKEND_ROOT = Path(__file__).resolve().parent.parent.parent  # backend/
PROJECT_ROOT = BACKEND_ROOT.parent                             # uml-grader/


class Settings(BaseSettings):
    """应用全局配置。"""

    model_config = SettingsConfigDict(
        env_file=str(BACKEND_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ---- App ----
    app_name: str = "UML Grader"
    app_env: str = Field(default="development", description="development / production")
    debug: bool = True
    api_prefix: str = "/api"
    auto_create_tables: bool = Field(
        default=False,
        description="开发期启动时用 SQLAlchemy create_all 自动建表（代替 alembic）。",
    )
    cors_origins: list[str] = Field(
        default_factory=lambda: ["http://localhost:5173", "http://localhost:3000"]
    )

    # ---- Database ----
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_user: str = "uml_grader"
    postgres_password: str = "uml_grader"
    postgres_db: str = "uml_grader"
    db_pool_size: int = 10
    db_max_overflow: int = 10

    @computed_field  # type: ignore[misc]
    @property
    def database_url(self) -> str:
        """async SQLAlchemy 使用的连接串。"""
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @computed_field  # type: ignore[misc]
    @property
    def sync_database_url(self) -> str:
        """Alembic 使用的 sync 连接串。"""
        return (
            f"postgresql+psycopg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    # ---- Redis / ARQ ----
    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_db: int = 0

    @computed_field  # type: ignore[misc]
    @property
    def redis_url(self) -> str:
        return f"redis://{self.redis_host}:{self.redis_port}/{self.redis_db}"

    # ---- Auth ----
    jwt_secret: str = Field(
        default="dev-secret-change-me",
        description="JWT 签名密钥；生产环境必须改",
    )
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60 * 24

    # ---- Paths ----
    configs_dir: Path = Field(default_factory=lambda: BACKEND_ROOT / "configs")

    @computed_field  # type: ignore[misc]
    @property
    def uploads_dir(self) -> Path:
        p = BACKEND_ROOT / "uploads"
        p.mkdir(parents=True, exist_ok=True)
        return p

    @computed_field  # type: ignore[misc]
    @property
    def rubrics_dir(self) -> Path:
        return self.configs_dir / "rubrics"

    @computed_field  # type: ignore[misc]
    @property
    def models_yaml(self) -> Path:
        return self.configs_dir / "models.yaml"

    @computed_field  # type: ignore[misc]
    @property
    def prompts_dir(self) -> Path:
        return self.configs_dir / "prompts"

    # ---- MinIO 对象存储 ----
    minio_endpoint: str = "localhost:9000"
    minio_access_key: str = "minioadmin"
    minio_secret_key: str = "minioadmin"
    minio_bucket: str = "uml-grader"
    minio_secure: bool = False

    # ---- LLM API keys (从环境变量读) ----
    openai_api_key: str | None = None
    anthropic_api_key: str | None = None
    deepseek_api_key: str | None = None
    dashscope_api_key: str | None = None
    gemini_api_key: str | None = None
    qwen3_api_key: str | None = None

    # ---- 并发参数 ----
    llm_concurrency_default: int = 5
    llm_concurrency_per_model: dict[str, int] = Field(
        default_factory=lambda: {
            "gpt4o": 5,
            "deepseek_v3": 80,   # 5 keys round-robin，每 key 16 并发
            "gemini_3_flash": 10,
        }
    )

    # ARQ 子任务并发（单 worker）
    worker_max_jobs: int = 20
    multi_model_request_concurrency: int = 3
    upload_io_threads: int = 16


@lru_cache
def get_settings() -> Settings:
    """在整个应用生命周期内单例。"""
    return Settings()
