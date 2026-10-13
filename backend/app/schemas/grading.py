from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from ..models.grading import GradingResultStatus, GradingRunStatus
from .common import ORMBase


class IssueOut(ORMBase):
    id: int
    element_refs: list[str]
    description: str
    severity: str
    suggestion: str


class CriterionScoreOut(ORMBase):
    id: int
    code: str
    score: float
    max_score: float
    not_applicable: bool
    reasoning: str
    issues: list[IssueOut] = []


class GradingResultOut(ORMBase):
    id: int
    run_id: int
    submission_id: int
    rubric_version_id: int
    model_key: str
    status: GradingResultStatus
    total_score: float
    max_total_score: float
    normalized_score: float
    overall_comment: str
    prompt_tokens: int
    completion_tokens: int
    elapsed_seconds: float
    error: str
    started_at: datetime | None = None
    finished_at: datetime | None = None


class GradingResultDetailOut(GradingResultOut):
    criterion_scores: list[CriterionScoreOut] = []


class GradingRunOut(ORMBase):
    id: int
    name: str
    description: str
    status: GradingRunStatus
    model_keys: list[str]
    rubric_version_ids: list[int]
    submission_ids: list[int]
    total_tasks: int
    completed_tasks: int
    failed_tasks: int
    started_at: datetime | None = None
    finished_at: datetime | None = None
    error: str
    created_at: datetime


class GradingRunCreateIn(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    description: str = ""
    submission_ids: list[int] = Field(min_length=1)
    model_keys: list[str] = Field(min_length=1)
    rubric_version_ids: list[int] = Field(default_factory=list)
    # 留空则使用 is_active=True 的 rubric


class GradingProgressOut(BaseModel):
    run_id: int
    status: GradingRunStatus
    total: int
    completed: int
    failed: int
    running: int
    pending: int
    per_model: dict[str, dict[str, int]] = {}
