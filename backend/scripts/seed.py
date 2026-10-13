"""种子脚本：创建 admin 用户 + 批量导入 configs/rubrics/*.yaml。

用法（backend 根目录下）：
    python scripts/seed.py
    python scripts/seed.py --admin-user alice --admin-pass 123456
    python scripts/seed.py --skip-rubrics        # 只建账号
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

# 使脚本直接从 backend 根目录跑
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select, update  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.core.db import get_sessionmaker  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.models.rubric import RubricCriterion, RubricVersion  # noqa: E402
from app.models.user import AppUser  # noqa: E402
from app.services.grading.rubric_loader import load_rubric_from_yaml  # noqa: E402


async def ensure_admin(session, username: str, password: str) -> AppUser:
    stmt = select(AppUser).where(AppUser.username == username)
    user = (await session.execute(stmt)).scalar_one_or_none()
    if user:
        print(f"[=] admin already exists: {username}")
        return user
    user = AppUser(
        username=username,
        display_name="Admin",
        hashed_password=hash_password(password),
        role="admin",
        is_active=True,
    )
    session.add(user)
    await session.commit()
    await session.refresh(user)
    print(f"[+] created admin: {username}")
    return user


async def ensure_test_students(session) -> None:
    """创建测试学生账号（四个分组各两名），带 experiment_group。"""
    from app.models.class_ import SchoolClass

    # 确保班级存在
    cls_ = (await session.execute(
        select(SchoolClass).where(SchoolClass.code == "TEST01")
    )).scalar_one_or_none()
    if cls_ is None:
        cls_ = SchoolClass(code="TEST01", name="测试班级")
        session.add(cls_)
        await session.flush()

    test_students = [
        # (username, display_name, experiment_group)
        ("test_a1", "测试-A组-1", "agent_a"),
        ("test_a2", "测试-A组-2", "agent_a"),
        ("test_b1", "测试-B组-1", "agent_b"),
        ("test_b2", "测试-B组-2", "agent_b"),
        ("test_c1", "测试-C组-1", "agent_c"),
        ("test_c2", "测试-C组-2", "agent_c"),
        ("test_ctrl1", "测试-对照组-1", "control"),
        ("test_ctrl2", "测试-对照组-2", "control"),
    ]

    for uname, dname, group in test_students:
        existing = (await session.execute(
            select(AppUser).where(AppUser.username == uname)
        )).scalar_one_or_none()
        if existing:
            # 确保已有账号的分组正确
            if existing.experiment_group != group:
                existing.experiment_group = group
                session.add(existing)
                print(f"[~] updated group for {uname} -> {group}")
            else:
                print(f"[=] test student exists: {uname}")
            continue

        user = AppUser(
            username=uname,
            display_name=dname,
            hashed_password=hash_password(uname + "123"),
            role="student",
            is_active=True,
            class_id=cls_.id,
            experiment_group=group,
        )
        session.add(user)
        print(f"[+] created test student: {uname} ({group})")

    # 同时更新旧的 student01-05 账号，给它们分配分组（如果存在且未分配）
    for i, group in enumerate(["agent_a", "agent_b", "agent_c", "control", "agent_a"], start=1):
        uname = f"student0{i}"
        existing = (await session.execute(
            select(AppUser).where(AppUser.username == uname)
        )).scalar_one_or_none()
        if existing and not existing.experiment_group:
            existing.experiment_group = group
            session.add(existing)
            print(f"[~] assigned group for {uname} -> {group}")

    await session.commit()


async def import_rubric_yaml(session, path: Path, *, version: str = "v1") -> None:
    diagram_type = path.stem  # use_case / class / sequence / swimlane
    rubric = load_rubric_from_yaml(path, version_name=version)

    exists = (await session.execute(
        select(RubricVersion).where(
            RubricVersion.diagram_type == diagram_type,
            RubricVersion.name == version,
        )
    )).scalar_one_or_none()

    if exists:
        print(f"[=] rubric exists: {diagram_type}/{version}, skip")
        return

    # 其他同类型版本置为 inactive
    await session.execute(
        update(RubricVersion)
        .where(RubricVersion.diagram_type == diagram_type)
        .values(is_active=False)
    )
    rv = RubricVersion(
        diagram_type=diagram_type,
        name=version,
        source_file=path.name,
        is_active=True,
    )
    session.add(rv)
    await session.flush()

    for i, c in enumerate(rubric.criteria):
        session.add(RubricCriterion(
            rubric_version_id=rv.id,
            code=c.code, parent_code=c.parent_code, parent_name=c.parent_name,
            name=c.name, description=c.description, weight=c.weight,
            max_score=c.max_score, order_index=i,
            error_freq_total=c.error_freq_total, error_freq_by_class={},
            common_errors=c.common_errors,
            scoring_hint=c.scoring_hint,
            not_applicable_when=c.not_applicable_when,
        ))
    await session.commit()
    print(f"[+] imported rubric: {diagram_type}/{version} ({len(rubric.criteria)} criteria)")


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--admin-user", default="admin")
    ap.add_argument("--admin-pass", default="admin1234")
    ap.add_argument("--skip-rubrics", action="store_true")
    ap.add_argument("--version", default="v1", help="rubric version name")
    args = ap.parse_args()

    settings = get_settings()

    # 自动建表（如果尚未存在）
    from app.core.db import init_db  # noqa: E402
    await init_db()

    Session = get_sessionmaker()

    async with Session() as session:
        await ensure_admin(session, args.admin_user, args.admin_pass)
        await ensure_test_students(session)

        if not args.skip_rubrics:
            rdir = settings.rubrics_dir
            if not rdir.exists():
                print(f"[!] rubrics dir not found: {rdir}")
                return
            yamls = sorted(rdir.glob("*.yaml")) + sorted(rdir.glob("*.yml"))
            if not yamls:
                print(f"[!] no YAML files found in {rdir}")
                return
            for p in yamls:
                await import_rubric_yaml(session, p, version=args.version)


if __name__ == "__main__":
    asyncio.run(main())
