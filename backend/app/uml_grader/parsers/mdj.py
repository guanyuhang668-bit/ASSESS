"""StarUML `.mdj` (JSON) → 统一 UML IR 解析器。

**约定**：
- 一个 `.mdj` 文件可包含多个 `UMLDiagram`；解析器返回每张图独立的 `UmlDiagram`。
- 解析仅依赖 `_type / _id / $ref` 等结构化字段，**不依赖坐标/字体/颜色**等 View 信息。
- 通过 `_id` 索引整张表，再按图类型筛选元素与关系。

**支持的 mdj 节点类型**：
- 用例图：`UMLUseCaseDiagram`, `UMLActor`, `UMLUseCase`, `UMLUseCaseSubject`,
         `UMLAssociation`, `UMLInclude`, `UMLExtend`, `UMLGeneralization`
- 类图：`UMLClassDiagram`, `UMLClass`, `UMLInterface`, `UMLEnumeration`,
       `UMLAttribute`, `UMLOperation`,
       `UMLAssociation`, `UMLGeneralization`, `UMLDependency`,
       `UMLInterfaceRealization`
- 时序图：`UMLSequenceDiagram`, `UMLLifeline`, `UMLMessage`,
         `UMLCombinedFragment`, `UMLInteractionOperand`
- 活动 / 泳道图：`UMLActivityDiagram`, `UMLActivity`, `UMLActivityPartition`,
              `UMLAction`, `UMLInitialNode`, `UMLActivityFinalNode`,
              `UMLDecisionNode`, `UMLMergeNode`, `UMLForkNode`, `UMLJoinNode`,
              `UMLControlFlow`, `UMLObjectFlow`
"""

from __future__ import annotations

import json
import math
import re
from pathlib import Path
from typing import Any, Iterable

from ..ir import (
    DiagramType,
    UmlContainer,
    UmlDiagram,
    UmlElement,
    UmlRelation,
)


# ---------------------------- 通用工具 ----------------------------


def _walk(node: Any) -> Iterable[dict]:
    """深度优先遍历所有 dict 节点。"""
    if isinstance(node, dict):
        yield node
        for v in node.values():
            yield from _walk(v)
    elif isinstance(node, list):
        for v in node:
            yield from _walk(v)


def _ref(value: Any) -> str | None:
    """从 `{'$ref': 'xxx'}` 提取目标 id；若是 reference 嵌套也兼容。"""
    if not isinstance(value, dict):
        return None
    if "$ref" in value:
        return value["$ref"]
    inner = value.get("reference")
    if isinstance(inner, dict) and "$ref" in inner:
        return inner["$ref"]
    return None


def _build_index(root: dict) -> dict[str, dict]:
    """把所有 `_id` → 节点的索引建好。"""
    idx: dict[str, dict] = {}
    for n in _walk(root):
        nid = n.get("_id")
        if isinstance(nid, str):
            idx[nid] = n
    return idx


def _children_recursive(node: dict, predicate) -> list[dict]:
    """递归收集满足 predicate 的子节点。"""
    out: list[dict] = []
    for n in _walk(node):
        if predicate(n):
            out.append(n)
    return out


# ---------------------------- 类型映射 ----------------------------


_DIAGRAM_TYPE_MAP: dict[str, DiagramType] = {
    "UMLUseCaseDiagram": "use_case",
    "UMLClassDiagram": "class",
    "UMLSequenceDiagram": "sequence",
    "UMLActivityDiagram": "swimlane",  # 泳道图本质是带 partition 的活动图
}

_USECASE_ELEMENT_TYPES = {
    "UMLActor": "actor",
    "UMLUseCase": "use_case",
    "UMLUseCaseSubject": "system_boundary",
}

_CLASS_ELEMENT_TYPES = {
    "UMLClass": "class",
    "UMLInterface": "interface",
    "UMLEnumeration": "enumeration",
    "UMLPackage": "package",
}

_SEQUENCE_ELEMENT_TYPES = {
    "UMLLifeline": "lifeline",
}

_ACTIVITY_ELEMENT_TYPES = {
    "UMLAction": "activity",
    "UMLActivityNode": "activity",
    "UMLOpaqueAction": "activity",
    "UMLInitialNode": "initial",
    "UMLActivityFinalNode": "final",
    "UMLFlowFinalNode": "final",
    "UMLDecisionNode": "decision",
    "UMLMergeNode": "merge",
    "UMLForkNode": "fork",
    "UMLJoinNode": "join",
}


# ---------------------------- 单图解析 ----------------------------


