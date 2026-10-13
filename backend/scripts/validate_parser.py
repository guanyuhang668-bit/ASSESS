#!/usr/bin/env python3
"""遍历所有 `.mdj` 样本，跑 parser，打印核对表格。

用法：
    python scripts/validate_parser.py ../完整/
    python scripts/validate_parser.py ../完整/ --verbose         # 额外打印每张图的文本表示
    python scripts/validate_parser.py ../完整/ --file 4.1.mdj    # 只看某一份

输出两张表：
1. **逐文件对比表**：每份 .mdj 的
   - raw（直接扫描 mdj 原始节点）：actor / usecase / class / lifeline / message / partition / action / association / include / extend / generalization / controlflow ...
   - parsed（parser 输出 IR 后的）：elements / containers / relations 各类计数
   若两侧数字不一致会在末尾加 `⚠` 标记，提示可能漏解析。

2. **汇总表**：4 类图分别统计平均/最大/最小元素与关系数，以及出现过的关系类型分布。

该脚本不做自动判定，只把数据摆出来让人眼核对。
"""

from __future__ import annotations

import argparse
import collections
import json
import sys
from pathlib import Path

# 让脚本能从仓库根目录运行
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from uml_grader.parsers.mdj import parse_mdj_file  # noqa: E402


# ---------- 原始 mdj 节点统计（对照组，不走 parser） ----------

RAW_TRACK_TYPES = [
    # 用例图
    "UMLActor", "UMLUseCase", "UMLUseCaseSubject",
    "UMLAssociation", "UMLInclude", "UMLExtend", "UMLGeneralization",
    # 类图
    "UMLClass", "UMLInterface", "UMLEnumeration", "UMLPackage",
    "UMLDependency", "UMLAbstraction", "UMLInterfaceRealization", "UMLRealization",
    # 时序图
    "UMLLifeline", "UMLMessage", "UMLCombinedFragment", "UMLInteractionOperand",
    # 活动 / 泳道
    "UMLActivityPartition", "UMLAction", "UMLOpaqueAction",
    "UMLInitialNode", "UMLActivityFinalNode", "UMLFlowFinalNode",
    "UMLDecisionNode", "UMLMergeNode", "UMLForkNode", "UMLJoinNode",
    "UMLControlFlow", "UMLObjectFlow",
]


def raw_count(path: Path) -> dict[str, int]:
    """直接扫 mdj，统计感兴趣的节点数量。"""
    with path.open(encoding="utf-8") as f:
        data = json.load(f)
    counts: collections.Counter = collections.Counter()
    stack = [data]
    while stack:
        n = stack.pop()
        if isinstance(n, dict):
            t = n.get("_type", "")
            if t in RAW_TRACK_TYPES:
                counts[t] += 1
            # 细分 association 的 aggregation / multiplicity
            if t == "UMLAssociation":
                for k in ("end1", "end2"):
                    e = n.get(k, {})
                    if isinstance(e, dict):
                        agg = (e.get("aggregation") or "").lower()
                        if agg in ("shared", "composite"):
                            counts[f"(assoc.aggregation={agg})"] += 1
                        if e.get("multiplicity"):
                            counts["(assoc.multiplicity)"] += 1
            stack.extend(n.values())
        elif isinstance(n, list):
            stack.extend(n)
    return dict(counts)


# ---------- parser 输出统计 ----------


def parsed_count(path: Path) -> dict:
    """跑 parser，按图类型汇总 IR 计数。"""
    diagrams = parse_mdj_file(path)
    by_type: dict[str, dict] = {}
    for d in diagrams:
        elem_by_type = collections.Counter(e.type for e in d.elements)
        rel_by_type = collections.Counter(r.type for r in d.relations)
        cont_by_type = collections.Counter(c.type for c in d.containers)
        by_type.setdefault(d.diagram_type, {
            "count": 0, "elements": collections.Counter(),
            "relations": collections.Counter(), "containers": collections.Counter(),
            "diagrams": [],
        })
        bucket = by_type[d.diagram_type]
        bucket["count"] += 1
        bucket["elements"].update(elem_by_type)
        bucket["relations"].update(rel_by_type)
        bucket["containers"].update(cont_by_type)
        bucket["diagrams"].append(d)
    return by_type


# ---------- 对比 & 报告 ----------


