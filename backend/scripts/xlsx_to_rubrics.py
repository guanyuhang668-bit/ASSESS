#!/usr/bin/env python3
"""把 `UML指标.xlsx` 转成 4 份 YAML 评分指标。

输入：单个 sheet，4 段（用例图 / 类图 / 时序图 / 泳道图），每段含：
- 一级指标（如 'UC1 识别参与者'），第一列；空表示沿用上一行
- 二级指标（如 'UC1.1 主要参与者完整性'），第二列
- 详细说明，第三列
- 各班错误数（实验报告 4 班 + 期中试卷 N 班），第 4 列起

输出：configs/rubrics/{use_case,class,sequence,swimlane}.yaml

每条指标的字段：
- code: 'UC1.1'
- name: '主要参与者完整性'
- parent_code / parent_name: 一级指标
- description: 详细说明
- error_freq_total: 错误总频次（用于 prompt 中标注"高频错误模式"）
- error_freq_by_class: 各班分布
- weight: 默认 1.0（占位，后续教研会决定）
- scoring_hint: 占位（人工补充）
- common_errors: 占位（从试批样本中补充）
- not_applicable_when: 占位（如时序图控制结构在无分支题目中 N/A）

依赖：仅 stdlib（zipfile + xml）+ PyYAML。
"""

from __future__ import annotations

import argparse
import re
import sys
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path

try:
    import yaml
except ImportError:
    print("[!] 缺少 PyYAML，请先 `pip install pyyaml`", file=sys.stderr)
    sys.exit(1)


NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"

# 4 类图在 sheet 中的段标题；用于自动定位起止行
DIAGRAM_HEADERS: list[tuple[str, str]] = [
    ("用例图", "use_case"),
    ("类图", "class"),
    ("时序图", "sequence"),
    ("泳道图", "swimlane"),
]


def read_sheet(xlsx_path: Path) -> list[list[str]]:
    """读取第一个 sheet 的所有行（去掉空行）。"""
    with zipfile.ZipFile(xlsx_path) as z:
        ss_root = ET.fromstring(z.read("xl/sharedStrings.xml"))
        strings = [
            "".join(t.text or "" for t in si.iter(NS + "t"))
            for si in ss_root.iter(NS + "si")
        ]
        sheet_root = ET.fromstring(z.read("xl/worksheets/sheet1.xml"))

    rows: list[list[str]] = []
    for row in sheet_root.iter(NS + "row"):
        # 用 r 属性记录列号，确保稀疏列对齐
        max_col = 0
        cells: dict[int, str] = {}
        for c in row.findall(NS + "c"):
            ref = c.attrib.get("r", "")
            col_idx = _col_letter_to_idx(re.match(r"[A-Z]+", ref).group(0)) if ref else len(cells)
            v = c.find(NS + "v")
            if v is None:
                continue
            text = (
                strings[int(v.text)] if c.attrib.get("t") == "s" else (v.text or "")
            )
            cells[col_idx] = text
            max_col = max(max_col, col_idx)
        flat = [cells.get(i, "") for i in range(max_col + 1)]
        rows.append(flat)
    return rows


def _col_letter_to_idx(letters: str) -> int:
    """A->0, B->1, ..., Z->25, AA->26 ..."""
    n = 0
    for ch in letters:
        n = n * 26 + (ord(ch) - ord("A") + 1)
    return n - 1


def split_by_diagram(rows: list[list[str]]) -> dict[str, tuple[int, int]]:
    """根据段标题定位每个图类型的行区间 (start_inclusive, end_exclusive)。

    跳过 header 行本身，从下一行开始算指标行。
    """
    # 找到每个图类型的标题行
    starts: list[tuple[int, str]] = []
    for i, r in enumerate(rows):
        if not r:
            continue
        head = r[0].strip() if r[0] else ""
        for label, key in DIAGRAM_HEADERS:
            if head == label:
                starts.append((i, key))
                break

    out: dict[str, tuple[int, int]] = {}
    for idx, (row_i, key) in enumerate(starts):
        end = starts[idx + 1][0] if idx + 1 < len(starts) else len(rows)
        out[key] = (row_i + 1, end)  # 跳过段标题行
    return out