def _parse_use_case_diagram(
    diag_node: dict, idx: dict[str, dict], source_file: str
) -> UmlDiagram:
    """解析用例图：actor / usecase / subject + association/include/extend/generalization.

    **策略**：以 diagram 的 `ownedViews` 为可见性真值——只有真正画在图上的
    元素 / 关系才进入 IR。学生在 StarUML 里删掉一根连线时只删 view 不删
    model 节点，若不做 view 过滤会产生大量"幽灵"关系污染评分。
    若 diagram 完全无 ownedViews（极少见的特殊 mdj）才退化为按 `_type` 全收。

    关系一律以「edge view」为真值：每个 UMLAssociationView/UMLIncludeView/...
    各自发射一条关系，端点取自 view.head/tail（修复 StarUML 多 view 共享
    单 model 时所有线被压成一条的伪迹）。当 view 端点解析失败时回落到
    model 的 end1/end2 / source/target。
    """
    elements: list[UmlElement] = []
    relations: list[UmlRelation] = []
    containers: list[UmlContainer] = []
    scope = _scope_or_none(diag_node)

    edge_view_types = ("UMLAssociationView", "UMLIncludeView",
                       "UMLExtendView", "UMLGeneralizationView")
    views_by_model = _views_by_model(diag_node, edge_view_types)

    def _emit_edge(n: dict, rtype: str, fallback_ep) -> None:
        nid = n["_id"]
        views = views_by_model.get(nid, [])
        if views:
            for v in views:
                ep = _edge_view_endpoints(v, idx) or fallback_ep()
                if not ep:
                    continue
                src, tgt = ep
                relations.append(
                    UmlRelation(
                        id=v["_id"],
                        type=rtype,  # type: ignore[arg-type]
                        source=src, target=tgt,
                        label=n.get("name", "") or "",
                        raw={"_type": n.get("_type"), "model_id": nid,
                             "view_id": v["_id"]},
                    )
                )
        else:
            ep = fallback_ep()
            if ep:
                src, tgt = ep
                relations.append(
                    UmlRelation(
                        id=nid,
                        type=rtype,  # type: ignore[arg-type]
                        source=src, target=tgt,
                        label=n.get("name", "") or "",
                        raw={"_type": n.get("_type")},
                    )
                )

    for n in idx.values():
        t = n.get("_type", "")
        nid = n.get("_id")
        if not nid:
            continue
        if scope is not None and nid not in scope:
            continue

        if t in _USECASE_ELEMENT_TYPES:
            etype = _USECASE_ELEMENT_TYPES[t]
            if etype == "system_boundary":
                containers.append(
                    UmlContainer(
                        id=nid,
                        type="system_boundary",
                        name=n.get("name", "") or "",
                        raw={"_type": t},
                    )
                )
            else:
                elements.append(
                    UmlElement(
                        id=nid,
                        type=etype,  # type: ignore[arg-type]
                        name=n.get("name", "") or "",
                        raw={"_type": t},
                    )
                )
        elif t == "UMLAssociation":
            _emit_edge(n, "association", lambda: _association_endpoints(n))
        elif t == "UMLInclude":
            _emit_edge(n, "include", lambda: _src_tgt_endpoints(n))
        elif t == "UMLExtend":
            _emit_edge(n, "extend", lambda: _src_tgt_endpoints(n))
        elif t == "UMLGeneralization":
            _emit_edge(n, "generalization", lambda: _src_tgt_endpoints(n))

    # 系统边界包含哪些用例：根据 view 中的 contained 关系判断（best-effort）
    _attach_subject_membership(diag_node, idx, elements, containers)

    return UmlDiagram(
        diagram_type="use_case",
        diagram_name=diag_node.get("name", "") or "",
        elements=elements,
        relations=_dedup_relations(relations),
        containers=containers,
        source_format="mdj",
        source_file=source_file,
    )


