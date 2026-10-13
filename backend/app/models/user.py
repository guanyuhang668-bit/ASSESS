"""用户表（教师 / 研究员）。"""

from __future__ import annotations

from sqlalchemy import Boolean, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from ..core.db import Base
from ._common import TimestampMixin


class AppUser(Base, TimestampMixin):
    __tablename__ = "app_user"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(128), default="")
    hashed_password: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(32), default="researcher")
    # 可选角色: 'student' | 'researcher' | 'teacher' | 'admin'
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    class_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("school_class.id", ondelete="SET NULL"), nullable=True, default=None,
    )
    # Part 2 实验分组: 'agent_a' | 'agent_b' | 'agent_c' | 'control' | NULL
    experiment_group: Mapped[str | None] = mapped_column(
        String(32), nullable=True, default=None, index=True,
    )
    # C 组编号: 'C1' ~ 'C16' | NULL
    cohort_group: Mapped[str | None] = mapped_column(
        String(8), nullable=True, default=None, index=True,
    )
    # 题目顺序: 'normal' | 'reversed' | NULL
    problem_order: Mapped[str | None] = mapped_column(
        String(16), nullable=True, default=None,
    )
    # 当次实验使用的 Agent 分组（独立于历史 experiment_group，用于本次/后续实验灵活切换）
    # 'agent_a' | 'agent_b' | 'agent_c' | 'control' | NULL
    session_group: Mapped[str | None] = mapped_column(
        String(32), nullable=True, default=None, index=True,
    )
