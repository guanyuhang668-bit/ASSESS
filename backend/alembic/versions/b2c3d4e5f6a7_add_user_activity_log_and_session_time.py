"""add user_activity_log table and chat_session.total_active_seconds

Revision ID: b2c3d4e5f6a7
Revises: c3e5b977516a
Create Date: 2026-05-26 22:30:00.000000
"""
from __future__ import annotations

from typing import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


revision: str = "b2c3d4e5f6a7"
down_revision: str | None = "c3e5b977516a"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. 新建 user_activity_log 表
    op.create_table(
        "user_activity_log",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("app_user.id", ondelete="CASCADE"), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("duration_seconds", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("chat_session_id", sa.Integer(), sa.ForeignKey("chat_session.id", ondelete="SET NULL"), nullable=True),
        sa.Column("context", JSONB(), nullable=False, server_default="{}"),
        sa.Column("source", sa.String(16), nullable=False, server_default="heartbeat"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_user_activity_log_user_id", "user_activity_log", ["user_id"])
    op.create_index("ix_user_activity_log_started_at", "user_activity_log", ["started_at"])
    op.create_index("ix_user_activity_log_ended_at", "user_activity_log", ["ended_at"])
    op.create_index("ix_user_activity_log_chat_session_id", "user_activity_log", ["chat_session_id"])
    op.create_index("ix_user_activity_log_source", "user_activity_log", ["source"])

    # 2. 给 chat_session 添加 total_active_seconds 列
    op.add_column(
        "chat_session",
        sa.Column("total_active_seconds", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("chat_session", "total_active_seconds")
    op.drop_table("user_activity_log")
