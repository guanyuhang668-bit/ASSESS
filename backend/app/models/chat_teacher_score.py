"""教师对聊天会话的逐条指标评分（金标）。"""

from __future__ import annotations

from sqlalchemy import Boolean, Float, ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..core.db import Base
from ._common import TimestampMixin


class ChatTeacherScore(Base, TimestampMixin):
    """教师对某个聊天会话中某条指标的评分。"""

    __tablename__ = "chat_teacher_score"
    __table_args__ = (
        UniqueConstraint(
            "session_id", "code", "teacher_id",
            name="uq_chat_teacher_score_sess_code_teacher",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[int] = mapped_column(
        ForeignKey("chat_session.id", ondelete="CASCADE"), index=True
    )
    teacher_id: Mapped[int] = mapped_column(
        ForeignKey("app_user.id", ondelete="SET NULL"), index=True
    )
    code: Mapped[str] = mapped_column(String(16), index=True)
    score: Mapped[float] = mapped_column(Float, default=0.0)       # 0-1
    max_score: Mapped[float] = mapped_column(Float, default=1.0)
    not_applicable: Mapped[bool] = mapped_column(Boolean, default=False)
    comment: Mapped[str] = mapped_column(String(2000), default="")

    session = relationship("ChatSession", back_populates="teacher_scores")
    issues = relationship(
        "ChatTeacherIssue", back_populates="chat_teacher_score",
        cascade="all, delete-orphan",
    )


class ChatTeacherIssue(Base, TimestampMixin):
    """教师对聊天会话中标注的缺陷。"""

    __tablename__ = "chat_teacher_issue"

    id: Mapped[int] = mapped_column(primary_key=True)
    chat_teacher_score_id: Mapped[int] = mapped_column(
        ForeignKey("chat_teacher_score.id", ondelete="CASCADE"), index=True
    )
    element_refs: Mapped[list[str]] = mapped_column(
        ARRAY(String(64)), default=list, nullable=False
    )
    description: Mapped[str] = mapped_column(String(2000))
    severity: Mapped[str] = mapped_column(String(16), default="minor")

    chat_teacher_score = relationship("ChatTeacherScore", back_populates="issues")
