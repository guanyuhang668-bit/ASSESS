"""教师评分（金标），用于与 Agent 对齐。"""

from __future__ import annotations

from sqlalchemy import Boolean, Float, ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..core.db import Base
from ._common import TimestampMixin


class TeacherScore(Base, TimestampMixin):
    """教师对某条指标的评分。"""

    __tablename__ = "teacher_score"
    __table_args__ = (
        UniqueConstraint(
            "submission_id", "code", "teacher_id",
            name="uq_teacher_score_sub_code_teacher",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    submission_id: Mapped[int] = mapped_column(
        ForeignKey("submission.id", ondelete="CASCADE"), index=True
    )
    teacher_id: Mapped[int] = mapped_column(
        ForeignKey("app_user.id", ondelete="SET NULL"), index=True
    )
    code: Mapped[str] = mapped_column(String(16), index=True)
    score: Mapped[float] = mapped_column(Float, default=0.0)       # 0-1
    max_score: Mapped[float] = mapped_column(Float, default=1.0)
    not_applicable: Mapped[bool] = mapped_column(Boolean, default=False)
    comment: Mapped[str] = mapped_column(String(2000), default="")

    submission = relationship("Submission", back_populates="teacher_scores")
    issues = relationship(
        "TeacherIssue", back_populates="teacher_score", cascade="all, delete-orphan",
    )


class TeacherIssue(Base, TimestampMixin):
    """教师标注的缺陷（用于与 Agent issue 做 P/R/F1 对齐）。"""

    __tablename__ = "teacher_issue"

    id: Mapped[int] = mapped_column(primary_key=True)
    teacher_score_id: Mapped[int] = mapped_column(
        ForeignKey("teacher_score.id", ondelete="CASCADE"), index=True
    )
    element_refs: Mapped[list[str]] = mapped_column(
        ARRAY(String(64)), default=list, nullable=False
    )
    description: Mapped[str] = mapped_column(String(2000))
    severity: Mapped[str] = mapped_column(String(16), default="minor")

    teacher_score = relationship("TeacherScore", back_populates="issues")
