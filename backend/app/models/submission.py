"""学生提交的原始 mdj + 解析后的 IR。"""

from __future__ import annotations

from typing import Any

from sqlalchemy import ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..core.db import Base
from ._common import TimestampMixin


class Submission(Base, TimestampMixin):
    """一名学生对一种图类型的一次提交。"""

    __tablename__ = "submission"
    __table_args__ = (
        UniqueConstraint(
            "student_id", "diagram_type", "problem_code",
            name="uq_submission_student_diagram_problem",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    student_id: Mapped[int] = mapped_column(
        ForeignKey("student.id", ondelete="CASCADE"), index=True
    )
    diagram_type: Mapped[str] = mapped_column(String(32), index=True)
    # 'use_case' | 'class' | 'sequence' | 'swimlane'
    problem_code: Mapped[str] = mapped_column(String(32), default="")
    # 题目编号，如 '1'、'2'、'实验报告-1'
    problem_statement: Mapped[str] = mapped_column(String(4000), default="")

    original_filename: Mapped[str] = mapped_column(String(255), default="")
    image_filename: Mapped[str] = mapped_column(String(255), default="")
    source_format: Mapped[str] = mapped_column(String(16), default="mdj")

    # 原始 mdj JSON 原样存档，方便回溯
    raw_data: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    # 解析后的 IR（UmlDiagram.model_dump()）
    ir_data: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    # parser 输出的文本化表示，LLM 喂 prompt 用
    ir_textual: Mapped[str] = mapped_column(String, default="")

    # 解析统计
    element_count: Mapped[int] = mapped_column(Integer, default=0)
    relation_count: Mapped[int] = mapped_column(Integer, default=0)
    container_count: Mapped[int] = mapped_column(Integer, default=0)

    parse_error: Mapped[str] = mapped_column(String(2000), default="")

    student = relationship("Student", back_populates="submissions")
    grading_results = relationship(
        "GradingResult", back_populates="submission", cascade="all, delete-orphan"
    )
    teacher_scores = relationship(
        "TeacherScore", back_populates="submission", cascade="all, delete-orphan"
    )