def _parse_class_diagram(
    diag_node: dict, idx: dict[str, dict], source_file: str
) -> UmlDiagram:
    """解析类图：class/interface/enum + 关系。

    见 `_parse_use_case_diagram` 注释：以 `ownedViews` 为真值过滤可见性。
    类内部的 attribute / operation 也按 view 过滤——学生删掉某条属性/方法时
    StarUML 同样只删 AttributeView/OperationView，model 残留会被当成幽灵字段。

    关系一律以「edge view」为真值：每条 UMLAssociationView/UMLDependencyView/...
    各发射一条关系，端点取自 view.head/tail（修复 StarUML 多 view 共享单 model
    时所有线被压成一条的伪迹）。多重性 / 角色名仍来自 model.end1/end2，
    多 view 共享场景下会沿用 model 的值（best-effort）。
    """
    elements: list[UmlElement] = []
    relations: list[UmlRelation] = []
    scope = _scope_or_none(diag_node)

    def _in_scope(_id: str | None) -> bool:
        return scope is None or (_id is not None and _id in scope)

    edge_view_types = ("UMLAssociationView", "UMLGeneralizationView",
                       "UMLDependencyView", "UMLAbstractionView",
                       "UMLInterfaceRealizationView", "UMLRealizationView")
    views_by_model = _views_by_model(diag_node, edge_view_types)

    def _emit_assoc(n: dict) -> None:
        nid = n["_id"]
        end1 = _find_end(n, "end1")
        end2 = _find_end(n, "end2")
        rtype = _classify_association(end1, end2)
        kwargs = dict(
            label=n.get("name", "") or "",
            multiplicity_source=(end1 or {}).get("multiplicity") or None,
            multiplicity_target=(end2 or {}).get("multiplicity") or None,
            role_source=(end1 or {}).get("name") or None,
            role_target=(end2 or {}).get("name") or None,
            arrow_style={
                "navigable_source": (end1 or {}).get("navigable"),
                "navigable_target": (end2 or {}).get("navigable"),
                "aggregation_source": (end1 or {}).get("aggregation"),
                "aggregation_target": (end2 or {}).get("aggregation"),
            },
        )
        views = views_by_model.get(nid, [])
        if views:
            for v in views:
                ep = _edge_view_endpoints(v, idx) or _association_endpoints(n)
                if not ep:
                    continue
                src, tgt = ep
                relations.append(UmlRelation(
                    id=v["_id"], type=rtype,  # type: ignore[arg-type]
                    source=src, target=tgt,
                    raw={"_type": "UMLAssociation", "model_id": nid,
                         "view_id": v["_id"]},
                    **kwargs,
                ))
        else:
            ep = _association_endpoints(n)
            if ep:
                src, tgt = ep
                relations.append(UmlRelation(
                    id=nid, type=rtype,  # type: ignore[arg-type]
                    source=src, target=tgt,
                    raw={"_type": "UMLAssociation"},
                    **kwargs,
                ))

    def _emit_simple_edge(n: dict, rtype: str) -> None:
        nid = n["_id"]
        views = views_by_model.get(nid, [])
        if views:
            for v in views:
                ep = _edge_view_endpoints(v, idx) or _src_tgt_endpoints(n)
                if not ep:
                    continue
                src, tgt = ep
                relations.append(UmlRelation(
                    id=v["_id"], type=rtype,  # type: ignore[arg-type]
                    source=src, target=tgt,
                    label=n.get("name", "") or "",
                    raw={"_type": n.get("_type"), "model_id": nid,
                         "view_id": v["_id"]},
                ))
        else:
            ep = _src_tgt_endpoints(n)
            if ep:
                src, tgt = ep
                relations.append(UmlRelation(
                    id=nid, type=rtype,  # type: ignore[arg-type]
                    source=src, target=tgt,
                    label=n.get("name", "") or "",
                    raw={"_type": n.get("_type")},
                ))

    for n in idx.values():
        t = n.get("_type", "")
        nid = n.get("_id")
        if not nid:
            continue
        if not _in_scope(nid):
            continue

        if t in _CLASS_ELEMENT_TYPES:
            etype = _CLASS_ELEMENT_TYPES[t]
            attrs = [
                _format_attribute(a) for a in (n.get("attributes") or [])
                if isinstance(a, dict) and _in_scope(a.get("_id"))
            ]
            ops = [
                _format_operation(o) for o in (n.get("operations") or [])
                if isinstance(o, dict) and _in_scope(o.get("_id"))
            ]
            elements.append(
                UmlElement(
                    id=nid,
                    type=etype,  # type: ignore[arg-type]
                    name=n.get("name", "") or "",
                    attributes=attrs,
                    operations=ops,
                    raw={"_type": t},
                )
            )
        elif t == "UMLAssociation":
            _emit_assoc(n)
        elif t == "UMLGeneralization":
            _emit_simple_edge(n, "generalization")
        elif t in ("UMLDependency", "UMLAbstraction"):
            _emit_simple_edge(n, "dependency")
        elif t in ("UMLInterfaceRealization", "UMLRealization"):
            _emit_simple_edge(n, "realization")

    # 学生若把多重性 / 角色名 / 关系标签写成游离 UMLTextView 文本框（而非用
    # StarUML 的 multiplicity / aggregation 字段），用坐标几何匹配把它们绑回到
    # 最近的边视图上——这是 best-effort，仅在结构字段为空时填入，不会覆盖。
    _attach_floating_labels(diag_node, idx, relations, edge_view_types)

    return UmlDiagram(
        diagram_type="class",
        diagram_name=diag_node.get("name", "") or "",
        elements=elements,
        relations=_dedup_relations(relations),
        source_format="mdj",
        source_file=source_file,
    )


