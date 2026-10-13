"""API token 用量审计（成本分析、用量趋势）。"""

from __future__ import annotations

from sqlalchemy import Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from ..core.db import Base
from ._common import TimestampMixin


class TokenUsage(Base, TimestampMixin):
    """每次 LLM 调用的详细用量记录。"""

    __tablename__ = "token_usage"

    id: Mapped[int] = mapped_column(primary_key=True)
    grading_result_id: Mapped[int | None] = mapped_column(
        ForeignKey("grading_result.id", ondelete="CASCADE"), index=True
    )
    model_key: Mapped[str] = mapped_column(String(64), index=True)
    phase: Mapped[str] = mapped_column(String(32), default="")  # 'rubric_batch' / 'summary'
    prompt_tokens: Mapped[int] = mapped_column(Integer, default=0)
    completion_tokens: Mapped[int] = mapped_column(Integer, default=0)
    total_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    elapsed_seconds: Mapped[float] = mapped_column(Float, default=0.0)
