"""聊天会话与消息（Part 2 学生端对话式交互）。"""

from __future__ import annotations

from typing import Any

from sqlalchemy import Boolean, Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..core.db import Base
from ._common import TimestampMixin


class ChatSession(Base, TimestampMixin):
    """一次完整的作业对话会话（学生 × 图类型 × 题号）。"""

    __tablename__ = "chat_session"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("app_user.id", ondelete="CASCADE"), index=True,
    )
    # 实验分组快照（冗余，防 user 表改后对不上）
    experiment_group: Mapped[str] = mapped_column(String(32), default="control")
    diagram_type: Mapped[str] = mapped_column(String(32), index=True)
    problem_code: Mapped[str] = mapped_column(String(64), default="")
    problem_statement: Mapped[str] = mapped_column(String(4000), default="")

    # 会话状态: active | completed | abandoned
    status: Mapped[str] = mapped_column(String(32), default="active")
    # 当前轮次（Agent B/C 多轮时递增）
    round_number: Mapped[int] = mapped_column(Integer, default=0)
    # 最新一次评分（0-100）
    latest_score: Mapped[float | None] = mapped_column(Float, nullable=True, default=None)
    # 是否已通过（Agent B/C 的结束条件）
    passed: Mapped[bool] = mapped_column(Boolean, default=False)

    # 学生在本会话中累计活跃秒数（由心跳或回填更新）
    total_active_seconds: Mapped[int] = mapped_column(Integer, default=0)

    # 最新 mdj 文件在 MinIO 的 object_key
    latest_mdj_key: Mapped[str] = mapped_column(String(512), default="")
    # 最新 mdj 解析后的 IR（JSON）
    latest_ir_data: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    latest_ir_textual: Mapped[str] = mapped_column(Text, default="")

    messages = relationship(
        "ChatMessage", back_populates="session",
        cascade="all, delete-orphan", order_by="ChatMessage.id",
    )
    teacher_scores = relationship(
        "ChatTeacherScore", back_populates="session",
        cascade="all, delete-orphan",
    )


class ChatMessage(Base, TimestampMixin):
    """聊天消息（用户消息 / Agent 回复）。"""

    __tablename__ = "chat_message"

    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[int] = mapped_column(
        ForeignKey("chat_session.id", ondelete="CASCADE"), index=True,
    )
    # 'user' | 'assistant' | 'system'
    role: Mapped[str] = mapped_column(String(16))
    content: Mapped[str] = mapped_column(Text, default="")

    # 附件: mdj 文件的 MinIO key
    mdj_object_key: Mapped[str | None] = mapped_column(String(512), nullable=True, default=None)
    mdj_filename: Mapped[str | None] = mapped_column(String(255), nullable=True, default=None)
    # 附件: 图片的 MinIO key（仅存储，不解析）
    image_object_key: Mapped[str | None] = mapped_column(String(512), nullable=True, default=None)
    image_filename: Mapped[str | None] = mapped_column(String(255), nullable=True, default=None)

    # Agent 回复时的评分快照
    score_snapshot: Mapped[float | None] = mapped_column(Float, nullable=True, default=None)
    # 用于追踪 token 消耗
    prompt_tokens: Mapped[int] = mapped_column(Integer, default=0)
    completion_tokens: Mapped[int] = mapped_column(Integer, default=0)

    session = relationship("ChatSession", back_populates="messages")
    criterion_scores = relationship(
        "ChatCriterionScore", back_populates="message",
        cascade="all, delete-orphan",
    )
    model_results = relationship(
        "ChatModelResult", back_populates="message",
        cascade="all, delete-orphan",
    )


class ChatCriterionScore(Base, TimestampMixin):
    """Agent 对话中产出的逐条指标结构化评分（关联到 assistant 消息）。"""

    __tablename__ = "chat_criterion_score"

    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[int] = mapped_column(
        ForeignKey("chat_session.id", ondelete="CASCADE"), index=True,
    )
    message_id: Mapped[int] = mapped_column(
        ForeignKey("chat_message.id", ondelete="CASCADE"), index=True,
    )
    code: Mapped[str] = mapped_column(String(16), index=True)  # e.g. 'UC1.1'
    score: Mapped[float] = mapped_column(Float, default=0.0)   # 0.0~1.0
    max_score: Mapped[float] = mapped_column(Float, default=1.0)
    not_applicable: Mapped[bool] = mapped_column(Boolean, default=False)
    has_issue: Mapped[bool] = mapped_column(Boolean, default=False)
    brief: Mapped[str] = mapped_column(String(500), default="")  # 简短说明

    message = relationship("ChatMessage", back_populates="criterion_scores")


class ChatModelResult(Base, TimestampMixin):
    __tablename__ = "chat_model_result"

    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[int] = mapped_column(
        ForeignKey("chat_session.id", ondelete="CASCADE"), index=True,
    )
    message_id: Mapped[int] = mapped_column(
        ForeignKey("chat_message.id", ondelete="CASCADE"), index=True,
    )
    model_key: Mapped[str] = mapped_column(String(64), index=True)
    status: Mapped[str] = mapped_column(String(32), default="success", index=True)
    total_score: Mapped[float | None] = mapped_column(Float, nullable=True, default=None)
    max_total_score: Mapped[float] = mapped_column(Float, default=100.0)
    normalized_score: Mapped[float | None] = mapped_column(Float, nullable=True, default=None)
    overall_comment: Mapped[str] = mapped_column(Text, default="")
    raw_response: Mapped[str] = mapped_column(Text, default="")
    error: Mapped[str] = mapped_column(String(2000), default="")
    prompt_tokens: Mapped[int] = mapped_column(Integer, default=0)
    completion_tokens: Mapped[int] = mapped_column(Integer, default=0)
    elapsed_seconds: Mapped[float] = mapped_column(Float, default=0.0)

    message = relationship("ChatMessage", back_populates="model_results")
    criterion_scores = relationship(
        "ChatModelCriterionScore", back_populates="model_result",
        cascade="all, delete-orphan",
    )


class ChatModelCriterionScore(Base, TimestampMixin):
    __tablename__ = "chat_model_criterion_score"

    id: Mapped[int] = mapped_column(primary_key=True)
    model_result_id: Mapped[int] = mapped_column(
        ForeignKey("chat_model_result.id", ondelete="CASCADE"), index=True,
    )
    code: Mapped[str] = mapped_column(String(16), index=True)
    score: Mapped[float] = mapped_column(Float, default=0.0)
    max_score: Mapped[float] = mapped_column(Float, default=1.0)
    not_applicable: Mapped[bool] = mapped_column(Boolean, default=False)
    has_issue: Mapped[bool] = mapped_column(Boolean, default=False)
    brief: Mapped[str] = mapped_column(String(500), default="")
    reasoning: Mapped[str] = mapped_column(Text, default="")

    model_result = relationship("ChatModelResult", back_populates="criterion_scores")