def _parse_sequence_diagram(
    diag_node: dict, idx: dict[str, dict], source_file: str
) -> UmlDiagram:
    """解析时序图：lifeline + message + combined fragment。

    见 `_parse_use_case_diagram` 注释：以 `ownedViews` 为真值过滤可见性。
    每条 UMLMessageView 单独发射一条消息，端点取自 view.head/tail（与
    use-case / class 同构，修复多 view 共享单 model 的伪迹）。
    """
    elements: list[UmlElement] = []
    relations: list[UmlRelation] = []
    containers: list[UmlContainer] = []
    scope = _scope_or_none(diag_node)

    views_by_model = _views_by_model(diag_node, ("UMLMessageView",))

    def _classify_message(n: dict) -> str:
        sort = (n.get("messageSort") or "synchCall").lower()
        if "reply" in sort:
            return "message_return"
        if "create" in sort:
            return "message_create"
        if "delete" in sort:
            return "message_delete"
        if "asynch" in sort or "async" in sort:
            return "message_async"
        return "message_sync"

    def _emit_message(n: dict) -> None:
        nid = n["_id"]
        rtype = _classify_message(n)
        kwargs = dict(
            label=n.get("name", "") or "",
            raw={"_type": "UMLMessage", "messageSort": n.get("messageSort")},
        )
        views = views_by_model.get(nid, [])
        if views:
            for v in views:
                ep = _edge_view_endpoints(v, idx) or _src_tgt_endpoints(n)
                if not ep:
                    continue
                src, tgt = ep
                relations.append(UmlRelation(
                    id=v["_id"], type=rtype,  # type: ignore[arg-type]
                    source=src, target=tgt,
                    **{**kwargs, "raw": {**kwargs["raw"], "model_id": nid,
                                         "view_id": v["_id"]}},
                ))
        else:
            ep = _src_tgt_endpoints(n)
            if ep:
                src, tgt = ep
                relations.append(UmlRelation(
                    id=nid, type=rtype,  # type: ignore[arg-type]
                    source=src, target=tgt,
                    **kwargs,
                ))

    for n in idx.values():
        t = n.get("_type", "")
        nid = n.get("_id")
        if not nid:
            continue
        if scope is not None and nid not in scope:
            continue

        if t == "UMLLifeline":
            elements.append(
                UmlElement(
                    id=nid, type="lifeline",
                    name=n.get("name", "") or "",
                    raw={"_type": t},
                )
            )
        elif t == "UMLMessage":
            _emit_message(n)
        elif t == "UMLCombinedFragment":
            # 控制结构（alt/opt/loop/par）作为容器收纳
            containers.append(
                UmlContainer(
                    id=nid, type="frame",
                    name=n.get("name", "") or "",
                    raw={"_type": t, "interactionOperator": n.get("interactionOperator")},
                )
            )

    # 给消息按出现顺序排序号
    for i, r in enumerate(relations, start=1):
        r.sequence_number = i

    return UmlDiagram(
        diagram_type="sequence",
        diagram_name=diag_node.get("name", "") or "",
        elements=elements,
        relations=relations,
        containers=containers,
        source_format="mdj",
        source_file=source_file,
    )


def _infer_partition_from_views(
    diag_node: dict, idx: dict[str, dict],
    partition_member: dict[str, str],
) -> None:
    """从 diagram 的 ownedViews 中利用坐标推断 action↔swimlane 归属。

    StarUML 的泳道图中，UMLSwimlaneView 有 left/width 定义水平范围，
    UMLActionView 的 left 坐标落在哪个 swimlane 范围内即属于哪个泳道。
    同样支持垂直泳道（用 top/height）。
    """
    views = diag_node.get("ownedViews") or []

    # 收集泳道视图的范围 → partition model id
    lane_ranges: list[tuple[int, int, int, int, str]] = []  # (left, top, width, height, model_id)
    # 收集 action 视图的坐标 → model id
    action_positions: list[tuple[int, int, str]] = []  # (left, top, model_id)

    for view in views:
        if not isinstance(view, dict):
            continue
        vtype = view.get("_type", "")
        model_ref = _ref(view.get("model"))
        if not model_ref:
            continue

        if vtype == "UMLSwimlaneView":
            left = view.get("left", 0)
            top = view.get("top", 0)
            width = view.get("width", 0)
            height = view.get("height", 0)
            lane_ranges.append((left, top, width, height, model_ref))
        elif vtype in ("UMLActionView", "UMLInitialNodeView", "UMLActivityFinalNodeView",
                        "UMLDecisionNodeView", "UMLMergeNodeView", "UMLForkNodeView", "UMLJoinNodeView"):
            left = view.get("left", 0)
            top = view.get("top", 0)
            action_positions.append((left, top, model_ref))
        elif vtype == "UMLNameCompartmentView":
            # 跳过子视图
            continue
        else:
            # 尝试从 subViews 中也识别 action 类视图
            sub_model = _ref(view.get("model"))
            if sub_model and sub_model in idx:
                node = idx[sub_model]
                nt = node.get("_type", "")
                if nt in _ACTIVITY_ELEMENT_TYPES:
                    left = view.get("left", 0)
                    top = view.get("top", 0)
                    action_positions.append((left, top, sub_model))

    if not lane_ranges or not action_positions:
        return

    # 判断泳道方向：如果泳道宽度远大于高度，可能是横向排列(垂直泳道)
    # 典型情况：泳道并排排列，left 不同, top 相同
    for ax, ay, a_model_id in action_positions:
        if a_model_id in partition_member:
            continue
        # 找包含该 action 坐标的 swimlane
        best_lane = None
        for lx, ly, lw, lh, lane_model_id in lane_ranges:
            if lx <= ax < lx + lw and ly <= ay < ly + lh:
                best_lane = lane_model_id
                break
        if best_lane:
            partition_member[a_model_id] = best_lane


