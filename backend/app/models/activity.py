"""学生使用时长追踪（心跳汇聚 + 历史回填）。"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from ..core.db import Base
from ._common import TimestampMixin


class UserActivityLog(Base, TimestampMixin):
    """一段连续使用时间块（心跳合并产生 或 历史回填推算）。"""

    __tablename__ = "user_activity_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("app_user.id", ondelete="CASCADE"), index=True,
    )
    # 使用块的开始/结束时间
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), index=True, server_default=func.now(),
    )
    ended_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), index=True, server_default=func.now(),
    )
    # 持续秒数（冗余，方便聚合查询）
    duration_seconds: Mapped[int] = mapped_column(Integer, default=0)

    # 关联的 ChatSession ID（可选，做会话级分析用）
    chat_session_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("chat_session.id", ondelete="SET NULL"),
        nullable=True, default=None, index=True,
    )

    # 上下文信息: page, diagram_type 等
    context: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)

    # 数据来源: 'heartbeat'(实时上报) | 'reconstructed'(历史回填)
    source: Mapped[str] = mapped_column(String(16), default="heartbeat", index=True)
