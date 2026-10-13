"""mdj 解析服务（对 uml_grader.parsers.mdj 的薄包装）。"""

from __future__ import annotations

import json
from typing import Any

from ..uml_grader.ir import UmlDiagram
from ..uml_grader.parsers.mdj import parse_mdj


def parse_submission(raw_mdj: dict[str, Any] | str) -> list[UmlDiagram]:
    """解析一份学生 mdj（JSON 已 load 或字符串）。"""
    data = json.loads(raw_mdj) if isinstance(raw_mdj, str) else raw_mdj
    return parse_mdj(data)


def pick_diagram(diagrams: list[UmlDiagram], diagram_type: str) -> UmlDiagram | None:
    """从多张图里选指定类型的第一张（mdj 里除默认空 Main 外通常只有 1 张）。"""
    for d in diagrams:
        if d.diagram_type == diagram_type:
            return d
    return None
