from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel

from .common import ORMBase


class GradingStatusItem(BaseModel):
    model_key: str
    status: str       # pending | running | success | failed
    score: float = 0.0


class CriterionScoreOut(BaseModel):
    code: str
    name: str = ""
    score: float
    max_score: float
    reasoning: str = ""


class GradingFeedbackOut(BaseModel):
    model_key: str
    status: str
    total_score: float = 0.0
    max_total_score: float = 0.0
    normalized_score: float = 0.0
    overall_comment: str = ""
    criteria: list[CriterionScoreOut] = []


class SubmissionOut(ORMBase):
    id: int
    student_id: int
    student_code: str = ""
    student_name: str = ""
    diagram_type: str
    problem_code: str
    problem_statement: str
    original_filename: str
    image_filename: str
    source_format: str
    element_count: int
    relation_count: int
    container_count: int
    parse_error: str
    created_at: datetime
    grading_status: list[GradingStatusItem] = []
    grading_feedback: GradingFeedbackOut | None = None


class SubmissionDetailOut(SubmissionOut):
    ir_textual: str


class SubmissionUploadIn(BaseModel):
    class_id: int
    student_code: str
    student_name: str = ""
    diagram_type: str        # use_case / class / sequence / swimlane
    problem_code: str = ""
    problem_statement: str = ""


class ClassOut(ORMBase):
    id: int
    code: str
    name: str


class StudentOut(ORMBase):
    id: int
    class_id: int
    student_code: str
    name: str
