"""教师对聊天会话逐条指标评分的 schemas。"""

from __future__ import annotations

from pydantic import BaseModel, Field

from .common import ORMBase


class ChatTeacherIssueIn(BaseModel):
    element_refs: list[str] = []
    description: str
    severity: str = "minor"


class ChatTeacherIssueOut(ORMBase):
    id: int
    element_refs: list[str]
    description: str
    severity: str


class ChatTeacherScoreIn(BaseModel):
    session_id: int
    code: str
    score: float = Field(ge=0.0, le=1.0)
    max_score: float = 1.0
    not_applicable: bool = False
    comment: str = ""
    issues: list[ChatTeacherIssueIn] = []


class ChatTeacherScoreOut(ORMBase):
    id: int
    session_id: int
    teacher_id: int
    code: str
    score: float
    max_score: float
    not_applicable: bool
    comment: str
    issues: list[ChatTeacherIssueOut] = []