def _parse_activity_diagram(
    diag_node: dict, idx: dict[str, dict], source_file: str
) -> UmlDiagram:
    """解析活动 / 泳道图：partition + action + control flow。

    见 `_parse_use_case_diagram` 注释：以 `ownedViews` 为真值过滤可见性。
    """
    elements: list[UmlElement] = []
    relations: list[UmlRelation] = []
    containers: list[UmlContainer] = []
    partition_member: dict[str, str] = {}  # element_id -> partition_id
    scope = _scope_or_none(diag_node)

    # 先扫一遍 partition，建立成员关系（partition.inPartition 反向 / partition.ownedElements）
    for n in idx.values():
        if n.get("_type") != "UMLActivityPartition":
            continue
        pid = n.get("_id")
        if not pid:
            continue
        if scope is not None and pid not in scope:
            continue
        containers.append(
            UmlContainer(
                id=pid, type="swimlane",
                name=n.get("name", "") or "",
                raw={"_type": "UMLActivityPartition"},
            )
        )
        # 一些 mdj 用 inPartition 数组（在 action 上反向引用），先尝试正向
        for owned in (n.get("ownedElements") or []):
            oid = owned.get("_id") if isinstance(owned, dict) else None
            if oid:
                partition_member[oid] = pid

    # 反向：从每个节点的 inPartition 中读
    for n in idx.values():
        in_p = n.get("inPartition")
        nid = n.get("_id")
        if not nid:
            continue
        if isinstance(in_p, list):
            for ref in in_p:
                rid = _ref(ref)
                if rid:
                    partition_member[nid] = rid
                    break
        elif isinstance(in_p, dict):
            rid = _ref(in_p)
            if rid:
                partition_member[nid] = rid

    # 视图坐标兜底：StarUML 常把 action↔partition 的归属仅用坐标重叠表达
    # 从 diagram 的 ownedViews 中提取 swimlane 的水平范围，把 action 按 x 坐标归入
    if not partition_member and containers:
        _infer_partition_from_views(diag_node, idx, partition_member)

    flow_views_by_model = _views_by_model(
        diag_node, ("UMLControlFlowView", "UMLObjectFlowView")
    )

    def _emit_flow(n: dict, rtype: str) -> None:
        nid = n["_id"]
        kwargs = dict(
            label=(n.get("name") or n.get("guard") or "") or "",
            raw={"_type": n.get("_type"), "guard": n.get("guard")},
        )
        views = flow_views_by_model.get(nid, [])
        if views:
            for v in views:
                ep = _edge_view_endpoints(v, idx) or _src_tgt_endpoints(n)
                if not ep:
                    continue
                src, tgt = ep
                relations.append(UmlRelation(
                    id=v["_id"], type=rtype,  # type: ignore[arg-type]
                    source=src, target=tgt,
                    **{**kwargs, "raw": {**kwargs["raw"], "model_id": nid,
                                         "view_id": v["_id"]}},
                ))
        else:
            ep = _src_tgt_endpoints(n)
            if ep:
                src, tgt = ep
                relations.append(UmlRelation(
                    id=nid, type=rtype,  # type: ignore[arg-type]
                    source=src, target=tgt,
                    **kwargs,
                ))

    for n in idx.values():
        t = n.get("_type", "")
        nid = n.get("_id")
        if not nid:
            continue
        if scope is not None and nid not in scope:
            continue

        if t in _ACTIVITY_ELEMENT_TYPES:
            elements.append(
                UmlElement(
                    id=nid,
                    type=_ACTIVITY_ELEMENT_TYPES[t],  # type: ignore[arg-type]
                    name=n.get("name", "") or "",
                    container=partition_member.get(nid),
                    raw={"_type": t},
                )
            )
        elif t == "UMLControlFlow":
            _emit_flow(n, "control_flow")
        elif t == "UMLObjectFlow":
            _emit_flow(n, "object_flow")

    # 同步 container.members
    member_map: dict[str, list[str]] = {}
    for eid, pid in partition_member.items():
        member_map.setdefault(pid, []).append(eid)
    for c in containers:
        c.members = member_map.get(c.id, [])

    return UmlDiagram(
        diagram_type="swimlane",
        diagram_name=diag_node.get("name", "") or "",
        elements=elements,
        relations=relations,
        containers=containers,
        source_format="mdj",
        source_file=source_file,
    )


# ---------------------------- 辅助函数 ----------------------------


def _format_attribute(a: dict) -> str:
    """把 UMLAttribute 节点格式化为 'name: type [mult]'。"""
    name = a.get("name", "") or ""
    type_ = a.get("type", "") or ""
    mult = a.get("multiplicity", "") or ""
    visibility = a.get("visibility", "") or ""
    vis_prefix = {"public": "+", "private": "-", "protected": "#", "package": "~"}.get(
        visibility, ""
    )
    parts = [vis_prefix + name] if vis_prefix else [name]
    if type_:
        parts.append(f": {type_}" if isinstance(type_, str) else f": {type_}")
    if mult:
        parts.append(f"[{mult}]")
    return " ".join(p for p in parts if p).strip()


def _format_operation(o: dict) -> str:
    """把 UMLOperation 节点格式化为 'name(params)'。"""
    name = o.get("name", "") or ""
    params = o.get("parameters") or []
    if isinstance(params, list):
        param_strs = []
        ret = None
        for p in params:
            if not isinstance(p, dict):
                continue
            d = (p.get("direction") or "").lower()
            if d == "return":
                ret = p.get("type", "") or ""
                continue
            pname = p.get("name", "") or ""
            ptype = p.get("type", "") or ""
            param_strs.append(f"{pname}: {ptype}".strip(": ").strip())
        sig = f"{name}({', '.join(param_strs)})"
        if ret:
            sig += f": {ret}"
        return sig.strip()
    return name


