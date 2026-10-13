"""批改任务：新建、列表、详情、取消、结果对比。"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..core.db import get_session
from ..core.security import require_non_student
from ..models.grading import (
    CriterionScore, GradingResult, GradingResultStatus, GradingRun, GradingRunStatus, Issue,
)
from ..models.rubric import RubricVersion
from ..models.submission import Submission
from ..schemas.common import OkResponse
from ..schemas.grading import (
    CriterionScoreOut, GradingProgressOut, GradingResultDetailOut,
    GradingResultOut, GradingRunCreateIn, GradingRunOut, IssueOut,
)
from ..services.llm.factory import get_llm_pool
from ..workers.enqueue import enqueue_grading_run


router = APIRouter()


@router.get("/models", response_model=list[str])
async def list_models(_u=Depends(require_non_student)) -> list[str]:
    """列出当前可用的 LLM 客户端 key。"""
    pool = await get_llm_pool()
    return sorted(pool.keys())


@router.post("/runs", response_model=GradingRunOut, status_code=status.HTTP_201_CREATED)
async def create_run(
    body: GradingRunCreateIn,
    session: AsyncSession = Depends(get_session),
    user=Depends(require_non_student),
):
    # 校验 submissions 存在
    stmt = select(Submission).where(Submission.id.in_(body.submission_ids))
    subs = list((await session.execute(stmt)).scalars().all())
    if len(subs) != len(body.submission_ids):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "some submission_ids missing")

    # 校验 models
    pool = await get_llm_pool()
    unknown = [m for m in body.model_keys if m not in pool]
    if unknown:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"unknown models: {unknown}")

    # 推断 rubric_version_ids
    if body.rubric_version_ids:
        rv_ids = list(body.rubric_version_ids)
        # 校验
        rv_rows = list((await session.execute(
            select(RubricVersion).where(RubricVersion.id.in_(rv_ids))
        )).scalars().all())
        if len(rv_rows) != len(rv_ids):
            raise HTTPException(status.HTTP_404_NOT_FOUND, "some rubric_version_ids missing")
    else:
        # 对 submissions 涉及的每种 diagram_type，取 is_active=True 的版本
        dtypes = sorted({s.diagram_type for s in subs})
        rv_rows = list((await session.execute(
            select(RubricVersion).where(
                RubricVersion.diagram_type.in_(dtypes),
                RubricVersion.is_active.is_(True),
            )
        )).scalars().all())
        rv_by_type = {rv.diagram_type: rv for rv in rv_rows}
        missing = [dt for dt in dtypes if dt not in rv_by_type]
        if missing:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                f"no active rubric for diagram types: {missing}",
            )
        rv_ids = [rv.id for rv in rv_rows]

    run = GradingRun(
        name=body.name,
        description=body.description,
        created_by=user.id,
        rubric_version_ids=rv_ids,
        model_keys=list(body.model_keys),
        submission_ids=list(body.submission_ids),
        status=GradingRunStatus.PENDING,
        total_tasks=len(body.submission_ids) * len(body.model_keys),
    )
    session.add(run)
    await session.commit()
    await session.refresh(run)

    # 预创建 grading_result 行（按 submission × model）
    by_dtype_rv = {}
    for rv_id in rv_ids:
        rv = await session.get(RubricVersion, rv_id)
        if rv:
            by_dtype_rv[rv.diagram_type] = rv.id
    for sub in subs:
        rv_id = by_dtype_rv.get(sub.diagram_type)
        if rv_id is None:
            continue
        for mk in body.model_keys:
            session.add(GradingResult(
                run_id=run.id,
                submission_id=sub.id,
                rubric_version_id=rv_id,
                model_key=mk,
                status=GradingResultStatus.PENDING,
            ))
    await session.commit()

    # 下发给 worker
    await enqueue_grading_run(run.id)

    return run


@router.get("/runs", response_model=list[GradingRunOut])
async def list_runs(
    session: AsyncSession = Depends(get_session),
    _u=Depends(require_non_student),
    limit: int = 50,
):
    rows = (await session.execute(
        select(GradingRun).order_by(GradingRun.created_at.desc()).limit(limit)
    )).scalars().all()
    return list(rows)


@router.get("/runs/{run_id}", response_model=GradingRunOut)
async def get_run(
    run_id: int,
    session: AsyncSession = Depends(get_session),
    _u=Depends(require_non_student),
):
    run = await session.get(GradingRun, run_id)
    if run is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    return run


@router.get("/runs/{run_id}/progress", response_model=GradingProgressOut)
async def get_progress(
    run_id: int,
    session: AsyncSession = Depends(get_session),
    _u=Depends(require_non_student),
):
    run = await session.get(GradingRun, run_id)
    if run is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND)

    rows = (await session.execute(
        select(GradingResult.model_key, GradingResult.status, func.count())
        .where(GradingResult.run_id == run_id)
        .group_by(GradingResult.model_key, GradingResult.status)
    )).all()

    totals = {"total": 0, "pending": 0, "running": 0, "success": 0, "failed": 0, "completed": 0}
    per_model: dict[str, dict[str, int]] = {}
    for model_key, status_val, n in rows:
        totals["total"] += n
        s = status_val.value if hasattr(status_val, "value") else str(status_val)
        if s == "success":
            totals["success"] += n
            totals["completed"] += n
        elif s == "failed":
            totals["failed"] += n
            totals["completed"] += n
        else:
            totals[s] = totals.get(s, 0) + n
        per_model.setdefault(model_key, {"pending": 0, "running": 0, "success": 0, "failed": 0})
        per_model[model_key][s] = per_model[model_key].get(s, 0) + n

    return GradingProgressOut(
        run_id=run.id,
        status=run.status,
        total=totals["total"],
        completed=totals["completed"],
        failed=totals["failed"],
        running=totals.get("running", 0),
        pending=totals.get("pending", 0),
        per_model=per_model,
    )


@router.get("/runs/{run_id}/results", response_model=list[GradingResultOut])
async def list_run_results(
    run_id: int,
    session: AsyncSession = Depends(get_session),
    _u=Depends(require_non_student),
):
    rows = (await session.execute(
        select(GradingResult).where(GradingResult.run_id == run_id)
    )).scalars().all()
    return list(rows)


@router.get("/results/{result_id}", response_model=GradingResultDetailOut)
async def get_result(
    result_id: int,
    session: AsyncSession = Depends(get_session),
    _u=Depends(require_non_student),
):
    stmt = (
        select(GradingResult)
        .options(
            selectinload(GradingResult.criterion_scores).selectinload(CriterionScore.issues)
        )
        .where(GradingResult.id == result_id)
    )
    row = (await session.execute(stmt)).scalar_one_or_none()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    return {
        **GradingResultOut.model_validate(row).model_dump(),
        "criterion_scores": [
            {
                **CriterionScoreOut.model_validate(cs).model_dump(exclude={"issues"}),
                "issues": [IssueOut.model_validate(i).model_dump() for i in cs.issues],
            }
            for cs in row.criterion_scores
        ],
    }


@router.get("/results/by-submission/{submission_id}", response_model=list[GradingResultDetailOut])
async def results_by_submission(
    submission_id: int,
    run_id: int | None = None,
    session: AsyncSession = Depends(get_session),
    _u=Depends(require_non_student),
):
    """多模型横向对比一个 submission 的评分。"""
    stmt = (
        select(GradingResult)
        .options(
            selectinload(GradingResult.criterion_scores).selectinload(CriterionScore.issues)
        )
        .where(GradingResult.submission_id == submission_id)
        .order_by(GradingResult.created_at.desc())
    )
    if run_id:
        stmt = stmt.where(GradingResult.run_id == run_id)
    rows = (await session.execute(stmt)).scalars().all()
    return [
        {
            **GradingResultOut.model_validate(r).model_dump(),
            "criterion_scores": [
                {
                    **CriterionScoreOut.model_validate(cs).model_dump(exclude={"issues"}),
                    "issues": [IssueOut.model_validate(i).model_dump() for i in cs.issues],
                }
                for cs in r.criterion_scores
            ],
        }
        for r in rows
    ]


@router.post("/runs/{run_id}/cancel", response_model=OkResponse)
async def cancel_run(
    run_id: int,
    session: AsyncSession = Depends(get_session),
    _u=Depends(require_non_student),
):
    run = await session.get(GradingRun, run_id)
    if run is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    if run.status in (GradingRunStatus.COMPLETED, GradingRunStatus.FAILED, GradingRunStatus.CANCELLED):
        return OkResponse(ok=False, message=f"already {run.status.value}")
    run.status = GradingRunStatus.CANCELLED
    run.finished_at = datetime.now(timezone.utc)
    await session.commit()
    return OkResponse(message="cancelled")
