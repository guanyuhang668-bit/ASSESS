"""学生上传后自动触发批改：用全部可用模型 × 对应 rubric。"""

from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.grading import (
    GradingResult,
    GradingResultStatus,
    GradingRun,
    GradingRunStatus,
)
from ..models.rubric import RubricVersion
from ..models.submission import Submission
from .grading_svc import grade_one
from .llm.factory import get_llm_pool
from ..workers.enqueue import enqueue_grading_run

logger = logging.getLogger(__name__)

# 学生自助上传默认使用的模型
STUDENT_GRADING_MODEL = "deepseek_v3"


async def auto_grade_submission(session: AsyncSession, submission_id: int) -> int | None:
    """为一份 submission 自动创建 GradingRun（全部可用模型），并入队。

    Returns:
        run.id if created, None if skipped (parse_error / no models / no rubric).
    """
    sub = await session.get(Submission, submission_id)
    if sub is None:
        logger.warning("auto_grade: submission %s not found", submission_id)
        return None

    # 有解析错误就不批改
    if sub.parse_error:
        logger.info("auto_grade: skip sub %s (parse_error)", submission_id)
        return None

    # 优先使用 deepseek_v3 进行评分；不可用时退化为全部模型
    pool = await get_llm_pool()
    if STUDENT_GRADING_MODEL in pool:
        model_keys = [STUDENT_GRADING_MODEL]
    else:
        model_keys = sorted(pool.keys())
    if not model_keys:
        logger.warning("auto_grade: no models available")
        return None

    # 取该 diagram_type 对应的 active rubric
    rv = (await session.execute(
        select(RubricVersion).where(
            RubricVersion.diagram_type == sub.diagram_type,
            RubricVersion.is_active.is_(True),
        )
    )).scalar_one_or_none()
    if rv is None:
        logger.warning("auto_grade: no active rubric for %s", sub.diagram_type)
        return None

    # 创建 GradingRun
    run = GradingRun(
        name=f"auto-{sub.diagram_type}-sub{sub.id}",
        description=f"自动批改 submission #{sub.id}",
        created_by=None,
        rubric_version_ids=[rv.id],
        model_keys=model_keys,
        submission_ids=[sub.id],
        status=GradingRunStatus.PENDING,
        total_tasks=len(model_keys),
    )
    session.add(run)
    await session.commit()
    await session.refresh(run)

    # 预创建 grading_result 行
    for mk in model_keys:
        session.add(GradingResult(
            run_id=run.id,
            submission_id=sub.id,
            rubric_version_id=rv.id,
            model_key=mk,
            status=GradingResultStatus.PENDING,
        ))
    await session.commit()

    # 下发给 worker
    await enqueue_grading_run(run.id)
    logger.info("auto_grade: created run %s for sub %s (%d models)", run.id, sub.id, len(model_keys))
    return run.id


async def auto_grade_submission_sync(
    session: AsyncSession, submission_id: int,
) -> GradingResult | None:
    """同步批改：为一份 submission 创建 GradingRun + GradingResult，并直接执行批改。

    用于学生自助上传场景，让学生立即获得评分反馈。

    Returns:
        GradingResult if graded, None if skipped.
    """
    sub = await session.get(Submission, submission_id)
    if sub is None:
        logger.warning("auto_grade_sync: submission %s not found", submission_id)
        return None

    if sub.parse_error:
        logger.info("auto_grade_sync: skip sub %s (parse_error)", submission_id)
        return None

    # 优先使用 deepseek_v3
    pool = await get_llm_pool()
    if STUDENT_GRADING_MODEL in pool:
        model_key = STUDENT_GRADING_MODEL
    else:
        available = sorted(pool.keys())
        if not available:
            logger.warning("auto_grade_sync: no models available")
            return None
        model_key = available[0]

    # 取该 diagram_type 对应的 active rubric
    rv = (await session.execute(
        select(RubricVersion).where(
            RubricVersion.diagram_type == sub.diagram_type,
            RubricVersion.is_active.is_(True),
        )
    )).scalar_one_or_none()
    if rv is None:
        logger.warning("auto_grade_sync: no active rubric for %s", sub.diagram_type)
        return None

    # 创建 GradingRun
    run = GradingRun(
        name=f"sync-{sub.diagram_type}-sub{sub.id}",
        description=f"同步批改 submission #{sub.id}",
        created_by=None,
        rubric_version_ids=[rv.id],
        model_keys=[model_key],
        submission_ids=[sub.id],
        status=GradingRunStatus.RUNNING,
        total_tasks=1,
    )
    session.add(run)
    await session.commit()
    await session.refresh(run)

    # 创建 grading_result 行
    result = GradingResult(
        run_id=run.id,
        submission_id=sub.id,
        rubric_version_id=rv.id,
        model_key=model_key,
        status=GradingResultStatus.PENDING,
    )
    session.add(result)
    await session.commit()
    await session.refresh(result)

    # 同步执行批改
    try:
        await grade_one(session, result_id=result.id)
    except Exception:
        logger.exception("auto_grade_sync: grade_one failed for sub %s", submission_id)

    # 刷新结果
    await session.refresh(result)

    # 更新 run 状态
    run = await session.get(GradingRun, run.id)
    if run and result.status == GradingResultStatus.SUCCESS:
        run.status = GradingRunStatus.COMPLETED
        run.completed_tasks = 1
    elif run:
        run.status = GradingRunStatus.FAILED
        run.failed_tasks = 1
    from datetime import datetime, timezone
    run.finished_at = datetime.now(timezone.utc)
    await session.commit()

    return result