# 期望的"某类原始节点 → parser IR 中对应的元素/关系类型"对照，用于自动标警
RAW_TO_IR = {
    "UMLActor": ("element", "actor"),
    "UMLUseCase": ("element", "use_case"),
    "UMLUseCaseSubject": ("container", "system_boundary"),
    "UMLClass": ("element", "class"),
    "UMLInterface": ("element", "interface"),
    "UMLEnumeration": ("element", "enumeration"),
    "UMLLifeline": ("element", "lifeline"),
    "UMLCombinedFragment": ("container", "frame"),
    "UMLActivityPartition": ("container", "swimlane"),
    "UMLAction": ("element", "activity"),
    "UMLOpaqueAction": ("element", "activity"),
    "UMLInitialNode": ("element", "initial"),
    "UMLActivityFinalNode": ("element", "final"),
    "UMLFlowFinalNode": ("element", "final"),
    "UMLDecisionNode": ("element", "decision"),
    "UMLMergeNode": ("element", "merge"),
    "UMLForkNode": ("element", "fork"),
    "UMLJoinNode": ("element", "join"),
    "UMLInclude": ("relation", "include"),
    "UMLExtend": ("relation", "extend"),
    "UMLGeneralization": ("relation", "generalization"),
    "UMLDependency": ("relation", "dependency"),
    "UMLAbstraction": ("relation", "dependency"),
    "UMLInterfaceRealization": ("relation", "realization"),
    "UMLRealization": ("relation", "realization"),
    "UMLControlFlow": ("relation", "control_flow"),
    "UMLObjectFlow": ("relation", "object_flow"),
}

# UMLAssociation 可能映射到多个 IR 类型（association / aggregation / composition）
# UMLMessage 可能映射到 5 种（sync/async/reply/create/delete）
# 这两类特殊处理。


def summarise_parsed(by_type: dict) -> dict[str, int]:
    """把 parser 输出的所有 (category, ir_type) → 计数 展平。"""
    flat: dict[tuple[str, str], int] = {}
    for dt, bucket in by_type.items():
        for et, n in bucket["elements"].items():
            flat[("element", et)] = flat.get(("element", et), 0) + n
        for rt, n in bucket["relations"].items():
            flat[("relation", rt)] = flat.get(("relation", rt), 0) + n
        for ct, n in bucket["containers"].items():
            flat[("container", ct)] = flat.get(("container", ct), 0) + n
    return flat


def check_one_file(path: Path) -> tuple[list[str], list[str]]:
    """返回 (info_lines, warning_lines)。"""
    raw = raw_count(path)
    by_type = parsed_count(path)
    parsed_flat = summarise_parsed(by_type)

    info: list[str] = []
    warn: list[str] = []

    # 整体计数行
    diag_summary = "; ".join(
        f"{dt}×{b['count']} (e={sum(b['elements'].values())} r={sum(b['relations'].values())} c={sum(b['containers'].values())})"
        for dt, b in by_type.items()
    ) or "(no diagrams)"
    info.append(f"  [parsed] {diag_summary}")

    # raw 关键节点
    if raw:
        raw_str = ", ".join(f"{k}={v}" for k, v in sorted(raw.items()))
        info.append(f"  [raw   ] {raw_str}")

    # 对照标警
    # 1) 简单 1 对 1 类型
    for raw_t, (cat, ir_t) in RAW_TO_IR.items():
        if raw_t in raw:
            got = parsed_flat.get((cat, ir_t), 0)
            if got != raw[raw_t]:
                warn.append(
                    f"  ⚠ {path.name}: {raw_t}={raw[raw_t]} 但 parsed {cat}/{ir_t}={got}"
                )

    # 2) UMLAssociation → association + aggregation + composition
    if "UMLAssociation" in raw:
        got = (
            parsed_flat.get(("relation", "association"), 0)
            + parsed_flat.get(("relation", "aggregation"), 0)
            + parsed_flat.get(("relation", "composition"), 0)
        )
        if got != raw["UMLAssociation"]:
            warn.append(
                f"  ⚠ {path.name}: UMLAssociation={raw['UMLAssociation']} "
                f"但 parsed association+aggregation+composition={got}"
            )

    # 3) UMLMessage → 5 种消息类型
    if "UMLMessage" in raw:
        got = sum(
            parsed_flat.get(("relation", k), 0)
            for k in ("message_sync", "message_async", "message_return",
                      "message_create", "message_delete")
        )
        if got != raw["UMLMessage"]:
            warn.append(
                f"  ⚠ {path.name}: UMLMessage={raw['UMLMessage']} "
                f"但 parsed 5种消息合计={got}"
            )

    return info, warn


