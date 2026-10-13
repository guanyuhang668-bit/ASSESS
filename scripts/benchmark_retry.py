#!/root/UML图工具/uml-grader/backend/.venv/bin/python3
"""补跑 benchmark 中因额度不足等原因失败的任务。

读取 detail.csv，找出某模型缺失的 (student, diagram_type) 组合，重新评分并追加到 detail.csv。
然后重新生成 summary.csv 和 report.txt。

用法:
    cd /root/UML图工具/uml-grader
    python scripts/benchmark_retry.py [model_name]
    
    model_name 可选，默认补跑所有有缺失的模型。
"""

from __future__ import annotations

import asyncio
import csv
import json
import logging
import math
import os
import re
import sys
import time
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent / "backend"
sys.path.insert(0, str(BACKEND_DIR))
os.environ.setdefault("APP_ENV", "dev")

from app.services.grading.cot_runner import CotRunner
from app.services.grading.rubric_loader import load_rubric_from_yaml, RubricDef
from app.services.llm.factory import load_all_clients
from app.services.parser_svc import parse_submission, pick_diagram

import openpyxl

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("benchmark_retry")

# Import shared config from main script
sys.path.insert(0, str(Path(__file__).resolve().parent))
from benchmark_models import (
    DIAGRAM_TYPES, DIAGRAM_CN, DIAGRAM_FOLDER_KW,
    GT_FILES, GT_DIR, RUBRIC_DIR, OUTPUT_DIR, MDJ_ROOT,
    STUDENT_NAME_MAP,
    load_teacher_scores, find_mdj, compute_metrics,
    TeacherScore, ModelScore, grade_one,
)


