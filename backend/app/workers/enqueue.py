"""把 grading_run 投递到 ARQ 队列。

如果 Redis 不可用（开发模式 / 未启 worker），退化为 asyncio.create_task 直接跑。
"""

from __future__ import annotations

import asyncio
import logging

from arq import create_pool
from arq.connections import RedisSettings

from ..core.config import get_settings


logger = logging.getLogger(__name__)


def _redis_settings() -> RedisSettings:
    s = get_settings()
    return RedisSettings(host=s.redis_host, port=s.redis_port, database=s.redis_db)


async def enqueue_grading_run(run_id: int) -> None:
    """投递一个 grading_run 到 worker。"""
    try:
        pool = await create_pool(_redis_settings())
        await pool.enqueue_job("run_grading_run", run_id)
        await pool.close()
        logger.info("enqueued grading_run=%s", run_id)
    except Exception as e:  # noqa: BLE001
        logger.warning("enqueue failed, fallback to in-process: %s", e)
        # 延迟导入避免循环
        from .grading_worker import run_grading_run

        asyncio.create_task(run_grading_run({}, run_id))
