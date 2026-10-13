"""WebSocket：实时推送 grading_run 进度。

前端 `/ws/runs/{run_id}` 订阅；后端每 2 秒轮询 DB 推送一次。
（为避免复杂度，没做 pubsub；规模 < 50 并发订阅够用。）
"""

from __future__ import annotations

import asyncio
import json
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.db import get_sessionmaker
from ..core.security import decode_token
from ..models.grading import GradingResult, GradingRun, GradingRunStatus


router = APIRouter()
logger = logging.getLogger(__name__)

POLL_SECONDS = 2.0


async def _snapshot(session: AsyncSession, run_id: int) -> dict:
    run = await session.get(GradingRun, run_id)
    if run is None:
        return {"error": "run not found"}

    rows = (await session.execute(
        select(GradingResult.model_key, GradingResult.status, func.count())
        .where(GradingResult.run_id == run_id)
        .group_by(GradingResult.model_key, GradingResult.status)
    )).all()

    per_model: dict[str, dict[str, int]] = {}
    total = 0
    completed = 0
    for mk, st, n in rows:
        total += n
        s = st.value if hasattr(st, "value") else str(st)
        if s in ("success", "failed"):
            completed += n
        per_model.setdefault(mk, {"pending": 0, "running": 0, "success": 0, "failed": 0})
        per_model[mk][s] = per_model[mk].get(s, 0) + n

    return {
        "run_id": run.id,
        "status": run.status.value if hasattr(run.status, "value") else str(run.status),
        "total": total,
        "completed": completed,
        "per_model": per_model,
    }


@router.websocket("/ws/runs/{run_id}")
async def ws_run_progress(
    websocket: WebSocket,
    run_id: int,
):
    # 强制认证：通过 query 传 token
    token = websocket.query_params.get("token")
    if not token:
        await websocket.close(code=4401)
        return
    try:
        decode_token(token)
    except Exception:
        await websocket.close(code=4401)
        return

    await websocket.accept()
    maker = get_sessionmaker()
    try:
        while True:
            async with maker() as session:
                snap = await _snapshot(session, run_id)
            await websocket.send_text(json.dumps(snap, ensure_ascii=False))
            if snap.get("status") in ("completed", "failed", "cancelled"):
                await asyncio.sleep(POLL_SECONDS)
                break
            await asyncio.sleep(POLL_SECONDS)
    except WebSocketDisconnect:
        logger.info("ws disconnect run_id=%s", run_id)
    except Exception as e:  # noqa: BLE001
        logger.exception("ws error: %s", e)
        try:
            await websocket.close(code=1011)
        except Exception:
            pass
