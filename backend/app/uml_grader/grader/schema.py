"""LLM 评分输出的强类型 schema。

用 pydantic 约束 LLM 必须输出的 JSON 结构，配合 repair 机制防止格式漂移。
所有 issue 必须给出 `element_ref`（IR 元素/关系 id），这是 P/R/F1 自动对齐的关键。
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


Severity = Literal["minor", "major", "critical"]


class Issue(BaseModel):
    """单条缺陷描述。"""

    element_ref: list[str] = Field(
        default_factory=list,
        description="缺陷涉及的 IR 元素/关系 id 列表。必须从 prompt 中提供的 [Elements]/[Relations] id 中选取。",
    )
    description: str = Field(description="对该缺陷的简洁描述（不含修改建议）。")
    severity: Severity = "minor"
    suggestion: str = Field(default="", description="给学生的修改建议。")


class CriterionScore(BaseModel):
    """对单条评价指标（如 UC1.1）的评判结果。"""

    code: str = Field(description="指标编号，如 'UC1.1'")
    score: float = Field(ge=0.0, le=10.0, description="该指标得分 [0,10]")
    max_score: float = 10.0
    reasoning: str = Field(description="逐步推理过程（CoT）。")
    issues: list[Issue] = Field(default_factory=list)
    not_applicable: bool = Field(
        default=False,
        description="若指标在本题不适用（如时序图控制结构指标在无分支题目中），置 True 并给出 reasoning。",
    )


class TokenUsage(BaseModel):
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


class GradingResult(BaseModel):
    """一次完整批改的结果（一份学生 × 一张图 × 一个模型）。"""

    student_id: str
    diagram_type: str
    model: str
    criteria: list[CriterionScore] = Field(default_factory=list)
    total_score: float = 0.0
    max_total_score: float = 0.0
    overall_comment: str = ""
    raw_response: str = ""
    timestamp: datetime = Field(default_factory=datetime.now)
    cost_tokens: TokenUsage = Field(default_factory=TokenUsage)
    elapsed_seconds: float = 0.0
    error: str | None = None  # 解析失败时填写
