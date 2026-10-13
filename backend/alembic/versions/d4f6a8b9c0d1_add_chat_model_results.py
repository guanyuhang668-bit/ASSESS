"""add chat model results

Revision ID: d4f6a8b9c0d1
Revises: b2c3d4e5f6a7
Create Date: 2026-05-26 23:40:00.000000
"""
from __future__ import annotations

from typing import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "d4f6a8b9c0d1"
down_revision: str | None = "b2c3d4e5f6a7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "chat_model_result",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("session_id", sa.Integer(), nullable=False),
        sa.Column("message_id", sa.Integer(), nullable=False),
        sa.Column("model_key", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("total_score", sa.Float(), nullable=True),
        sa.Column("max_total_score", sa.Float(), nullable=False),
        sa.Column("normalized_score", sa.Float(), nullable=True),
        sa.Column("overall_comment", sa.Text(), nullable=False),
        sa.Column("raw_response", sa.Text(), nullable=False),
        sa.Column("error", sa.String(length=2000), nullable=False),
        sa.Column("prompt_tokens", sa.Integer(), nullable=False),
        sa.Column("completion_tokens", sa.Integer(), nullable=False),
        sa.Column("elapsed_seconds", sa.Float(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["message_id"], ["chat_message.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["session_id"], ["chat_session.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_chat_model_result_message_id"), "chat_model_result", ["message_id"], unique=False)
    op.create_index(op.f("ix_chat_model_result_model_key"), "chat_model_result", ["model_key"], unique=False)
    op.create_index(op.f("ix_chat_model_result_session_id"), "chat_model_result", ["session_id"], unique=False)
    op.create_index(op.f("ix_chat_model_result_status"), "chat_model_result", ["status"], unique=False)

    op.create_table(
        "chat_model_criterion_score",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("model_result_id", sa.Integer(), nullable=False),
        sa.Column("code", sa.String(length=16), nullable=False),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("max_score", sa.Float(), nullable=False),
        sa.Column("not_applicable", sa.Boolean(), nullable=False),
        sa.Column("has_issue", sa.Boolean(), nullable=False),
        sa.Column("brief", sa.String(length=500), nullable=False),
        sa.Column("reasoning", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["model_result_id"], ["chat_model_result.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_chat_model_criterion_score_code"), "chat_model_criterion_score", ["code"], unique=False)
    op.create_index(op.f("ix_chat_model_criterion_score_model_result_id"), "chat_model_criterion_score", ["model_result_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_chat_model_criterion_score_model_result_id"), table_name="chat_model_criterion_score")
    op.drop_index(op.f("ix_chat_model_criterion_score_code"), table_name="chat_model_criterion_score")
    op.drop_table("chat_model_criterion_score")
    op.drop_index(op.f("ix_chat_model_result_status"), table_name="chat_model_result")
    op.drop_index(op.f("ix_chat_model_result_session_id"), table_name="chat_model_result")
    op.drop_index(op.f("ix_chat_model_result_model_key"), table_name="chat_model_result")
    op.drop_index(op.f("ix_chat_model_result_message_id"), table_name="chat_model_result")
    op.drop_table("chat_model_result")
