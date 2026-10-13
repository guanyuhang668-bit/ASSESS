"""统一 UML 中间表示（Intermediate Representation, IR）。

无论学生提交的是 StarUML `.mdj`、drawio XML 还是其他格式，最终都先解析到此 IR。
后续 CoT/LLM 评判、教师评分对齐、错误检测 P/R/F1 计算均以 IR 中的 `id` 为锚点。

设计原则：
- 元素与关系全部展平，互引通过 `id` 字符串
- `raw` 字段保留原始解析片段，便于人工核查或可视化
- 字段尽量贴合 UML 概念，但允许 `extra` 收纳格式特有信息
"""

from __future__ import annotations

from typing import Literal, Any

from pydantic import BaseModel, Field


DiagramType = Literal["use_case", "class", "sequence", "swimlane"]

ElementType = Literal[
    # 用例图
    "actor", "use_case", "system_boundary",
    # 类图
    "class", "interface", "enumeration", "package",
    # 时序图
    "lifeline", "object", "boundary", "control", "entity",
    # 泳道图
    "swimlane", "activity", "initial", "final",
    "decision", "merge", "fork", "join",
    # 通用
    "note", "unknown",
]

RelationType = Literal[
    # 用例图
    "association", "include", "extend",
    # 类图 + 通用
    "generalization", "realization", "aggregation", "composition", "dependency",
    # 时序图
    "message_sync", "message_async", "message_return", "message_create", "message_delete",
    # 泳道图
    "control_flow", "object_flow",
    "unknown",
]


class UmlElement(BaseModel):
    """UML 中的一个节点（actor / use case / class / lifeline / activity ...）。"""

    id: str
    type: ElementType
    name: str = ""
    # 类图专用
    attributes: list[str] = Field(default_factory=list)
    operations: list[str] = Field(default_factory=list)
    # 容器关系：所属系统边界 / 泳道 / 包 等的 id
    container: str | None = None
    # 时序图：在生命线上的顺序索引（消息序号定位）
    order_index: int | None = None
    # 原始片段，便于回溯
    raw: dict[str, Any] = Field(default_factory=dict)
    extra: dict[str, Any] = Field(default_factory=dict)


class UmlRelation(BaseModel):
    """UML 中的一条边（关联 / 泛化 / 包含 / 消息 / 控制流 ...）。"""

    id: str
    type: RelationType
    source: str  # element id
    target: str  # element id
    label: str = ""
    # 类图专用
    multiplicity_source: str | None = None
    multiplicity_target: str | None = None
    role_source: str | None = None
    role_target: str | None = None
    # 泛化等的方向 / 箭头是否空心 / 是否实线（来自 .mdj 的 lineMode 等）
    arrow_style: dict[str, Any] = Field(default_factory=dict)
    # 时序图：消息序号
    sequence_number: int | None = None
    raw: dict[str, Any] = Field(default_factory=dict)
    extra: dict[str, Any] = Field(default_factory=dict)


class UmlContainer(BaseModel):
    """系统边界 / 泳道 / 包等容器。"""

    id: str
    type: Literal["system_boundary", "swimlane", "package", "frame"]
    name: str = ""
    # 包含的元素 id 列表（冗余信息，便于查询）
    members: list[str] = Field(default_factory=list)
    raw: dict[str, Any] = Field(default_factory=dict)


class UmlDiagram(BaseModel):
    """一份学生作品中的某一张 UML 图。"""

    diagram_type: DiagramType
    diagram_name: str = ""
    elements: list[UmlElement] = Field(default_factory=list)
    relations: list[UmlRelation] = Field(default_factory=list)
    containers: list[UmlContainer] = Field(default_factory=list)
    source_format: Literal["mdj", "drawio", "xmi"] = "mdj"
    source_file: str = ""
    extra: dict[str, Any] = Field(default_factory=dict)

    # ---- 便捷访问 ----
    def get_element(self, eid: str) -> UmlElement | None:
        for e in self.elements:
            if e.id == eid:
                return e
        return None

    def get_relation(self, rid: str) -> UmlRelation | None:
        for r in self.relations:
            if r.id == rid:
                return r
        return None

    def to_textual(self) -> str:
        """生成喂给 LLM 的紧凑文本表示（避免直接塞 JSON 浪费 token）。"""
        lines = [f"[Diagram] {self.diagram_type}: {self.diagram_name}"]
        if self.containers:
            lines.append("[Containers]")
            for c in self.containers:
                lines.append(f"  - {c.id} ({c.type}) {c.name}")
        if self.elements:
            lines.append("[Elements]")
            for e in self.elements:
                bits = [f"{e.id}", f"{e.type}", f'"{e.name}"']
                if e.attributes:
                    bits.append(f"attrs={e.attributes}")
                if e.operations:
                    bits.append(f"ops={e.operations}")
                if e.container:
                    bits.append(f"in={e.container}")
                lines.append("  - " + " | ".join(bits))
        if self.relations:
            lines.append("[Relations]")
            for r in self.relations:
                lab = f' "{r.label}"' if r.label else ""
                mul = ""
                if r.multiplicity_source or r.multiplicity_target:
                    mul = f" [{r.multiplicity_source or ''}..{r.multiplicity_target or ''}]"
                lines.append(
                    f"  - {r.id}: {r.source} --{r.type}{lab}{mul}--> {r.target}"
                )
        return "\n".join(lines)


class StudentSubmission(BaseModel):
    """一名学生的一次提交（可能包含多张图）。"""

    student_id: str
    class_id: str = ""
    diagrams: list[UmlDiagram] = Field(default_factory=list)
    submitted_at: str = ""
    raw_files: list[str] = Field(default_factory=list)
