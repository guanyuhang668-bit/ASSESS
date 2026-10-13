"""批改任务 / 结果 / 指标分数 / 缺陷。"""

from __future__ import annotations

import enum
from datetime import datetime
from typing import Any

from sqlalchemy import (
    DateTime, Enum, Float, ForeignKey, Integer, String, UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..core.db import Base
from ._common import TimestampMixin


class GradingRunStatus(str, enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class GradingResultStatus(str, enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"


class GradingRun(Base, TimestampMixin):
    """一次批改任务：一次性为 M 份 submission × N 个模型批改。"""

    __tablename__ = "grading_run"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(128))
    description: Mapped[str] = mapped_column(String(1000), default="")
    created_by: Mapped[int | None] = mapped_column(
        ForeignKey("app_user.id", ondelete="SET NULL")
    )

    rubric_version_ids: Mapped[list[int]] = mapped_column(
        ARRAY(Integer), default=list, nullable=False
    )
    # 本次使用哪些 rubric version（一般一张图用一个）
    model_keys: Mapped[list[str]] = mapped_column(
        ARRAY(String(64)), default=list, nullable=False
    )
    # 本次批改使用哪些模型：['gpt4o_mini','claude_opus_47','deepseek_v4','qwen_max']
    submission_ids: Mapped[list[int]] = mapped_column(
        ARRAY(Integer), default=list, nullable=False
    )
    # 本次批改涉及的 submission id 列表

    status: Mapped[GradingRunStatus] = mapped_column(
        Enum(GradingRunStatus, name="grading_run_status"),
        default=GradingRunStatus.PENDING,
        index=True,
    )
    total_tasks: Mapped[int] = mapped_column(Integer, default=0)
    completed_tasks: Mapped[int] = mapped_column(Integer, default=0)
    failed_tasks: Mapped[int] = mapped_column(Integer, default=0)

    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error: Mapped[str] = mapped_column(String(2000), default="")

    results = relationship(
        "GradingResult", back_populates="run", cascade="all, delete-orphan"
    )


class GradingResult(Base, TimestampMixin):
    """一次 (submission × model) 批改结果。"""

    __tablename__ = "grading_result"
    __table_args__ = (
        UniqueConstraint(
            "run_id", "submission_id", "model_key",
            name="uq_result_run_sub_model",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(
        ForeignKey("grading_run.id", ondelete="CASCADE"), index=True
    )
    submission_id: Mapped[int] = mapped_column(
        ForeignKey("submission.id", ondelete="CASCADE"), index=True
    )
    rubric_version_id: Mapped[int] = mapped_column(
        ForeignKey("rubric_version.id", ondelete="RESTRICT"), index=True
    )
    model_key: Mapped[str] = mapped_column(String(64), index=True)

    status: Mapped[GradingResultStatus] = mapped_column(
        Enum(GradingResultStatus, name="grading_result_status"),
        default=GradingResultStatus.PENDING,
        index=True,
    )
    total_score: Mapped[float] = mapped_column(Float, default=0.0)
    max_total_score: Mapped[float] = mapped_column(Float, default=0.0)
    normalized_score: Mapped[float] = mapped_column(Float, default=0.0)  # 0-100
    overall_comment: Mapped[str] = mapped_column(String(4000), default="")

    raw_response: Mapped[str] = mapped_column(String, default="")
    prompt_tokens: Mapped[int] = mapped_column(Integer, default=0)
    completion_tokens: Mapped[int] = mapped_column(Integer, default=0)
    elapsed_seconds: Mapped[float] = mapped_column(Float, default=0.0)

    error: Mapped[str] = mapped_column(String(2000), default="")
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    run = relationship("GradingRun", back_populates="results")
    submission = relationship("Submission", back_populates="grading_results")
    criterion_scores = relationship(
        "CriterionScore", back_populates="grading_result",
        cascade="all, delete-orphan",
    )


class CriterionScore(Base, TimestampMixin):
    """对某条指标（如 UC1.1）的评分。"""

    __tablename__ = "criterion_score"
    __table_args__ = (
        UniqueConstraint(
            "grading_result_id", "code", name="uq_critscore_result_code",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    grading_result_id: Mapped[int] = mapped_column(
        ForeignKey("grading_result.id", ondelete="CASCADE"), index=True
    )
    code: Mapped[str] = mapped_column(String(16), index=True)
    score: Mapped[float] = mapped_column(Float, default=0.0)      # 0-1
    max_score: Mapped[float] = mapped_column(Float, default=1.0)
    not_applicable: Mapped[bool] = mapped_column(default=False)
    reasoning: Mapped[str] = mapped_column(String, default="")

    grading_result = relationship("GradingResult", back_populates="criterion_scores")
    issues = relationship(
        "Issue", back_populates="criterion_score", cascade="all, delete-orphan",
    )


class Issue(Base, TimestampMixin):
    """单条缺陷。"""

    __tablename__ = "issue"

    id: Mapped[int] = mapped_column(primary_key=True)
    criterion_score_id: Mapped[int] = mapped_column(
        ForeignKey("criterion_score.id", ondelete="CASCADE"), index=True
    )
    element_refs: Mapped[list[str]] = mapped_column(
        ARRAY(String(64)), default=list, nullable=False
    )
    description: Mapped[str] = mapped_column(String(2000))
    severity: Mapped[str] = mapped_column(String(16), default="minor")
    # 'minor' | 'major' | 'critical'
    suggestion: Mapped[str] = mapped_column(String(2000), default="")

    criterion_score = relationship("CriterionScore", back_populates="issues")
