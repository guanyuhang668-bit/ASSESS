#!/root/UML图工具/uml-grader/backend/.venv/bin/python3
"""从 benchmark_results/detail.csv 生成论文所需的深度分析图表。

输出到 scripts/benchmark_results/figures/ 目录：
  1. bias_boxplot.png          — 严苛/宽松偏差箱线图 (RQ2)
  2. bias_by_diagram.png       — 按图类型的偏差箱线图 (RQ2)
  3. criterion_mae_heatmap.png — 一级指标 × 模型 MAE 热力图 (RQ2)
  4. radar_by_diagram.png      — 按图类型的一级指标 MAE 雷达图 (RQ2)
  5. na_confusion.png          — N/A 混淆矩阵 (RQ1)
  6. score_distribution.png    — 教师 vs 模型打分分布 (RQ1)
  7. criterion_bias_detail.png — 逐二级指标偏差热力图 (RQ2)
  8. analysis_report.txt       — 文字分析报告
"""

from __future__ import annotations

import csv
import math
import os
import re
import sys
from collections import defaultdict
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker
import numpy as np
import pandas as pd
import seaborn as sns

# 中文字体
plt.rcParams["font.sans-serif"] = ["WenQuanYi Micro Hei", "SimHei", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False

RESULT_DIR = Path(__file__).resolve().parent / "benchmark_results"
FIG_DIR = RESULT_DIR / "figures"
FIG_DIR.mkdir(parents=True, exist_ok=True)

DIAGRAM_CN = {"use_case": "用例图", "class": "类图", "sequence": "时序图", "swimlane": "泳道图"}
DIAGRAM_ORDER = ["use_case", "class", "sequence", "swimlane"]

# ======================= 加载数据 =======================

def load_detail() -> pd.DataFrame:
    df = pd.read_csv(RESULT_DIR / "detail.csv")
    # teacher_score 为空 → N/A
    df["teacher_na"] = df["teacher_score"].isna() | (df["teacher_score"] == "")
    df["teacher_score_num"] = pd.to_numeric(df["teacher_score"], errors="coerce")
    df["model_score_num"] = pd.to_numeric(df["model_score"], errors="coerce")
    df["model_na_bool"] = df["model_na"].astype(str).str.strip().str.lower() == "true"
    # 偏差 = 模型 - 教师 (正=宽松, 负=严苛)
    mask = (~df["teacher_na"]) & (~df["model_na_bool"])
    df.loc[mask, "bias"] = df.loc[mask, "model_score_num"] - df.loc[mask, "teacher_score_num"]
    # 一级指标 code: UC1, CC2, SC3 etc.
    df["parent_code"] = df["code"].str.extract(r"^([A-Z]{2}\d+)")[0]
    df["diagram_cn"] = df["diagram_type"].map(DIAGRAM_CN)
    return df


# ======================= 1. 严苛/宽松偏差箱线图 =======================

def plot_bias_boxplot(df: pd.DataFrame):
    """整体偏差箱线图：每个模型一个 box。"""
    data = df.dropna(subset=["bias"])
    fig, ax = plt.subplots(figsize=(8, 5))
    models = sorted(data["model"].unique())
    box_data = [data[data["model"] == m]["bias"].values for m in models]
    bp = ax.boxplot(box_data, labels=models, patch_artist=True, showmeans=True,
                    meanprops=dict(marker="D", markerfacecolor="red", markersize=6))
    color_map = {"deepseek_v3": "#4C72B0", "gemini_3_flash": "#55A868", "gpt4o": "#C44E52", "qwen_3_max": "#8172B2"}
    for patch, m in zip(bp["boxes"], models):
        c = color_map.get(m, "#999")
        patch.set_facecolor(c)
        patch.set_alpha(0.6)
    ax.axhline(0, color="black", linewidth=0.8, linestyle="--")
    ax.set_ylabel("偏差 (模型分 − 教师分)")
    ax.set_title("模型评分偏差分布（正=宽松，负=严苛）")
    ax.grid(axis="y", alpha=0.3)
    fig.tight_layout()
    fig.savefig(FIG_DIR / "bias_boxplot.png", dpi=150)
    plt.close(fig)
    print("  ✓ bias_boxplot.png")


def plot_bias_by_diagram(df: pd.DataFrame):
    """按图类型分面的偏差箱线图。"""
    data = df.dropna(subset=["bias"]).copy()
    data["diagram_cn"] = pd.Categorical(
        data["diagram_cn"],
        categories=[DIAGRAM_CN[d] for d in DIAGRAM_ORDER],
        ordered=True,
    )
    fig, axes = plt.subplots(1, 4, figsize=(16, 5), sharey=True)
    models = sorted(data["model"].unique())
    colors = {"deepseek_v3": "#4C72B0", "gemini_3_flash": "#55A868", "gpt4o": "#C44E52", "qwen_3_max": "#8172B2"}
    for ax, dt in zip(axes, DIAGRAM_ORDER):
        cn = DIAGRAM_CN[dt]
        sub = data[data["diagram_type"] == dt]
        box_data = [sub[sub["model"] == m]["bias"].values for m in models]
        bp = ax.boxplot(box_data, labels=[m.replace("_", "\n") for m in models],
                        patch_artist=True, showmeans=True,
                        meanprops=dict(marker="D", markerfacecolor="red", markersize=5))
        for patch, m in zip(bp["boxes"], models):
            patch.set_facecolor(colors.get(m, "#999"))
            patch.set_alpha(0.6)
        ax.axhline(0, color="black", linewidth=0.8, linestyle="--")
        ax.set_title(cn, fontsize=13)
        ax.grid(axis="y", alpha=0.3)
    axes[0].set_ylabel("偏差 (模型分 − 教师分)")
    fig.suptitle("各图类型的模型评分偏差", fontsize=14, y=1.02)
    fig.tight_layout()
    fig.savefig(FIG_DIR / "bias_by_diagram.png", dpi=150, bbox_inches="tight")
    plt.close(fig)
    print("  ✓ bias_by_diagram.png")


# ======================= 2. 一级指标 MAE 热力图 =======================

def plot_criterion_mae_heatmap(df: pd.DataFrame):
    """一级指标 × 模型的 MAE 热力图。"""
    data = df.dropna(subset=["bias"]).copy()
    data["abs_err"] = data["bias"].abs()
    pivot = data.groupby(["parent_code", "model"])["abs_err"].mean().unstack("model")
    # 按图类型排序
    prefix_order = []
    for dt in DIAGRAM_ORDER:
        codes = sorted([c for c in pivot.index if c.startswith({"use_case": "UC", "class": "CC", "sequence": "SC", "swimlane": "SW"}[dt])])
        prefix_order.extend(codes)
    pivot = pivot.reindex(prefix_order)
    pivot = pivot.dropna(how="all")

    fig, ax = plt.subplots(figsize=(8, max(6, len(pivot) * 0.35)))
    sns.heatmap(pivot, annot=True, fmt=".2f", cmap="YlOrRd", ax=ax,
                linewidths=0.5, cbar_kws={"label": "MAE"})
    ax.set_xlabel("模型")
    ax.set_ylabel("一级指标")
    ax.set_title("各一级指标 × 模型 MAE 热力图")
    fig.tight_layout()
    fig.savefig(FIG_DIR / "criterion_mae_heatmap.png", dpi=150)
    plt.close(fig)
    print("  ✓ criterion_mae_heatmap.png")


# ======================= 3. 雷达图 =======================

def plot_radar_by_diagram(df: pd.DataFrame):
    """每种图类型一个雷达图，比较各模型在一级指标上的 MAE。"""
    data = df.dropna(subset=["bias"]).copy()
    data["abs_err"] = data["bias"].abs()
    models = sorted(data["model"].unique())
    colors = {"deepseek_v3": "#4C72B0", "gemini_3_flash": "#55A868", "gpt4o": "#C44E52", "qwen_3_max": "#8172B2"}

    fig, axes = plt.subplots(2, 2, figsize=(12, 12), subplot_kw=dict(polar=True))
    dt_prefix = {"use_case": "UC", "class": "CC", "sequence": "SC", "swimlane": "SW"}

    for ax, dt in zip(axes.flat, DIAGRAM_ORDER):
        prefix = dt_prefix[dt]
        sub = data[data["diagram_type"] == dt]
        codes = sorted(sub["parent_code"].dropna().unique())
        codes = [c for c in codes if c.startswith(prefix)]
        if not codes:
            continue

        angles = np.linspace(0, 2 * np.pi, len(codes), endpoint=False).tolist()
        angles += angles[:1]

        for m in models:
            msub = sub[sub["model"] == m]
            vals = []
            for c in codes:
                v = msub[msub["parent_code"] == c]["abs_err"].mean()
                vals.append(v if not np.isnan(v) else 0)
            vals += vals[:1]
            ax.plot(angles, vals, "o-", linewidth=1.5, label=m, color=colors.get(m))
            ax.fill(angles, vals, alpha=0.1, color=colors.get(m))

        ax.set_xticks(angles[:-1])
        ax.set_xticklabels(codes, fontsize=9)
        ax.set_title(DIAGRAM_CN[dt], fontsize=13, pad=20)
        ax.set_rlabel_position(30)

    axes[0, 0].legend(loc="upper right", bbox_to_anchor=(1.3, 1.1), fontsize=9)
    fig.suptitle("各模型一级指标 MAE 雷达图（越小越好）", fontsize=14, y=1.02)
    fig.tight_layout()
    fig.savefig(FIG_DIR / "radar_by_diagram.png", dpi=150, bbox_inches="tight")
    plt.close(fig)
    print("  ✓ radar_by_diagram.png")


# ======================= 4. N/A 混淆矩阵 =======================

def plot_na_confusion(df: pd.DataFrame):
    """每个模型的 N/A 混淆矩阵。"""
    models = sorted(df["model"].unique())
    fig, axes = plt.subplots(1, len(models), figsize=(5 * len(models), 4))
    if len(models) == 1:
        axes = [axes]

    for ax, m in zip(axes, models):
        sub = df[df["model"] == m]
        # teacher_na vs model_na_bool
        tp = ((sub["teacher_na"]) & (sub["model_na_bool"])).sum()   # 两者都 N/A
        fp = ((~sub["teacher_na"]) & (sub["model_na_bool"])).sum()  # 模型误标 N/A
        fn = ((sub["teacher_na"]) & (~sub["model_na_bool"])).sum()  # 模型漏标 N/A
        tn = ((~sub["teacher_na"]) & (~sub["model_na_bool"])).sum() # 两者都非 N/A

        cm = np.array([[tn, fp], [fn, tp]])
        sns.heatmap(cm, annot=True, fmt="d", cmap="Blues", ax=ax,
                    xticklabels=["适用", "N/A"], yticklabels=["适用", "N/A"])
        ax.set_xlabel("模型判断")
        ax.set_ylabel("教师判断")
        ax.set_title(m)

    fig.suptitle("N/A 混淆矩阵", fontsize=14)
    fig.tight_layout()
    fig.savefig(FIG_DIR / "na_confusion.png", dpi=150)
    plt.close(fig)
    print("  ✓ na_confusion.png")


# ======================= 5. 打分分布对比 =======================

def plot_score_distribution(df: pd.DataFrame):
    """教师 vs 各模型的打分分布直方图。"""
    data = df[~df["teacher_na"]].copy()
    models = sorted(data["model"].unique())

    fig, axes = plt.subplots(1, len(models), figsize=(5 * len(models), 4), sharey=True)
    if len(models) == 1:
        axes = [axes]
    bins = np.arange(-0.5, 11.5, 1)

    for ax, m in zip(axes, models):
        sub = data[data["model"] == m]
        teacher = sub["teacher_score_num"].dropna()
        model = sub["model_score_num"].dropna()
        ax.hist(teacher, bins=bins, alpha=0.5, label="教师", color="#4C72B0", edgecolor="white")
        ax.hist(model, bins=bins, alpha=0.5, label=m, color="#C44E52", edgecolor="white")
        ax.set_xlabel("分数 (0-10)")
        ax.set_title(m)
        ax.legend()
        ax.xaxis.set_major_locator(ticker.MultipleLocator(2))

    axes[0].set_ylabel("频次")
    fig.suptitle("教师 vs 模型打分分布", fontsize=14)
    fig.tight_layout()
    fig.savefig(FIG_DIR / "score_distribution.png", dpi=150)
    plt.close(fig)
    print("  ✓ score_distribution.png")


# ======================= 6. 逐二级指标偏差热力图 =======================

def plot_criterion_bias_detail(df: pd.DataFrame):
    """二级指标 × 模型的平均偏差热力图（正=宽松，负=严苛）。"""
    data = df.dropna(subset=["bias"]).copy()
    pivot = data.groupby(["code", "model"])["bias"].mean().unstack("model")

    # 按图类型排序
    def sort_key(code):
        prefix_map = {"UC": 0, "CC": 1, "SC": 2, "SW": 3}
        m = re.match(r"([A-Z]{2})(\d+)\.(\d+)", code)
        if m:
            return (prefix_map.get(m.group(1), 9), int(m.group(2)), int(m.group(3)))
        return (9, 0, 0)

    pivot = pivot.reindex(sorted(pivot.index, key=sort_key))

    fig, ax = plt.subplots(figsize=(8, max(10, len(pivot) * 0.25)))
    sns.heatmap(pivot, annot=True, fmt=".1f", cmap="RdBu_r", center=0, ax=ax,
                linewidths=0.3, cbar_kws={"label": "平均偏差 (正=宽松, 负=严苛)"},
                annot_kws={"fontsize": 7})
    ax.set_xlabel("模型")
    ax.set_ylabel("二级指标")
    ax.set_title("各二级指标 × 模型 平均偏差（蓝=严苛, 红=宽松）")
    ax.tick_params(axis="y", labelsize=7)
    fig.tight_layout()
    fig.savefig(FIG_DIR / "criterion_bias_detail.png", dpi=150)
    plt.close(fig)
    print("  ✓ criterion_bias_detail.png")


# ======================= 7. 错误检测 Precision / Recall / F1 =======================

def _binary_error(scores: pd.Series, threshold: float = 10.0) -> pd.Series:
    """分数 < threshold → 检出错误 (True)；= threshold → 无错误 (False)。"""
    return scores < threshold


def compute_prf(df: pd.DataFrame) -> pd.DataFrame:
    """逐 (model, diagram_type, parent_code) 计算 P/R/F1。

    二值化规则：教师或模型给分 < 10 → 视为'检出错误'。
    排除 N/A（教师或模型标 N/A 的条目）。
    """
    data = df[(~df["teacher_na"]) & (~df["model_na_bool"])].copy()
    data["teacher_err"] = _binary_error(data["teacher_score_num"])
    data["model_err"] = _binary_error(data["model_score_num"])

    rows = []
    for (m, dt), g in data.groupby(["model", "diagram_type"]):
        # 整体
        tp = ((g["teacher_err"]) & (g["model_err"])).sum()
        fp = ((~g["teacher_err"]) & (g["model_err"])).sum()
        fn = ((g["teacher_err"]) & (~g["model_err"])).sum()
        tn = ((~g["teacher_err"]) & (~g["model_err"])).sum()
        p = tp / (tp + fp) if (tp + fp) > 0 else 0
        r = tp / (tp + fn) if (tp + fn) > 0 else 0
        f1 = 2 * p * r / (p + r) if (p + r) > 0 else 0
        rows.append({"model": m, "diagram_type": dt, "parent_code": "ALL",
                     "precision": p, "recall": r, "f1": f1,
                     "tp": tp, "fp": fp, "fn": fn, "tn": tn, "n": len(g)})

        # 按一级指标
        for pc, pg in g.groupby("parent_code"):
            tp2 = ((pg["teacher_err"]) & (pg["model_err"])).sum()
            fp2 = ((~pg["teacher_err"]) & (pg["model_err"])).sum()
            fn2 = ((pg["teacher_err"]) & (~pg["model_err"])).sum()
            tn2 = ((~pg["teacher_err"]) & (~pg["model_err"])).sum()
            p2 = tp2 / (tp2 + fp2) if (tp2 + fp2) > 0 else 0
            r2 = tp2 / (tp2 + fn2) if (tp2 + fn2) > 0 else 0
            f12 = 2 * p2 * r2 / (p2 + r2) if (p2 + r2) > 0 else 0
            rows.append({"model": m, "diagram_type": dt, "parent_code": pc,
                         "precision": p2, "recall": r2, "f1": f12,
                         "tp": tp2, "fp": fp2, "fn": fn2, "tn": tn2, "n": len(pg)})

    return pd.DataFrame(rows)


def plot_f1_radar(prf: pd.DataFrame):
    """按图类型的一级指标 F1 雷达图 (RQ2 §6.2(1))。"""
    models = sorted(prf["model"].unique())
    colors = {"deepseek_v3": "#4C72B0", "gemini_3_flash": "#55A868", "gpt4o": "#C44E52", "qwen_3_max": "#8172B2"}
    dt_prefix = {"use_case": "UC", "class": "CC", "sequence": "SC", "swimlane": "SW"}

    fig, axes = plt.subplots(2, 2, figsize=(12, 12), subplot_kw=dict(polar=True))
    detail = prf[prf["parent_code"] != "ALL"]

    for ax, dt in zip(axes.flat, DIAGRAM_ORDER):
        prefix = dt_prefix[dt]
        sub = detail[detail["diagram_type"] == dt]
        codes = sorted([c for c in sub["parent_code"].unique() if c.startswith(prefix)])
        if not codes:
            continue

        angles = np.linspace(0, 2 * np.pi, len(codes), endpoint=False).tolist()
        angles += angles[:1]

        for m in models:
            msub = sub[sub["model"] == m]
            vals = []
            for c in codes:
                row = msub[msub["parent_code"] == c]
                vals.append(row["f1"].values[0] if len(row) > 0 else 0)
            vals += vals[:1]
            ax.plot(angles, vals, "o-", linewidth=1.5, label=m, color=colors.get(m))
            ax.fill(angles, vals, alpha=0.1, color=colors.get(m))

        ax.set_xticks(angles[:-1])
        ax.set_xticklabels(codes, fontsize=9)
        ax.set_ylim(0, 1)
        ax.set_title(DIAGRAM_CN[dt], fontsize=13, pad=20)
        ax.set_rlabel_position(30)

    axes[0, 0].legend(loc="upper right", bbox_to_anchor=(1.3, 1.1), fontsize=9)
    fig.suptitle("各模型一级指标 F1 雷达图（越大越好）", fontsize=14, y=1.02)
    fig.tight_layout()
    fig.savefig(FIG_DIR / "f1_radar_by_diagram.png", dpi=150, bbox_inches="tight")
    plt.close(fig)
    print("  ✓ f1_radar_by_diagram.png")


def plot_pr_quadrant(prf: pd.DataFrame):
    """P-R 四象限散点图 (RQ2 §6.2(3))：按模型 × 图类型标点。"""
    overall = prf[prf["parent_code"] == "ALL"].copy()
    overall["diagram_cn"] = overall["diagram_type"].map(DIAGRAM_CN)
    models = sorted(overall["model"].unique())
    colors = {"deepseek_v3": "#4C72B0", "gemini_3_flash": "#55A868", "gpt4o": "#C44E52", "qwen_3_max": "#8172B2"}
    markers = {"use_case": "o", "class": "s", "sequence": "^", "swimlane": "D"}

    fig, ax = plt.subplots(figsize=(8, 7))

    # 画四象限背景
    ax.axhline(0.5, color="gray", linewidth=0.5, linestyle="--")
    ax.axvline(0.5, color="gray", linewidth=0.5, linestyle="--")
    ax.text(0.75, 0.75, "理想模型\n(高P高R)", ha="center", va="center", fontsize=10, color="green", alpha=0.5)
    ax.text(0.25, 0.75, "保守型\n(高P低R)", ha="center", va="center", fontsize=10, color="orange", alpha=0.5)
    ax.text(0.75, 0.25, "激进型\n(低P高R)", ha="center", va="center", fontsize=10, color="red", alpha=0.5)
    ax.text(0.25, 0.25, "不可靠\n(低P低R)", ha="center", va="center", fontsize=10, color="gray", alpha=0.5)

    for _, row in overall.iterrows():
        ax.scatter(row["recall"], row["precision"],
                   color=colors.get(row["model"], "gray"),
                   marker=markers.get(row["diagram_type"], "o"),
                   s=120, edgecolors="black", linewidths=0.5, zorder=5)
        ax.annotate(f"{row['model'][:3]}\n{row['diagram_cn']}",
                    (row["recall"], row["precision"]),
                    fontsize=7, ha="center", va="bottom",
                    xytext=(0, 6), textcoords="offset points")

    # 图例
    for m in models:
        ax.scatter([], [], color=colors[m], label=m, s=60)
    for dt in DIAGRAM_ORDER:
        ax.scatter([], [], color="gray", marker=markers[dt], label=DIAGRAM_CN[dt], s=60)
    ax.legend(loc="lower left", fontsize=8, ncol=2)

    ax.set_xlabel("Recall（召回率）", fontsize=12)
    ax.set_ylabel("Precision（精确率）", fontsize=12)
    ax.set_title("模型判断性格：P-R 四象限散点图", fontsize=14)
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.set_aspect("equal")
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(FIG_DIR / "pr_quadrant.png", dpi=150)
    plt.close(fig)
    print("  ✓ pr_quadrant.png")


def plot_f1_heatmap(prf: pd.DataFrame):
    """一级指标 × 模型 的 F1 热力图。"""
    detail = prf[prf["parent_code"] != "ALL"].copy()
    pivot = detail.pivot_table(index="parent_code", columns="model", values="f1", aggfunc="mean")

    # 排序
    prefix_order = []
    for dt in DIAGRAM_ORDER:
        p = {"use_case": "UC", "class": "CC", "sequence": "SC", "swimlane": "SW"}[dt]
        codes = sorted([c for c in pivot.index if c.startswith(p)])
        prefix_order.extend(codes)
    pivot = pivot.reindex(prefix_order).dropna(how="all")

    fig, ax = plt.subplots(figsize=(8, max(6, len(pivot) * 0.35)))
    sns.heatmap(pivot, annot=True, fmt=".2f", cmap="RdYlGn", vmin=0, vmax=1, ax=ax,
                linewidths=0.5, cbar_kws={"label": "F1"})
    ax.set_xlabel("模型")
    ax.set_ylabel("一级指标")
    ax.set_title("各一级指标 × 模型 错误检测 F1 热力图")
    fig.tight_layout()
    fig.savefig(FIG_DIR / "f1_heatmap.png", dpi=150)
    plt.close(fig)
    print("  ✓ f1_heatmap.png")


# ======================= 8. 文字分析报告 =======================

def generate_analysis_report(df: pd.DataFrame, prf: pd.DataFrame | None = None):
    data = df.dropna(subset=["bias"]).copy()
    models = sorted(data["model"].unique())
    lines = []
    lines.append("=" * 60)
    lines.append("深度分析报告")
    lines.append("=" * 60)

    # --- 偏差分析 ---
    lines.append("\n## 1. 严苛/宽松倾向分析 (RQ2)")
    lines.append("-" * 40)
    for m in models:
        sub = data[data["model"] == m]["bias"]
        lines.append(f"\n  {m}:")
        lines.append(f"    平均偏差: {sub.mean():+.2f} ({'宽松' if sub.mean() > 0 else '严苛'})")
        lines.append(f"    中位偏差: {sub.median():+.2f}")
        lines.append(f"    标准差:   {sub.std():.2f}")
        lines.append(f"    偏差>0 占比: {(sub > 0).mean()*100:.1f}% (宽松)")
        lines.append(f"    偏差<0 占比: {(sub < 0).mean()*100:.1f}% (严苛)")
        lines.append(f"    偏差=0 占比: {(sub == 0).mean()*100:.1f}% (完全一致)")

    # --- 按图类型偏差 ---
    lines.append("\n\n## 2. 按图类型的偏差倾向 (RQ2)")
    lines.append("-" * 40)
    for dt in DIAGRAM_ORDER:
        cn = DIAGRAM_CN[dt]
        lines.append(f"\n  {cn}:")
        for m in models:
            sub = data[(data["model"] == m) & (data["diagram_type"] == dt)]["bias"]
            if len(sub) == 0:
                continue
            lines.append(f"    {m:<20} 平均偏差={sub.mean():+.2f}  中位={sub.median():+.1f}  {'宽松' if sub.mean() > 0 else '严苛'}")

    # --- 最易偏差的指标 ---
    lines.append("\n\n## 3. 偏差最大的指标 TOP 10 (RQ2)")
    lines.append("-" * 40)
    for m in models:
        sub = data[data["model"] == m]
        by_code = sub.groupby("code")["bias"].agg(["mean", "std", "count"])
        by_code["abs_mean"] = by_code["mean"].abs()
        top = by_code.sort_values("abs_mean", ascending=False).head(10)
        lines.append(f"\n  {m}:")
        for code, row in top.iterrows():
            direction = "宽松" if row["mean"] > 0 else "严苛"
            lines.append(f"    {code:<10} 平均偏差={row['mean']:+.2f} ({direction})  n={int(row['count'])}")

    # --- N/A 分析 ---
    lines.append("\n\n## 4. N/A 识别分析 (RQ1)")
    lines.append("-" * 40)
    for m in models:
        sub = df[df["model"] == m]
        tp = ((sub["teacher_na"]) & (sub["model_na_bool"])).sum()
        fp = ((~sub["teacher_na"]) & (sub["model_na_bool"])).sum()
        fn = ((sub["teacher_na"]) & (~sub["model_na_bool"])).sum()
        tn = ((~sub["teacher_na"]) & (~sub["model_na_bool"])).sum()
        precision = tp / (tp + fp) if (tp + fp) > 0 else 0
        recall = tp / (tp + fn) if (tp + fn) > 0 else 0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0
        lines.append(f"\n  {m}:")
        lines.append(f"    TP={tp}  FP={fp}  FN={fn}  TN={tn}")
        lines.append(f"    Precision={precision:.3f}  Recall={recall:.3f}  F1={f1:.3f}")
        lines.append(f"    解读: {'善于识别N/A' if recall > 0.6 else '容易漏判N/A'}，{'误判N/A较少' if precision > 0.7 else '存在误判N/A风险'}")

    # --- 打分分布 ---
    lines.append("\n\n## 5. 打分分布特征 (RQ1)")
    lines.append("-" * 40)
    teacher = df[~df["teacher_na"]]["teacher_score_num"].dropna()
    lines.append(f"  教师: mean={teacher.mean():.2f}  std={teacher.std():.2f}  median={teacher.median():.1f}")
    for m in models:
        sub = data[data["model"] == m]["model_score_num"]
        lines.append(f"  {m:<20} mean={sub.mean():.2f}  std={sub.std():.2f}  median={sub.median():.1f}")

    # --- P/R/F1 分析 ---
    if prf is not None:
        lines.append("\n\n## 6. 错误检测 Precision / Recall / F1 (RQ1)")
        lines.append("-" * 40)
        lines.append("  二值化规则：分数 < 10 → 检出错误，= 10 → 无错误")
        overall_prf = prf[prf["parent_code"] == "ALL"]
        for m in models:
            msub = overall_prf[overall_prf["model"] == m]
            lines.append(f"\n  {m}:")
            for _, row in msub.iterrows():
                cn = DIAGRAM_CN.get(row["diagram_type"], row["diagram_type"])
                lines.append(
                    f"    {cn:<8} P={row['precision']:.3f}  R={row['recall']:.3f}  "
                    f"F1={row['f1']:.3f}  (TP={int(row['tp'])} FP={int(row['fp'])} "
                    f"FN={int(row['fn'])} TN={int(row['tn'])})")
            # 整体 P/R/F1
            all_tp = msub["tp"].sum()
            all_fp = msub["fp"].sum()
            all_fn = msub["fn"].sum()
            all_tn = msub["tn"].sum()
            all_p = all_tp / (all_tp + all_fp) if (all_tp + all_fp) > 0 else 0
            all_r = all_tp / (all_tp + all_fn) if (all_tp + all_fn) > 0 else 0
            all_f1 = 2 * all_p * all_r / (all_p + all_r) if (all_p + all_r) > 0 else 0
            lines.append(f"    {'整体':<8} P={all_p:.3f}  R={all_r:.3f}  F1={all_f1:.3f}")

            # 性格判断
            if all_p >= 0.5 and all_r >= 0.5:
                personality = "理想型（高P高R）"
            elif all_p >= 0.5 and all_r < 0.5:
                personality = "保守型（高P低R）：只在高确定性下指出错误"
            elif all_p < 0.5 and all_r >= 0.5:
                personality = "激进型（低P高R）：倾向于多报错误"
            else:
                personality = "不可靠（低P低R）"
            lines.append(f"    → 判断性格: {personality}")

    report_text = "\n".join(lines)
    report_path = RESULT_DIR / "analysis_report.txt"
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(report_text)
    print(f"  ✓ analysis_report.txt")
    return report_text


# ======================= main =======================

def main():
    print("Loading data...")
    df = load_detail()
    print(f"  {len(df)} rows loaded\n")

    print("Generating figures...")
    plot_bias_boxplot(df)
    plot_bias_by_diagram(df)
    plot_criterion_mae_heatmap(df)
    plot_radar_by_diagram(df)
    plot_na_confusion(df)
    plot_score_distribution(df)
    plot_criterion_bias_detail(df)

    print("\nComputing Precision/Recall/F1...")
    prf = compute_prf(df)
    prf.to_csv(RESULT_DIR / "prf_detail.csv", index=False)
    print("  ✓ prf_detail.csv")
    plot_f1_radar(prf)
    plot_pr_quadrant(prf)
    plot_f1_heatmap(prf)

    print("\nGenerating analysis report...")
    report = generate_analysis_report(df, prf)

    print("\n" + report)
    print(f"\n\nAll outputs saved to: {FIG_DIR}")


if __name__ == "__main__":
    main()