def _association_endpoints(assoc: dict) -> tuple[str, str] | None:
    """从 UMLAssociation 取出两端引用的元素 id。"""
    e1 = assoc.get("end1")
    e2 = assoc.get("end2")
    if isinstance(e1, dict) and isinstance(e2, dict):
        s = _ref(e1.get("reference"))
        t = _ref(e2.get("reference"))
        if s and t:
            return s, t
    # 兜底：直接 source/target
    s = _ref(assoc.get("source"))
    t = _ref(assoc.get("target"))
    if s and t:
        return s, t
    return None


def _src_tgt_endpoints(n: dict) -> tuple[str, str] | None:
    """从带 source/target 字段的 edge model（非 UMLAssociation）取出两端。"""
    s = _ref(n.get("source"))
    t = _ref(n.get("target"))
    return (s, t) if s and t else None


def _edge_view_endpoints(
    view: dict, idx: dict[str, dict]
) -> tuple[str, str] | None:
    """从 edge view 的 tail/head 推导出（source_model_id, target_model_id）。

    StarUML 的 edge view（UMLAssociationView / UMLDependencyView / UMLIncludeView / ...）
    都有 head/tail 两个字段引用另两个 element view（如 UMLActorView / UMLClassView），
    这些 element view 的 `model.$ref` 才是真正要连接的 element model。
    约定：tail = source，head = target（与 StarUML 内部一致）。

    这个函数是修复「多 view 共享单 model」伪迹的关键：学生用 quick-edit / drag
    复制连线时，staruml 会创建多个 view，但所有 view 的 model.$ref 全都指
    向首次绘制那个 model。以 view 的 head/tail 为准才能还原学生实际的连接意图。
    """
    head_view_id = _ref(view.get("head"))
    tail_view_id = _ref(view.get("tail"))
    if not (head_view_id and tail_view_id):
        return None
    head_view = idx.get(head_view_id)
    tail_view = idx.get(tail_view_id)
    if not (head_view and tail_view):
        return None
    head_model = _ref(head_view.get("model"))
    tail_model = _ref(tail_view.get("model"))
    if not (head_model and tail_model):
        return None
    return tail_model, head_model


def _views_by_model(
    diag_node: dict, view_types: tuple[str, ...]
) -> dict[str, list[dict]]:
    """把 diagram 中指定类型的所有 view 按 `model.$ref` 分组。

    返回 {model_id: [view, view, ...]}。同一个 model 被多个 view 引用是正常场景
    （学生用 quick-edit / drag 复制连线 → 多个 view 共享一个 model）。
    调用方需为每个 view 各发射一条关系、且用 view.head/tail 取端点。
    """
    out: dict[str, list[dict]] = {}
    for v in _walk(diag_node.get("ownedViews") or []):
        if not isinstance(v, dict):
            continue
        if v.get("_type") not in view_types:
            continue
        mid = _ref(v.get("model"))
        if mid:
            out.setdefault(mid, []).append(v)
    return out


# ---------------------------- 坐标几何匹配 ----------------------------


_MULT_RE = re.compile(r"^\s*[\d*nN]+\s*(\.{2,3}\s*[\d*nN]+\s*)?$")


def _is_multiplicity_text(text: str) -> bool:
    """识别多重性字面量：`1`、`*`、`n`、`0..1`、`0..*`、`1..n`、`0...n` 等。"""
    return bool(_MULT_RE.match(text))


def _view_center(view: dict | None) -> tuple[float, float] | None:
    """从 left/top/width/height 算出 view 的几何中心。"""
    if not isinstance(view, dict):
        return None
    L = view.get("left")
    T = view.get("top")
    W = view.get("width")
    H = view.get("height")
    if any(x is None for x in (L, T, W, H)):
        return None
    try:
        return (float(L) + float(W) / 2.0, float(T) + float(H) / 2.0)
    except (TypeError, ValueError):
        return None


def _parse_points(s: str | None) -> list[tuple[float, float]]:
    """解析 'x1:y1;x2:y2;...' 折线字符串。"""
    if not isinstance(s, str) or not s:
        return []
    pts: list[tuple[float, float]] = []
    for part in s.split(";"):
        if ":" not in part:
            continue
        try:
            x_str, y_str = part.split(":", 1)
            pts.append((float(x_str.strip()), float(y_str.strip())))
        except (ValueError, TypeError):
            continue
    return pts


def _dist_p2p(a: tuple[float, float], b: tuple[float, float]) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


def _dist_p_seg(
    p: tuple[float, float],
    a: tuple[float, float],
    b: tuple[float, float],
) -> float:
    """点到线段的最短距离。"""
    px, py = p
    ax, ay = a
    bx, by = b
    dx, dy = bx - ax, by - ay
    if dx == 0 and dy == 0:
        return _dist_p2p(p, a)
    t = ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)
    t = max(0.0, min(1.0, t))
    qx, qy = ax + t * dx, ay + t * dy
    return math.hypot(px - qx, py - qy)


