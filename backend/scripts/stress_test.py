#!/usr/bin/env python3
"""压力测试：模拟 40 名学生同时发送聊天消息。

用法：
    python scripts/stress_test.py [--users 40] [--phase all|auth|chat]
"""
import argparse
import asyncio
import os
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

import httpx

BASE_URL = os.getenv("BASE_URL", "http://localhost:8000/api")
MDJ_DIR = Path("/root/UML图工具/合集/类图-错误图")
PASSWORD_SUFFIX = "123"


@dataclass
class Result:
    user: str
    phase: str
    ok: bool
    status: int = 0
    elapsed: float = 0.0
    error: str = ""


@dataclass
class Stats:
    results: list[Result] = field(default_factory=list)

    def add(self, r: Result):
        self.results.append(r)

    def summary(self, phase: str) -> str:
        rs = [r for r in self.results if r.phase == phase]
        if not rs:
            return f"  {phase}: (no results)"
        ok = sum(1 for r in rs if r.ok)
        fail = len(rs) - ok
        times = [r.elapsed for r in rs if r.ok]
        avg_t = sum(times) / len(times) if times else 0
        max_t = max(times) if times else 0
        min_t = min(times) if times else 0
        p95 = sorted(times)[int(len(times) * 0.95)] if times else 0
        lines = [
            f"  {phase}: {ok}/{len(rs)} OK, {fail} FAIL",
            f"    avg={avg_t:.2f}s  min={min_t:.2f}s  max={max_t:.2f}s  p95={p95:.2f}s",
        ]
        if fail:
            errors = [r for r in rs if not r.ok][:5]
            for e in errors:
                lines.append(f"    FAIL [{e.user}] {e.status} {e.error[:100]}")
        return "\n".join(lines)


async def get_test_students(n: int) -> list[str]:
    """从数据库获取 n 个非 control 学生账号。"""
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from app.core.db import get_engine
    import sqlalchemy as sa

    e = get_engine()
    async with e.connect() as conn:
        r = await conn.execute(sa.text("""
            SELECT u.username FROM app_user u
            WHERE u.role = 'student'
              AND u.experiment_group IS NOT NULL
              AND u.experiment_group != 'control'
            ORDER BY u.username LIMIT :n
        """), {"n": n})
        return [row[0] for row in r]


async def login(client: httpx.AsyncClient, username: str) -> str | None:
    """登录并返回 token。"""
    try:
        resp = await client.post(f"{BASE_URL}/auth/login", json={
            "username": username,
            "password": username + PASSWORD_SUFFIX,
        }, timeout=10)
        if resp.status_code == 200:
            return resp.json().get("access_token")
        return None
    except Exception:
        return None


# ======================== Phase 1: Auth 并发 ========================

async def phase_auth(users: list[str], stats: Stats):
    """40 人同时登录。"""
    print(f"\n{'='*60}")
    print(f"Phase 1: 并发登录 ({len(users)} 用户)")
    print(f"{'='*60}")

    async def _login_one(username: str):
        t0 = time.perf_counter()
        async with httpx.AsyncClient() as c:
            try:
                resp = await c.post(f"{BASE_URL}/auth/login", json={
                    "username": username,
                    "password": username + PASSWORD_SUFFIX,
                }, timeout=15)
                elapsed = time.perf_counter() - t0
                ok = resp.status_code == 200
                stats.add(Result(
                    user=username, phase="auth", ok=ok,
                    status=resp.status_code, elapsed=elapsed,
                    error="" if ok else resp.text[:200],
                ))
            except Exception as e:
                stats.add(Result(
                    user=username, phase="auth", ok=False,
                    elapsed=time.perf_counter() - t0, error=str(e)[:200],
                ))

    t_start = time.perf_counter()
    await asyncio.gather(*[_login_one(u) for u in users])
    total = time.perf_counter() - t_start
    print(f"  总耗时: {total:.2f}s")
    print(stats.summary("auth"))


# ======================== Phase 2: 轻量 API 并发 ========================

async def phase_api(users: list[str], stats: Stats):
    """40 人同时请求 /chat/sessions。"""
    print(f"\n{'='*60}")
    print(f"Phase 2: 并发 API 请求 ({len(users)} 用户 × GET /chat/sessions)")
    print(f"{'='*60}")

    # 先获取 tokens
    tokens = {}
    async with httpx.AsyncClient() as c:
        for u in users:
            t = await login(c, u)
            if t:
                tokens[u] = t
    print(f"  已登录 {len(tokens)}/{len(users)} 用户")

    async def _list_sessions(username: str, token: str):
        t0 = time.perf_counter()
        async with httpx.AsyncClient() as c:
            try:
                resp = await c.get(
                    f"{BASE_URL}/chat/sessions",
                    headers={"Authorization": f"Bearer {token}"},
                    timeout=15,
                )
                elapsed = time.perf_counter() - t0
                ok = resp.status_code == 200
                stats.add(Result(
                    user=username, phase="api", ok=ok,
                    status=resp.status_code, elapsed=elapsed,
                    error="" if ok else resp.text[:200],
                ))
            except Exception as e:
                stats.add(Result(
                    user=username, phase="api", ok=False,
                    elapsed=time.perf_counter() - t0, error=str(e)[:200],
                ))

    t_start = time.perf_counter()
    await asyncio.gather(*[_list_sessions(u, t) for u, t in tokens.items()])
    total = time.perf_counter() - t_start
    print(f"  总耗时: {total:.2f}s")
    print(stats.summary("api"))


