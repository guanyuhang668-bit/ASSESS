"""
回填历史使用时长数据（基于事件的保守估算）。

设计思路：
  仅靠 ChatMessage 时间戳之间的间隔会严重低估实际使用时长，因为：
    - 学生在 StarUML 里画图的离线时间（每张图 15-30 分钟）不可见
    - 读题、思考、阅读 Agent 反馈的时间不可见
    - LLM 响应间隔之间的"思考与改图"时间被算法切断

  改进：每个 ChatSession 估算使用时间 = min(合理上限, max(活跃跨度, 事件加权工作量))
       活跃跨度 = 相邻消息间隔逐段累加，但每段最多计 30 分钟
       事件加权工作量 = SESSION_BASE + n_user×USER_MSG_WORK + n_assistant×ASSISTANT_READ

参数（保守估算）：
  SESSION_BASE     = 15 min  进入会话+读题+画初稿的固定开销
  USER_MSG_WORK    = 8 min   每条用户消息背后的工作量（改图+上传）
  ASSISTANT_READ   = 2 min   阅读 Agent 反馈的时间
  GAP_CAP          = 30 min  相邻消息间隔最多计入 30 分钟，避免跨夜高估
  SESSION_CAP      = 150 min 单个会话最多 2.5 小时

每个 ChatSession 写入一条 UserActivityLog（source='reconstructed'）。

用法：
    cd /root/UML图工具/uml-grader/backend
    .venv/bin/python -m scripts.backfill_activity
"""

from __future__ import annotations

import asyncio
import sys
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import delete, func, select

from app.core.db import get_sessionmaker
from app.models.chat import ChatSession, ChatMessage
from app.models.activity import UserActivityLog

# ---- 参数（分钟） ----
SESSION_BASE_MIN = 15
USER_MSG_WORK_MIN = 8
ASSISTANT_READ_MIN = 2
GAP_CAP_MIN = 30
SESSION_CAP_MIN = 150


def estimate_active_span_seconds(message_times) -> int:
    """按相邻消息间隔估算活跃跨度，长间隔截断，避免跨夜/隔天高估。"""
    total = 0
    gap_cap_seconds = GAP_CAP_MIN * 60
    for prev, cur in zip(message_times, message_times[1:]):
        gap = int((cur - prev).total_seconds())
        if gap > 0:
            total += min(gap, gap_cap_seconds)
    return total


async def backfill():
    maker = get_sessionmaker()
    async with maker() as session:
        # 清除之前回填的数据（幂等）
        await session.execute(
            delete(UserActivityLog).where(UserActivityLog.source == "reconstructed")
        )
        await session.flush()

        chat_sessions = (await session.execute(
            select(ChatSession).order_by(ChatSession.id)
        )).scalars().all()

        total_blocks = 0
        per_user_seconds: dict[int, int] = {}

        for cs in chat_sessions:
            # 取该会话所有消息（按时间排序）
            msgs = (await session.execute(
                select(ChatMessage.role, ChatMessage.created_at)
                .where(ChatMessage.session_id == cs.id)
                .order_by(ChatMessage.created_at)
            )).all()

            if not msgs:
                continue

            n_user = sum(1 for m in msgs if m.role == "user")
            n_assistant = sum(1 for m in msgs if m.role == "assistant")
            message_times = [m.created_at for m in msgs]

            # 事件加权工作量
            work_min = (
                SESSION_BASE_MIN
                + n_user * USER_MSG_WORK_MIN
                + n_assistant * ASSISTANT_READ_MIN
            )
            work_seconds = work_min * 60

            # 首尾原始 span 只作为审计字段，不直接作为使用时长，避免隔天会话被算成几十小时。
            start_ts = message_times[0]
            end_ts = message_times[-1]
            actual_span_seconds = int((end_ts - start_ts).total_seconds())
            active_span_seconds = estimate_active_span_seconds(message_times)

            duration_seconds = min(
                max(work_seconds, active_span_seconds),
                SESSION_CAP_MIN * 60,
            )

            # 写入 UserActivityLog（块结束时间 = start + duration）
            ended_at = start_ts + timedelta(seconds=duration_seconds)
            log = UserActivityLog(
                user_id=cs.user_id,
                started_at=start_ts,
                ended_at=ended_at,
                duration_seconds=duration_seconds,
                chat_session_id=cs.id,
                context={
                    "backfill": True,
                    "n_user_msg": n_user,
                    "n_assistant_msg": n_assistant,
                    "work_seconds": work_seconds,
                    "active_span_seconds": active_span_seconds,
                    "actual_span_seconds": actual_span_seconds,
                    "gap_cap_seconds": GAP_CAP_MIN * 60,
                    "session_cap_seconds": SESSION_CAP_MIN * 60,
                },
                source="reconstructed",
            )
            session.add(log)
            total_blocks += 1

            per_user_seconds[cs.user_id] = per_user_seconds.get(cs.user_id, 0) + duration_seconds

        await session.flush()

        # 同步 ChatSession.total_active_seconds：包含本次回填和已有 heartbeat。
        session_ids = [cs.id for cs in chat_sessions]
        if session_ids:
            totals = dict((await session.execute(
                select(
                    UserActivityLog.chat_session_id,
                    func.coalesce(func.sum(UserActivityLog.duration_seconds), 0),
                )
                .where(UserActivityLog.chat_session_id.in_(session_ids))
                .group_by(UserActivityLog.chat_session_id)
            )).all())
            for cs in chat_sessions:
                cs.total_active_seconds = int(totals.get(cs.id, 0))
                session.add(cs)

        await session.commit()

    # ---- 统计 ----
    n_users = len(per_user_seconds)
    if n_users:
        secs = sorted(per_user_seconds.values())
        avg = sum(secs) / n_users
        median = secs[n_users // 2]
        ge_3h = sum(1 for s in secs if s >= 3 * 3600)
        ge_1h = sum(1 for s in secs if s >= 3600)
        print("✅ 回填完成（保守事件估算法）")
        print(
            "   - 参数: "
            f"SESSION_BASE={SESSION_BASE_MIN}min, "
            f"USER_MSG={USER_MSG_WORK_MIN}min, "
            f"ASSISTANT={ASSISTANT_READ_MIN}min, "
            f"GAP_CAP={GAP_CAP_MIN}min, "
            f"SESSION_CAP={SESSION_CAP_MIN}min"
        )
        print(f"   - 有 ChatSession 的学生: {n_users}")
        print(f"   - 写入使用块数: {total_blocks}")
        print(f"   - 平均使用时长: {avg/3600:.2f} h")
        print(f"   - 中位数: {median/3600:.2f} h")
        print(f"   - ≥3h 学生: {ge_3h} ({ge_3h/n_users*100:.1f}%)")
        print(f"   - ≥1h 学生: {ge_1h} ({ge_1h/n_users*100:.1f}%)")
    else:
        print("⚠️  没有任何 ChatSession，无数据可回填")


if __name__ == "__main__":
    asyncio.run(backfill())