def _dist_p_polyline(
    p: tuple[float, float],
    segments: list[tuple[tuple[float, float], tuple[float, float]]],
) -> float:
    if not segments:
        return float("inf")
    return min(_dist_p_seg(p, a, b) for a, b in segments)


def _attach_floating_labels(
    diag_node: dict,
    idx: dict[str, dict],
    relations: list[UmlRelation],
    edge_view_types: tuple[str, ...],
    line_distance_threshold: float = 100.0,
) -> None:
    """把游离 `UMLTextView` 按坐标几何匹配到最近的边视图、回填到关系上。

    学生（如刘玉玲类图）会把多重性 / 角色名 / 关系标签写成游离文本框而非用
    StarUML 的 multiplicity / aggregation 字段。这些文本只有 left/top/width/height
    没有任何结构性绑定，唯一的还原途径是几何匹配。

    策略：
    - 多重性样式文本（`1` / `0..*` / `1..n` 等）→ 二部贪心匹配到 (line, end)：
      每个 (line, end) 至多一个多重性，避免同一文本被重复消耗或同一端被两次填入。
      如果 model.end1/end2 已有多重性则不覆盖（尊重学生用结构字段写的版本）。
    - 普通标签文本 → 拼接到最近边的关系 `label`。

    `line_distance_threshold`：文本到线段的最大像素距离，超过即视为无关注释跳过。
    """
    if not relations:
        return

    relation_by_view_id = {r.id: r for r in relations}

    # 收集本图所有 edge view 及其几何（折线、head/tail 中心）
    edges: list[tuple[str, list, tuple[float, float] | None, tuple[float, float] | None]] = []
    for v in _walk(diag_node.get("ownedViews") or []):
        if not isinstance(v, dict):
            continue
        if v.get("_type") not in edge_view_types:
            continue
        vid = v.get("_id")
        if not vid or vid not in relation_by_view_id:
            continue
        pts = _parse_points(v.get("points"))
        segs = [(pts[i], pts[i + 1]) for i in range(len(pts) - 1)]
        head_view = idx.get(_ref(v.get("head")) or "")
        tail_view = idx.get(_ref(v.get("tail")) or "")
        head_center = _view_center(head_view) if head_view else None
        tail_center = _view_center(tail_view) if tail_view else None
        if not segs and head_center and tail_center:
            segs = [(tail_center, head_center)]
        edges.append((vid, segs, head_center, tail_center))

    if not edges:
        return

    # 收集游离 UMLTextView 并按"是否像多重性"分流
    mult_texts: list[tuple[tuple[float, float], str]] = []
    label_texts: list[tuple[tuple[float, float], str]] = []
    for v in _walk(diag_node.get("ownedViews") or []):
        if not isinstance(v, dict):
            continue
        if v.get("_type") != "UMLTextView":
            continue
        text = v.get("text")
        if not isinstance(text, str) or not text.strip():
            continue
        c = _view_center(v)
        if c is None:
            continue
        text_clean = text.strip()
        if _is_multiplicity_text(text_clean):
            mult_texts.append((c, text_clean))
        else:
            label_texts.append((c, text_clean))

    # === 多重性：二部贪心匹配 ===
    # 候选三元组 (combined_distance, text_idx, edge_idx, end_kind)
    # combined_distance = 文本到线距离 + 0.5 * 文本到端点距离（线优先、端兜底）
    candidates: list[tuple[float, int, int, str]] = []
    for ti, (tc, _) in enumerate(mult_texts):
        for ei, (_eid, segs, hc, tcr) in enumerate(edges):
            d_line = _dist_p_polyline(tc, segs)
            if d_line > line_distance_threshold:
                continue
            for end_kind, ec in (("head", hc), ("tail", tcr)):
                if ec is None:
                    continue
                d_end = _dist_p2p(tc, ec)
                candidates.append((d_line + 0.5 * d_end, ti, ei, end_kind))
    candidates.sort()
    used_text: set[int] = set()
    used_slot: set[tuple[int, str]] = set()
    for _score, ti, ei, ek in candidates:
        if ti in used_text or (ei, ek) in used_slot:
            continue
        eid = edges[ei][0]
        rel = relation_by_view_id.get(eid)
        if rel is None:
            continue
        text_clean = mult_texts[ti][1]
        if ek == "head":
            if not rel.multiplicity_target:
                rel.multiplicity_target = text_clean
                used_text.add(ti)
                used_slot.add((ei, ek))
        else:
            if not rel.multiplicity_source:
                rel.multiplicity_source = text_clean
                used_text.add(ti)
                used_slot.add((ei, ek))

    # === 标签：拼接到最近边的 relation.label ===
    for tc, text_clean in label_texts:
        best_d = float("inf")
        best_ei = -1
        for ei, (_eid, segs, _hc, _tcr) in enumerate(edges):
            d = _dist_p_polyline(tc, segs)
            if d < best_d:
                best_d = d
                best_ei = ei
        if best_ei < 0 or best_d > line_distance_threshold:
            continue
        eid = edges[best_ei][0]
        rel = relation_by_view_id.get(eid)
        if rel is None:
            continue
        rel.label = f"{rel.label} {text_clean}".strip() if rel.label else text_clean


