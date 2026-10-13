"""从 YAML 或数据库加载指标体系。

数据源两种：
1. YAML 文件（开发期 / 启动初始化 / 教研会迭代批量导入）
2. PostgreSQL `rubric_criterion` 表（生产运行期）
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

import yaml

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


@dataclass
class CriterionDef:
    """运行期的指标定义（与 ORM 解耦，便于 prompt 模板使用）。"""

    code: str
    name: str
    parent_code: str = ""
    parent_name: str = ""
    description: str = ""
    scoring_hint: str = ""
    common_errors: list[str] = field(default_factory=list)
    error_freq_total: int = 0
    weight: float = 1.0
    max_score: float = 10.0
    not_applicable_when: str = ""


@dataclass
class RubricDef:
    diagram_type: str
    version_name: str
    criteria: list[CriterionDef]

    def group_by_parent(self) -> list[list[CriterionDef]]:
        """按一级指标分组（CoT 按组分批发给 LLM 避免漏判）。"""
        groups: dict[str, list[CriterionDef]] = {}
        order: list[str] = []
        for c in self.criteria:
            if c.parent_code not in groups:
                groups[c.parent_code] = []
                order.append(c.parent_code)
            groups[c.parent_code].append(c)
        return [groups[k] for k in order]


def load_rubric_from_yaml(path: str | Path, version_name: str = "v1") -> RubricDef:
    """从 YAML 加载一张图的指标。"""
    p = Path(path)
    with p.open(encoding="utf-8") as f:
        data = yaml.safe_load(f)
    criteria = [CriterionDef(**_sanitize(c)) for c in (data.get("criteria") or [])]
    return RubricDef(
        diagram_type=data.get("diagram_type", p.stem),
        version_name=version_name,
        criteria=criteria,
    )


def _sanitize(c: dict[str, Any]) -> dict[str, Any]:
    """YAML 转 CriterionDef 时剔除未知字段 + 默认值填充。"""
    allowed = {
        "code", "name", "parent_code", "parent_name", "description",
        "scoring_hint", "common_errors", "error_freq_total", "weight",
        "max_score", "not_applicable_when",
    }
    return {k: v for k, v in c.items() if k in allowed}


async def load_rubric_from_db(
    session: "AsyncSession", rubric_version_id: int,
) -> RubricDef:
    """从 PostgreSQL 加载。"""
    from ...models.rubric import RubricVersion  # 避免循环

    rv = await session.get(RubricVersion, rubric_version_id)
    if rv is None:
        raise ValueError(f"rubric_version_id={rubric_version_id} not found")
    criteria_rows = await rv.awaitable_attrs.criteria

    criteria = [
        CriterionDef(
            code=r.code,
            name=r.name,
            parent_code=r.parent_code,
            parent_name=r.parent_name,
            description=r.description,
            scoring_hint=r.scoring_hint,
            common_errors=list(r.common_errors or []),
            error_freq_total=r.error_freq_total,
            weight=r.weight,
            max_score=r.max_score,
            not_applicable_when=r.not_applicable_when,
        )
        for r in criteria_rows
    ]
    return RubricDef(
        diagram_type=rv.diagram_type,
        version_name=rv.name,
        criteria=criteria,
    )