# ---------- 主流程 ----------


def main() -> None:
    ap = argparse.ArgumentParser(description="Validate mdj parser against raw samples")
    ap.add_argument("root", type=Path, help="样本根目录（如 ../完整）")
    ap.add_argument("--file", default=None, help="只处理文件名含该关键字的样本")
    ap.add_argument("--verbose", action="store_true", help="额外打印每张图的 textual 表示")
    args = ap.parse_args()

    if not args.root.exists():
        print(f"[!] 目录不存在: {args.root}", file=sys.stderr)
        sys.exit(1)

    files = sorted(args.root.rglob("*.mdj"))
    if args.file:
        files = [p for p in files if args.file in p.name]
    if not files:
        print("[!] 没有找到 .mdj 文件")
        sys.exit(1)

    total = len(files)
    print(f"扫描 {total} 份 .mdj 样本\n")

    # 全局汇总（按图类型）
    overall: dict[str, dict] = {}
    warnings_all: list[str] = []

    for i, p in enumerate(files, 1):
        rel = p.relative_to(args.root)
        print(f"[{i:2d}/{total}] {rel}")
        try:
            info, warn = check_one_file(p)
        except Exception as e:
            print(f"  ✗ parser 崩溃: {e}")
            warnings_all.append(f"  ⚠ {p.name}: parser 崩溃 {e}")
            continue
        for line in info:
            print(line)
        warnings_all.extend(warn)

        # 累加到 overall
        by_type = parsed_count(p)
        for dt, bucket in by_type.items():
            o = overall.setdefault(dt, {
                "n_diagrams": 0, "n_files": 0,
                "elements": collections.Counter(),
                "relations": collections.Counter(),
                "containers": collections.Counter(),
                "elem_per_diag": [], "rel_per_diag": [],
            })
            o["n_diagrams"] += bucket["count"]
            o["n_files"] += 1
            o["elements"].update(bucket["elements"])
            o["relations"].update(bucket["relations"])
            o["containers"].update(bucket["containers"])
            for d in bucket["diagrams"]:
                o["elem_per_diag"].append(len(d.elements))
                o["rel_per_diag"].append(len(d.relations))
                if args.verbose:
                    print("  ---- textual ----")
                    for line in d.to_textual().splitlines():
                        print(f"     {line}")

    # ============ 汇总表 ============
    print()
    print("=" * 72)
    print("# 汇总（按图类型）")
    print("=" * 72)
    for dt in ("use_case", "class", "sequence", "swimlane"):
        if dt not in overall:
            continue
        o = overall[dt]
        elems = o["elem_per_diag"] or [0]
        rels = o["rel_per_diag"] or [0]
        print(
            f"\n[{dt}]  文件={o['n_files']}  图数={o['n_diagrams']}  "
            f"元素/图 avg={sum(elems)/len(elems):.1f} "
            f"(min={min(elems)}, max={max(elems)})  "
            f"关系/图 avg={sum(rels)/len(rels):.1f} "
            f"(min={min(rels)}, max={max(rels)})"
        )
        if o["elements"]:
            print("  元素类型:   " + ", ".join(f"{k}={v}" for k, v in sorted(o["elements"].items(), key=lambda x: -x[1])))
        if o["relations"]:
            print("  关系类型:   " + ", ".join(f"{k}={v}" for k, v in sorted(o["relations"].items(), key=lambda x: -x[1])))
        if o["containers"]:
            print("  容器类型:   " + ", ".join(f"{k}={v}" for k, v in sorted(o["containers"].items(), key=lambda x: -x[1])))

    # ============ 警告 ============
    print()
    print("=" * 72)
    print(f"# 警告（parser 输出与 mdj 原始节点数不一致的情形）")
    print("=" * 72)
    if warnings_all:
        for w in warnings_all:
            print(w)
    else:
        print("  ✓ 全部一致，未发现丢失")


if __name__ == "__main__":
    main()