def _find_end(assoc: dict, key: str) -> dict | None:
    """取出 end1 / end2 节点本身（含 multiplicity / aggregation 等）。"""
    e = assoc.get(key)
    if isinstance(e, dict):
        return e
    return None


def _classify_association(end1: dict | None, end2: dict | None) -> str:
    """根据 aggregation 字段把 association 细化成 aggregation/composition/association。"""
    for end in (end1, end2):
        if not end:
            continue
        agg = (end.get("aggregation") or "").lower()
        if agg == "shared":
            return "aggregation"
        if agg == "composite":
            return "composition"
    return "association"


def _collect_visible_model_ids(diag_node: dict) -> set[str]:
    """从 diagram 的 ownedViews 中提取所有 model.$ref，圈定该图涉及的元素 id 集合。

    返回空集表示无法判断（兜底：全收）。
    """
    ids: set[str] = set()
    views = diag_node.get("ownedViews") or []
    for view in _walk(views):
        m = view.get("model") if isinstance(view, dict) else None
        rid = _ref(m)
        if rid:
            ids.add(rid)
    return ids


def _scope_or_none(diag_node: dict) -> set[str] | None:
    """该 diagram 真正可见的 model id 集合；若 diagram 无任何 view 则返回 None。

    返回 None 时表示无法做 view 过滤，调用方应退化为按 `_type` 全收（兜底）。
    返回非空集合时，调用方应严格只接收集合内的 id。
    """
    ids = _collect_visible_model_ids(diag_node)
    return ids or None


def _attach_subject_membership(
    diag_node: dict, idx: dict[str, dict],
    elements: list[UmlElement], containers: list[UmlContainer],
) -> None:
    """用例图中：根据 SubjectView 的 containedViews 推断哪些用例属于该 subject。

    复杂度高时退化为：把所有 use_case 元素都挂到唯一 subject 下（best-effort）。
    """
    if len(containers) == 1 and elements:
        sole = containers[0]
        sole_members = []
        for e in elements:
            if e.type == "use_case":
                e.container = sole.id
                sole_members.append(e.id)
        sole.members = sole_members


def _dedup_relations(rels: list[UmlRelation]) -> list[UmlRelation]:
    """仅按关系 id 去重，**不能**按 (type, source, target) 去重。

    学生可能重复画同一对象间的关联（UC1.5 参与者冗余控制 / UC4.2 参与关联正确性
    等指标就是评判这个），按 (type, src, tgt) 去重会把学生的真实错误抹掉。
    同一 _id 在 mdj 中唯一，此函数实际等价于恒等变换，保留仅作为防御性写法。
    """
    seen_ids: set[str] = set()
    out: list[UmlRelation] = []
    for r in rels:
        if r.id in seen_ids:
            continue
        seen_ids.add(r.id)
        out.append(r)
    return out


# ---------------------------- 顶层 API ----------------------------


def parse_mdj(data: dict, source_file: str = "") -> list[UmlDiagram]:
    """解析整个 mdj JSON，返回所有图。"""
    idx = _build_index(data)
    diagrams: list[UmlDiagram] = []
    for n in idx.values():
        t = n.get("_type", "")
        if t not in _DIAGRAM_TYPE_MAP:
            continue
        # 部分模板会留下默认空的 UMLClassDiagram，跳过完全空的
        if not (n.get("ownedViews") or n.get("ownedElements")):
            continue
        diag_type = _DIAGRAM_TYPE_MAP[t]
        if diag_type == "use_case":
            diagrams.append(_parse_use_case_diagram(n, idx, source_file))
        elif diag_type == "class":
            diagrams.append(_parse_class_diagram(n, idx, source_file))
        elif diag_type == "sequence":
            diagrams.append(_parse_sequence_diagram(n, idx, source_file))
        elif diag_type == "swimlane":
            diagrams.append(_parse_activity_diagram(n, idx, source_file))
    return diagrams


def parse_mdj_file(path: str | Path) -> list[UmlDiagram]:
    """从 `.mdj` 文件路径解析。"""
    p = Path(path)
    with p.open(encoding="utf-8") as f:
        data = json.load(f)
    return parse_mdj(data, source_file=str(p))


# ---------------------------- CLI ----------------------------


def _cli() -> None:
    import argparse

    ap = argparse.ArgumentParser(description="Parse a StarUML .mdj into UML IR")
    ap.add_argument("path", help="Path to .mdj file")
    ap.add_argument("--json", action="store_true", help="Output JSON instead of text")
    args = ap.parse_args()

    diagrams = parse_mdj_file(args.path)
    if not diagrams:
        print("(no diagrams found)")
        return
    for d in diagrams:
        if args.json:
            print(d.model_dump_json(indent=2))
        else:
            print(d.to_textual())
        print()


if __name__ == "__main__":
    _cli()
