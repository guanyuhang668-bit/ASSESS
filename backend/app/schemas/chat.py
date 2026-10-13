"""聊天相关 Pydantic schemas。"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel

from .common import ORMBase


class ChatSessionOut(ORMBase):
    id: int
    user_id: int
    experiment_group: str
    diagram_type: str
    problem_code: str
    problem_statement: str
    status: str
    round_number: int
    latest_score: float | None = None
    passed: bool
    created_at: datetime
    updated_at: datetime


class ChatMessageOut(ORMBase):
    id: int
    session_id: int
    role: str
    content: str
    mdj_filename: str | None = None
    image_filename: str | None = None
    image_url: str | None = None
    score_snapshot: float | None = None
    model_results: list["ChatModelResultOut"] = []
    created_at: datetime


class ChatSessionDetailOut(ChatSessionOut):
    messages: list[ChatMessageOut] = []
    # UML 建模能力画像（仅对特定实验组返回），键为维度名称，值为 0-100 分或 None
    ability_profile: dict[str, float | None] | None = None


class SendMessageIn(BaseModel):
    content: str = ""
    diagram_type: str = "use_case"
    problem_code: str = ""
    problem_statement: str = ""


class SendMessageOut(BaseModel):
    user_message: ChatMessageOut
    assistant_message: ChatMessageOut
    session: ChatSessionOut


class ChatModelCriterionScoreOut(ORMBase):
    id: int
    code: str
    score: float
    max_score: float
    not_applicable: bool
    has_issue: bool
    brief: str
    reasoning: str


class ChatModelResultOut(ORMBase):
    id: int
    model_key: str
    status: str
    total_score: float | None = None
    max_total_score: float
    normalized_score: float | None = None
    overall_comment: str
    raw_response: str
    error: str
    prompt_tokens: int
    completion_tokens: int
    elapsed_seconds: float
    criterion_scores: list[ChatModelCriterionScoreOut] = []
