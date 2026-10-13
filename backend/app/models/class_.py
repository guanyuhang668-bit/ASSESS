"""班级。"""

from __future__ import annotations

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..core.db import Base
from ._common import TimestampMixin


class SchoolClass(Base, TimestampMixin):
    __tablename__ = "school_class"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    # 如 '12401'
    name: Mapped[str] = mapped_column(String(128), default="")

    students = relationship("Student", back_populates="class_", cascade="all, delete-orphan")
