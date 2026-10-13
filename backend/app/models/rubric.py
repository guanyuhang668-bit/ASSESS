"""评分指标体系（支持多版本迭代）。"""

from __future__ import annotations

from typing import Any

from sqlalchemy import Boolean, Float, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..core.db import Base
from ._common import TimestampMixin


class RubricVersion(Base, TimestampMixin):
    """一次评分标准定稿（如 'v1-教研会5/17'），支持版本迭代。"""

    __tablename__ = "rubric_version"
    __table_args__ = (
        UniqueConstraint("diagram_type", "name", name="uq_rubric_type_name"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    diagram_type: Mapped[str] = mapped_column(String(32), index=True)
    # 'use_case' | 'class' | 'sequence' | 'swimlane'
    name: Mapped[str] = mapped_column(String(64))
    source_file: Mapped[str] = mapped_column(String(255), default="")
    is_active: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    description: Mapped[str] = mapped_column(String(500), default="")

    criteria = relationship(
        "RubricCriterion",
        back_populates="rubric_version",
        cascade="all, delete-orphan",
        order_by="RubricCriterion.order_index",
    )


class RubricCriterion(Base, TimestampMixin):
    """单条二级指标。"""

    __tablename__ = "rubric_criterion"
    __table_args__ = (
        UniqueConstraint("rubric_version_id", "code", name="uq_criterion_version_code"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    rubric_version_id: Mapped[int] = mapped_column(
        ForeignKey("rubric_version.id", ondelete="CASCADE"), index=True
    )
    code: Mapped[str] = mapped_column(String(16), index=True)           # 'UC1.1'
    parent_code: Mapped[str] = mapped_column(String(16), default="")    # 'UC1'
    parent_name: Mapped[str] = mapped_column(String(255), default="")
    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(String(2000), default="")
    weight: Mapped[float] = mapped_column(Float, default=1.0)
    max_score: Mapped[float] = mapped_column(Float, default=1.0)
    order_index: Mapped[int] = mapped_column(Integer, default=0)
    error_freq_total: Mapped[int] = mapped_column(Integer, default=0)
    error_freq_by_class: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, nullable=False
    )
    common_errors: Mapped[list[str]] = mapped_column(JSONB, default=list, nullable=False)
    scoring_hint: Mapped[str] = mapped_column(String(2000), default="")
    not_applicable_when: Mapped[str] = mapped_column(String(500), default="")

    rubric_version = relationship("RubricVersion", back_populates="criteria")