# ======================== Phase 3: Chat 发送并发 ========================

async def phase_chat(users: list[str], stats: Stats, concurrency: int = 40):
    """N 人同时发送聊天消息（含 mdj 上传 + LLM 调用）。"""
    n = min(len(users), concurrency)
    test_users = users[:n]

    print(f"\n{'='*60}")
    print(f"Phase 3: 并发聊天 ({n} 用户同时发送消息 + mdj)")
    print(f"{'='*60}")

    # 获取 mdj 文件列表
    mdj_files = sorted(MDJ_DIR.glob("*.mdj"))
    if not mdj_files:
        print("  ERROR: 没有找到测试用 mdj 文件")
        return
    print(f"  使用 {len(mdj_files)} 个 mdj 文件轮流分配")

    # 登录
    tokens = {}
    async with httpx.AsyncClient() as c:
        for u in test_users:
            t = await login(c, u)
            if t:
                tokens[u] = t
    print(f"  已登录 {len(tokens)}/{n} 用户")

    sem = asyncio.Semaphore(n)  # 控制真正的并发

    test_image = Path("/tmp/test_uml.png")
    if not test_image.exists():
        from PIL import Image
        Image.new("RGB", (100, 100), color=(255, 255, 255)).save(test_image)

    async def _send_chat(username: str, token: str, mdj_path: Path):
        async with sem:
            t0 = time.perf_counter()
            try:
                async with httpx.AsyncClient(timeout=180) as c:
                    with open(mdj_path, "rb") as fmdj, open(test_image, "rb") as fimg:
                        files = [
                            ("mdj_file", (mdj_path.name, fmdj.read(), "application/json")),
                            ("image", ("test.png", fimg.read(), "image/png")),
                        ]
                        data = {
                            "content": "请帮我看看这个类图有什么问题",
                            "diagram_type": "class",
                            "problem_code": "stress_test",
                            "problem_statement": "压力测试题目",
                        }
                        resp = await c.post(
                            f"{BASE_URL}/chat/send",
                            headers={"Authorization": f"Bearer {token}"},
                            files=files,
                            data=data,
                        )
                elapsed = time.perf_counter() - t0
                ok = resp.status_code == 200
                detail = ""
                if ok:
                    body = resp.json()
                    score = body.get("assistant_message", {}).get("score_snapshot")
                    detail = f"score={score}"
                else:
                    detail = resp.text[:200]
                stats.add(Result(
                    user=username, phase="chat", ok=ok,
                    status=resp.status_code, elapsed=elapsed,
                    error=detail if not ok else "",
                ))
                status_icon = "✓" if ok else "✗"
                print(f"  {status_icon} {username} {elapsed:.1f}s {detail}")
            except Exception as e:
                elapsed = time.perf_counter() - t0
                stats.add(Result(
                    user=username, phase="chat", ok=False,
                    elapsed=elapsed, error=str(e)[:200],
                ))
                print(f"  ✗ {username} {elapsed:.1f}s ERROR: {str(e)[:80]}")

    # 同时发起所有请求
    tasks = []
    for i, (u, t) in enumerate(tokens.items()):
        mdj = mdj_files[i % len(mdj_files)]
        tasks.append(_send_chat(u, t, mdj))

    t_start = time.perf_counter()
    await asyncio.gather(*tasks)
    total = time.perf_counter() - t_start

    print(f"\n  总耗时: {total:.2f}s")
    print(stats.summary("chat"))


# ======================== Main ========================

async def main():
    parser = argparse.ArgumentParser(description="Chat API 压力测试")
    parser.add_argument("--users", type=int, default=40, help="并发用户数")
    parser.add_argument("--phase", default="all", choices=["all", "auth", "api", "chat"],
                        help="测试阶段")
    args = parser.parse_args()

    print(f"UML Chat 压力测试")
    print(f"目标: {BASE_URL}")
    print(f"并发用户: {args.users}")

    users = await get_test_students(args.users)
    if len(users) < args.users:
        print(f"WARNING: 只找到 {len(users)} 个可用学生账号")
    print(f"测试学生: {len(users)} 人")

    stats = Stats()

    if args.phase in ("all", "auth"):
        await phase_auth(users, stats)

    if args.phase in ("all", "api"):
        await phase_api(users, stats)

    if args.phase in ("all", "chat"):
        await phase_chat(users, stats, concurrency=args.users)

    print(f"\n{'='*60}")
    print("总结")
    print(f"{'='*60}")
    for p in ["auth", "api", "chat"]:
        if any(r.phase == p for r in stats.results):
            print(stats.summary(p))


if __name__ == "__main__":
    asyncio.run(main())