CODE_RE = re.compile(r"^([A-Z]{2,3}\d+(?:\.\d+)?)[\.\s\u3000]+(.*)$")


def split_code_and_name(cell: str) -> tuple[str, str]:
    """把 'UC1.1 主要参与者完整性' 拆成 ('UC1.1', '主要参与者完整性')。"""
    cell = cell.strip()
    m = CODE_RE.match(cell)
    if m:
        return m.group(1), m.group(2).strip()
    return "", cell


def parse_one_diagram(rows: list[list[str]], header_row: list[str]) -> list[dict]:
    """把指定区段的行解析为指标 dict 列表。

    `header_row` 用来识别哪些列是各班错误数（取第 4 列起的所有非空表头）。
    """
    # 假设第二行（紧跟 use_case 段标题之前那行）是表头：
    # ['一级指标','二级指标','详细说明','','12401班','12402班',...]
    class_cols: list[tuple[int, str]] = []
    for col_i, label in enumerate(header_row):
        if col_i < 3:
            continue
        if label and "班" in label:
            class_cols.append((col_i, label.strip()))

    out: list[dict] = []
    cur_parent_code = ""
    cur_parent_name = ""

    for r in rows:
        if not r or all(not c for c in r):
            continue
        col0 = r[0].strip() if len(r) > 0 and r[0] else ""
        col1 = r[1].strip() if len(r) > 1 and r[1] else ""
        col2 = r[2].strip() if len(r) > 2 and r[2] else ""

        # 一级指标更新
        if col0:
            pc, pn = split_code_and_name(col0)
            cur_parent_code = pc or col0
            cur_parent_name = pn or col0

        if not col1:
            continue
        code, name = split_code_and_name(col1)
        if not code:
            # 不是规范的"XX1.1 名称"，跳过
            continue

        # 错误频次
        freq_by_class: dict[str, int] = {}
        total = 0
        for col_i, label in class_cols:
            cell = r[col_i].strip() if col_i < len(r) and r[col_i] else ""
            if cell:
                try:
                    n = int(float(cell))
                except ValueError:
                    n = 0
                if n > 0:
                    freq_by_class[label] = n
                    total += n

        out.append(
            {
                "code": code,
                "name": name,
                "parent_code": cur_parent_code,
                "parent_name": cur_parent_name,
                "description": col2,
                "error_freq_total": total,
                "error_freq_by_class": freq_by_class,
                "weight": 1.0,
                "scoring_hint": "",
                "common_errors": [],
                "not_applicable_when": "",
            }
        )
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description="Convert UML指标.xlsx to YAML rubrics")
    ap.add_argument("xlsx", type=Path, help="UML指标.xlsx 路径")
    ap.add_argument("out_dir", type=Path, help="输出目录（如 configs/rubrics/）")
    args = ap.parse_args()

    rows = read_sheet(args.xlsx)
    spans = split_by_diagram(rows)

    # 取头几行的"列表头"行（含 12401班 等）作为 class column 识别基准
    # 表里 Row 1 就是这一行
    header_row = rows[1] if len(rows) > 1 else []

    args.out_dir.mkdir(parents=True, exist_ok=True)

    summary = []
    for key, (start, end) in spans.items():
        criteria = parse_one_diagram(rows[start:end], header_row)
        out_path = args.out_dir / f"{key}.yaml"
        with out_path.open("w", encoding="utf-8") as f:
            yaml.safe_dump(
                {
                    "diagram_type": key,
                    "source": str(args.xlsx),
                    "criteria": criteria,
                },
                f,
                allow_unicode=True,
                sort_keys=False,
                width=120,
            )
        summary.append((key, len(criteria), out_path))
        print(f"[OK] {key:10s} -> {out_path}  ({len(criteria)} criteria)")

    # 简单核对
    print("\n=== Summary ===")
    for key, n, p in summary:
        print(f"  {key:10s} : {n:3d} criteria  ({p})")


if __name__ == "__main__":
    main()
