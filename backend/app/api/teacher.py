"""教师标注：为某 submission 的某条指标打分 + 标 issue。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..core.db import get_session
from ..core.security import require_non_student
from ..models.submission import Submission
from ..models.teacher_score import TeacherIssue, TeacherScore
from ..schemas.common import OkResponse
from ..schemas.teacher import TeacherIssueOut, TeacherScoreIn, TeacherScoreOut


router = APIRouter()


@router.post("/scores", response_model=TeacherScoreOut)
async def upsert_teacher_score(
    body: TeacherScoreIn,
    session: AsyncSession = Depends(get_session),
    user=Depends(require_non_student),
):
    sub = await session.get(Submission, body.submission_id)
    if sub is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "submission missing")

    stmt = select(TeacherScore).where(
        TeacherScore.submission_id == body.submission_id,
        TeacherScore.teacher_id == user.id,
        TeacherScore.code == body.code,
    ).options(selectinload(TeacherScore.issues))
    ts = (await session.execute(stmt)).scalar_one_or_none()

    if ts is None:
        ts = TeacherScore(
            submission_id=body.submission_id,
            teacher_id=user.id,
            code=body.code,
        )
        session.add(ts)

    ts.score = body.score
    ts.max_score = body.max_score
    ts.not_applicable = body.not_applicable
    ts.comment = body.comment

    # 清空旧 issue 重新写
    if ts.id:
        for old in list(ts.issues):
            await session.delete(old)

    await session.flush()
    for i in body.issues:
        session.add(TeacherIssue(
            teacher_score_id=ts.id,
            element_refs=list(i.element_refs),
            description=i.description,
            severity=i.severity,
        ))
    await session.commit()

    # 重新载入
    ts = (await session.execute(
        select(TeacherScore).where(TeacherScore.id == ts.id)
        .options(selectinload(TeacherScore.issues))
    )).scalar_one()
    return {
        **TeacherScoreOut.model_validate(ts).model_dump(exclude={"issues"}),
        "issues": [TeacherIssueOut.model_validate(i).model_dump() for i in ts.issues],
    }


@router.get("/scores/{submission_id}", response_model=list[TeacherScoreOut])
async def list_teacher_scores(
    submission_id: int,
    session: AsyncSession = Depends(get_session),
    user=Depends(require_non_student),
):
    stmt = (
        select(TeacherScore)
        .where(TeacherScore.submission_id == submission_id)
        .options(selectinload(TeacherScore.issues))
        .order_by(TeacherScore.code)
    )
    rows = (await session.execute(stmt)).scalars().all()
    return [
        {
            **TeacherScoreOut.model_validate(r).model_dump(exclude={"issues"}),
            "issues": [TeacherIssueOut.model_validate(i).model_dump() for i in r.issues],
        }
        for r in rows
    ]
