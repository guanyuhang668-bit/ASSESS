"""ARQ worker：消费 grading_run，拆成子任务并发执行。

启动：
    arq app.workers.grading_worker.WorkerSettings
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from arq.connections import RedisSettings
from sqlalchemy import select, update

from ..core.config import get_settings
from ..core.db import dispose_engine, get_sessionmaker
from ..models.grading import (
    GradingResult, GradingResultStatus, GradingRun, GradingRunStatus,
)
from ..services.grading_svc import grade_one


logger = logging.getLogger(__name__)


async def run_grading_run(ctx: dict, run_id: int) -> dict:
    """外层任务：拉所有 pending 的 grading_result 并发跑。"""
    settings = get_settings()
    maker = get_sessionmaker()

    async with maker() as session:
        run = await session.get(GradingRun, run_id)
        if run is None:
            return {"run_id": run_id, "error": "run not found"}

        if run.status in (GradingRunStatus.COMPLETED, GradingRunStatus.CANCELLED):
            return {"run_id": run_id, "status": run.status.value}

        run.status = GradingRunStatus.RUNNING
        run.started_at = datetime.now(timezone.utc)
        await session.commit()

        # 拉 pending 的 result id 列表
        ids_rows = (await session.execute(
            select(GradingResult.id).where(
                GradingResult.run_id == run_id,
                GradingResult.status.in_([
                    GradingResultStatus.PENDING, GradingResultStatus.RUNNING,
                ]),
            )
        )).all()
        result_ids = [r[0] for r in ids_rows]

    if not result_ids:
        async with maker() as session:
            await _finalize_run(session, run_id)
        return {"run_id": run_id, "result_ids": []}

    # 为每个 result 起一个并发 task，LLM 客户端自带 per-model semaphore
    sem = asyncio.Semaphore(settings.worker_max_jobs)

    async def _one(rid: int) -> None:
        async with sem, maker() as ss:
            try:
                await grade_one(ss, result_id=rid)
            except Exception as e:  # noqa: BLE001
                logger.exception("grade_one crash rid=%s: %s", rid, e)

    await asyncio.gather(*[_one(rid) for rid in result_ids])

    async with maker() as session:
        await _finalize_run(session, run_id)

    return {"run_id": run_id, "graded": len(result_ids)}


async def _finalize_run(session, run_id: int) -> None:
    run = await session.get(GradingRun, run_id)
    if run is None:
        return
    rows = (await session.execute(
        select(GradingResult.status)
        .where(GradingResult.run_id == run_id)
    )).all()
    total = len(rows)
    completed = sum(1 for r in rows if r[0] == GradingResultStatus.SUCCESS)
    failed = sum(1 for r in rows if r[0] == GradingResultStatus.FAILED)

    run.total_tasks = total
    run.completed_tasks = completed
    run.failed_tasks = failed
    if failed == 0 and completed == total:
        run.status = GradingRunStatus.COMPLETED
    elif completed + failed == total:
        run.status = (
            GradingRunStatus.COMPLETED if failed == 0 else GradingRunStatus.FAILED
        )
    run.finished_at = datetime.now(timezone.utc)
    await session.commit()


async def on_startup(ctx: dict) -> None:
    logger.info("arq worker started")


async def on_shutdown(ctx: dict) -> None:
    await dispose_engine()
    logger.info("arq worker stopped")


def _build_redis_settings() -> RedisSettings:
    s = get_settings()
    return RedisSettings(host=s.redis_host, port=s.redis_port, database=s.redis_db)


class WorkerSettings:
    """arq 入口：`arq app.workers.grading_worker.WorkerSettings`"""

    functions = [run_grading_run]
    on_startup = on_startup
    on_shutdown = on_shutdown
    max_jobs = 8
    job_timeout = 60 * 60
    redis_settings = _build_redis_settings()
