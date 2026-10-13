"""add session_group to app_user

Revision ID: a1b2c3d4e5f6
Revises: ef4e6a528ae4
Create Date: 2026-05-19 13:00:00.000000
"""
from __future__ import annotations

from typing import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "a1b2c3d4e5f6"
down_revision: str | None = "ef4e6a528ae4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "app_user",
        sa.Column("session_group", sa.String(length=32), nullable=True),
    )
    op.create_index(
        op.f("ix_app_user_session_group"),
        "app_user",
        ["session_group"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_app_user_session_group"), table_name="app_user")
    op.drop_column("app_user", "session_group")
