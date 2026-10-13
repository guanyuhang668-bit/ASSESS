"""一致性分析：MAE / Spearman / ICC / P/R/F1。

简单实现——留给研究员 notebook 做更深入分析。
"""

from __future__ import annotations

import statistics
from collections import defaultdict

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..core.db import get_session
from ..core.security import require_non_student
from ..models.grading import CriterionScore, GradingResult, GradingRun, Issue
from ..models.teacher_score import TeacherIssue, TeacherScore
from ..schemas.analysis import AnalysisSummaryOut, ModelAgreementRow


router = APIRouter()


def _spearman(xs: list[float], ys: list[float]) -> float | None:
    if len(xs) != len(ys) or len(xs) < 3:
        return None
    try:
        from scipy.stats import spearmanr
        rho, _ = spearmanr(xs, ys)
        return float(rho) if rho == rho else None  # NaN check
    except Exception:
        return None


def _overlap(a: list[str], b: list[str]) -> bool:
    """判定两个 issue 是否指向"大致相同"的元素集合：只要有共同 element_ref 即视为匹配。"""
    sa, sb = set(a or []), set(b or [])
    if not sa or not sb:
        return False
    return bool(sa & sb)


@router.get("/runs/{run_id}/summary", response_model=AnalysisSummaryOut)
async def run_summary(
    run_id: int,
    session: AsyncSession = Depends(get_session),
    _u=Depends(require_non_student),
):
    run = await session.get(GradingRun, run_id)
    if run is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND)

    # 拉 agent 的全部 result（success 的）
    stmt = (
        select(GradingResult)
        .options(
            selectinload(GradingResult.criterion_scores).selectinload(CriterionScore.issues)
        )
        .where(GradingResult.run_id == run_id)
    )
    results = list((await session.execute(stmt)).scalars().all())

    # 拉教师打分（针对本 run 涉及的所有 submission）
    sub_ids = sorted({r.submission_id for r in results})
    t_rows = list((await session.execute(
        select(TeacherScore)
        .options(selectinload(TeacherScore.issues))
        .where(TeacherScore.submission_id.in_(sub_ids))
    )).scalars().all())
    # teacher score index: (sub_id, code) -> TeacherScore
    teacher_idx = {(t.submission_id, t.code): t for t in t_rows}
    n_teacher = len({t.submission_id for t in t_rows})

    rows_out: list[ModelAgreementRow] = []
    by_model: dict[str, list[GradingResult]] = defaultdict(list)
    for r in results:
        by_model[r.model_key].append(r)

    for mk, rs in by_model.items():
        agent_scores: list[float] = []
        teacher_scores_list: list[float] = []
        tp = fp = fn = 0
        total_tokens = 0
        total_seconds = 0.0

        for r in rs:
            total_tokens += r.prompt_tokens + r.completion_tokens
            total_seconds += r.elapsed_seconds or 0.0

            for cs in r.criterion_scores:
                key = (r.submission_id, cs.code)
                ts = teacher_idx.get(key)
                if ts is None or ts.not_applicable:
                    continue
                if cs.not_applicable:
                    continue
                # 按 max_score 归一到 [0, 100]
                agent_pct = (cs.score / cs.max_score * 100) if cs.max_score else cs.score
                teacher_pct = (ts.score / ts.max_score * 100) if ts.max_score else ts.score
                agent_scores.append(agent_pct)
                teacher_scores_list.append(teacher_pct)

                # Issue 对齐：只要有一个 agent issue 与 teacher issue 有 element_ref 交集，就算 TP
                agent_issues = cs.issues or []
                teacher_issues = ts.issues or []
                matched_t = set()
                for ai in agent_issues:
                    hit = False
                    for idx, ti in enumerate(teacher_issues):
                        if idx in matched_t:
                            continue
                        if _overlap(ai.element_refs, ti.element_refs):
                            matched_t.add(idx)
                            hit = True
                            break
                    if hit:
                        tp += 1
                    else:
                        fp += 1
                fn += max(0, len(teacher_issues) - len(matched_t))

        mae = (
            statistics.mean(abs(a - t) for a, t in zip(agent_scores, teacher_scores_list))
            if agent_scores else None
        )
        rho = _spearman(agent_scores, teacher_scores_list)
        precision = tp / (tp + fp) if (tp + fp) else None
        recall = tp / (tp + fn) if (tp + fn) else None
        f1 = (
            (2 * precision * recall / (precision + recall))
            if precision and recall
            else None
        )
        avg_tokens = total_tokens / len(rs) if rs else 0.0
        avg_seconds = total_seconds / len(rs) if rs else 0.0

        rows_out.append(ModelAgreementRow(
            model_key=mk,
            submissions_graded=len(rs),
            mae_vs_teacher=mae,
            rho_vs_teacher=rho,
            icc_vs_teacher=None,  # 留给 notebook
            precision=precision,
            recall=recall,
            f1=f1,
            avg_tokens=avg_tokens,
            avg_seconds=avg_seconds,
        ))

    return AnalysisSummaryOut(
        run_id=run.id,
        rows=sorted(rows_out, key=lambda x: x.model_key),
        n_teacher_labelled=n_teacher,
    )
