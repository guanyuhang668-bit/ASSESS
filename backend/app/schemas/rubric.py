from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from .common import ORMBase


class CriterionOut(ORMBase):
    id: int
    code: str
    parent_code: str
    parent_name: str
    name: str
    description: str
    weight: float
    max_score: float
    order_index: int
    error_freq_total: int
    common_errors: list[str]
    scoring_hint: str
    not_applicable_when: str


class RubricVersionOut(ORMBase):
    id: int
    diagram_type: str
    name: str
    is_active: bool
    description: str
    source_file: str


class RubricDetailOut(RubricVersionOut):
    criteria: list[CriterionOut]


class RubricImportIn(BaseModel):
    """从 YAML 文件（后端 configs/rubrics/）导入一份指标。"""

    diagram_type: str  # use_case / class / sequence / swimlane
    yaml_filename: str
    name: str = "v1"
    activate: bool = True