def load_existing_detail() -> list[dict]:
    """加载已有的 detail.csv"""
    path = OUTPUT_DIR / "detail.csv"
    if not path.exists():
        return []
    with open(path, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def find_missing_tasks(existing: list[dict], all_tasks: list[tuple], model_names: list[str]) -> dict[str, list[tuple]]:
    """找出每个模型缺失的任务。"""
    # existing 中已有的 (student, diagram_type, model) 组合
    done_keys: set[tuple[str, str, str]] = set()
    for row in existing:
        done_keys.add((row["student"], row["diagram_type"], row["model"]))

    missing: dict[str, list[tuple]] = {}
    for model_name in model_names:
        model_missing = []
        for stu_name, folder, dt, mdj_path in all_tasks:
            if (stu_name, dt, model_name) not in done_keys:
                model_missing.append((stu_name, folder, dt, mdj_path))
        if model_missing:
            missing[model_name] = model_missing
    return missing


def regenerate_reports(all_model_scores: list[dict], teacher_map: dict):
    """从完整的 detail 数据重新生成 summary.csv 和 report.txt。"""
    # 获取所有模型名
    model_names = sorted(set(r["model"] for r in all_model_scores))

    summary_rows = []
    for model_name in model_names:
        for dt in DIAGRAM_TYPES:
            teacher_vals = []
            model_vals = []
            na_match = 0
            na_total = 0
            for row in all_model_scores:
                if row["model"] != model_name or row["diagram_type"] != dt:
                    continue
                ts_val = teacher_map.get((row["student"], row["diagram_type"], row["code"]))
                model_score = float(row["model_score"]) if row["model_score"] else 0
                model_na = row["model_na"] == "True"

                if ts_val is None:
                    na_total += 1
                    if model_na:
                        na_match += 1
                    continue
                if model_na:
                    model_vals.append(0.0)
                    teacher_vals.append(ts_val)
                else:
                    teacher_vals.append(ts_val)
                    model_vals.append(model_score)

            metrics = compute_metrics(teacher_vals, model_vals)
            na_accuracy = na_match / na_total if na_total > 0 else float("nan")
            summary_rows.append({
                "model": model_name,
                "diagram_type": dt,
                "n": metrics["n"],
                "mae": round(metrics["mae"], 3),
                "rmse": round(metrics["rmse"], 3),
                "pearson": round(metrics["pearson"], 3),
                "agree_1pt": round(metrics["agree_1"] * 100, 1),
                "agree_2pt": round(metrics["agree_2"] * 100, 1),
                "na_total": na_total,
                "na_match": na_match,
                "na_accuracy": round(na_accuracy * 100, 1) if not math.isnan(na_accuracy) else "N/A",
            })

        # Overall
        all_t = []
        all_m = []
        for row in all_model_scores:
            if row["model"] != model_name:
                continue
            ts_val = teacher_map.get((row["student"], row["diagram_type"], row["code"]))
            model_na = row["model_na"] == "True"
            if ts_val is None or model_na:
                continue
            all_t.append(ts_val)
            all_m.append(float(row["model_score"]))
        overall = compute_metrics(all_t, all_m)
        summary_rows.append({
            "model": model_name, "diagram_type": "ALL",
            "n": overall["n"], "mae": round(overall["mae"], 3),
            "rmse": round(overall["rmse"], 3), "pearson": round(overall["pearson"], 3),
            "agree_1pt": round(overall["agree_1"] * 100, 1),
            "agree_2pt": round(overall["agree_2"] * 100, 1),
            "na_total": "", "na_match": "", "na_accuracy": "",
        })

    # Write summary
    summary_path = OUTPUT_DIR / "summary.csv"
    with open(summary_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=[
            "model", "diagram_type", "n", "mae", "rmse", "pearson",
            "agree_1pt", "agree_2pt", "na_total", "na_match", "na_accuracy",
        ])
        w.writeheader()
        w.writerows(summary_rows)

    # Write report
    report_lines = ["=" * 60, "模型基底选择评估报告（含补跑）", "=" * 60, ""]
    report_lines.append(f"{'模型':<20} {'MAE':>6} {'RMSE':>6} {'Pearson':>8} {'±1分准确率':>10} {'±2分准确率':>10} {'样本数':>6}")
    report_lines.append("-" * 60)
    overall_rows = [r for r in summary_rows if r["diagram_type"] == "ALL"]
    overall_rows.sort(key=lambda r: r["mae"])
    for r in overall_rows:
        report_lines.append(
            f"{r['model']:<20} {r['mae']:>6.3f} {r['rmse']:>6.3f} {r['pearson']:>8.3f} "
            f"{r['agree_1pt']:>9.1f}% {r['agree_2pt']:>9.1f}% {r['n']:>6}"
        )
    report_lines.append("")
    report_lines.append("=" * 60)
    report_lines.append("按图类型分解：")
    for dt in DIAGRAM_TYPES:
        report_lines.append(f"\n--- {DIAGRAM_CN[dt]} ---")
        dt_rows = [r for r in summary_rows if r["diagram_type"] == dt]
        dt_rows.sort(key=lambda r: r["mae"])
        for r in dt_rows:
            report_lines.append(
                f"  {r['model']:<20} MAE={r['mae']:.3f}  RMSE={r['rmse']:.3f}  "
                f"Pearson={r['pearson']:.3f}  ±1分={r['agree_1pt']:.1f}%  "
                f"±2分={r['agree_2pt']:.1f}%  N/A识别={r['na_accuracy']}"
            )
    report_lines.append("")
    best = overall_rows[0] if overall_rows else None
    if best:
        report_lines.append(f"★ 推荐模型: {best['model']} (MAE={best['mae']:.3f})")

    report_text = "\n".join(report_lines)
    with open(OUTPUT_DIR / "report.txt", "w", encoding="utf-8") as f:
        f.write(report_text)
    print("\n" + report_text)


async def main():
    target_model = sys.argv[1] if len(sys.argv) > 1 else None

    # Load teacher scores
    teacher_scores = load_teacher_scores()
    teacher_map = {}
    for ts in teacher_scores:
        teacher_map[(ts.student_name, ts.diagram_type, ts.code)] = ts.score

    # Load rubrics
    rubrics = {}
    for dt in DIAGRAM_TYPES:
        rubrics[dt] = load_rubric_from_yaml(RUBRIC_DIR / f"{dt}.yaml")

    # Load clients
    clients = load_all_clients(BACKEND_DIR / "configs" / "models.yaml")
    clients = {k: v for k, v in clients.items() if k != "mock"}

    if target_model:
        clients = {k: v for k, v in clients.items() if k == target_model}

    # Build all tasks
    all_tasks = []
    seen = set()
    for ts in teacher_scores:
        key = (ts.student_name, ts.diagram_type)
        if key in seen:
            continue
        seen.add(key)
        folder = STUDENT_NAME_MAP.get(ts.student_name)
        if not folder:
            continue
        mdj = find_mdj(folder, ts.diagram_type)
        if not mdj:
            continue
        all_tasks.append((ts.student_name, folder, ts.diagram_type, mdj))

    # Load existing results
    existing = load_existing_detail()
    missing = find_missing_tasks(existing, all_tasks, list(clients.keys()))

    total_missing = sum(len(v) for v in missing.values())
    if total_missing == 0:
        logger.info("No missing tasks. Regenerating reports from existing data.")
        regenerate_reports(existing, teacher_map)
        return

    logger.info("Missing tasks: %s", {k: len(v) for k, v in missing.items()})

    # Run missing tasks
    new_rows = []
    for model_name, tasks in missing.items():
        client = clients[model_name]
        logger.info("=== Retrying %d tasks for %s ===", len(tasks), model_name)
        for i, (stu_name, folder, dt, mdj_path) in enumerate(tasks):
            logger.info("  [%d/%d] %s / %s", i + 1, len(tasks), stu_name, dt)
            t0 = time.time()
            scores = await grade_one(client, rubrics[dt], mdj_path, dt, stu_name)
            elapsed = time.time() - t0
            logger.info("    → %d criteria in %.1fs", len(scores), elapsed)
            for ms in scores:
                ts_val = teacher_map.get((ms.student_name, ms.diagram_type, ms.code))
                new_rows.append({
                    "student": ms.student_name,
                    "diagram_type": ms.diagram_type,
                    "code": ms.code,
                    "teacher_score": "" if ts_val is None else ts_val,
                    "model": ms.model_name,
                    "model_score": ms.score,
                    "model_na": ms.not_applicable,
                })

    # Append to detail.csv
    detail_path = OUTPUT_DIR / "detail.csv"
    with open(detail_path, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=[
            "student", "diagram_type", "code", "teacher_score", "model", "model_score", "model_na",
        ])
        w.writerows(new_rows)
    logger.info("Appended %d rows to detail.csv", len(new_rows))

    # Regenerate reports
    all_data = load_existing_detail()
    regenerate_reports(all_data, teacher_map)


if __name__ == "__main__":
    asyncio.run(main())
