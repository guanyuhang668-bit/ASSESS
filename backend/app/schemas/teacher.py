from __future__ import annotations

from pydantic import BaseModel, Field

from .common import ORMBase


class TeacherIssueIn(BaseModel):
    element_refs: list[str] = []
    description: str
    severity: str = "minor"


class TeacherIssueOut(ORMBase):
    id: int
    element_refs: list[str]
    description: str
    severity: str


class TeacherScoreIn(BaseModel):
    submission_id: int
    code: str
    score: float = Field(ge=0.0, le=1.0)
    max_score: float = 1.0
    not_applicable: bool = False
    comment: str = ""
    issues: list[TeacherIssueIn] = []


class TeacherScoreOut(ORMBase):
    id: int
    submission_id: int
    teacher_id: int
    code: str
    score: float
    max_score: float
    not_applicable: bool
    comment: str
    issues: list[TeacherIssueOut] = []
