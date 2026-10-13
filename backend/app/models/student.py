"""学生。"""

from __future__ import annotations

from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..core.db import Base
from ._common import TimestampMixin


class Student(Base, TimestampMixin):
    __tablename__ = "student"
    __table_args__ = (
        UniqueConstraint("class_id", "student_code", name="uq_student_class_code"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    class_id: Mapped[int] = mapped_column(ForeignKey("school_class.id", ondelete="CASCADE"))
    student_code: Mapped[str] = mapped_column(String(64), index=True)
    # 学号
    name: Mapped[str] = mapped_column(String(128), default="")

    class_ = relationship("SchoolClass", back_populates="students")
    submissions = relationship("Submission", back_populates="student", cascade="all, delete-orphan")
