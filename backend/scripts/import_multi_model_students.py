"""导入“四个模型班级”学生，并设置为四模型 Agent A 实验。

用法：
    cd /root/UML图工具/uml-grader/backend
    .venv/bin/python -m scripts.import_multi_model_students

读取目录：/root/UML图工具/四个模型班级/*.xlsx
支持列：学号 / 姓名 / 班级（姓名、班级可选）。默认密码：学号 + 123。
所有导入学生：experiment_group='agent_a'，session_group='multi_model_a'。
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from openpyxl import load_workbook
from sqlalchemy import select

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.db import get_sessionmaker
from app.core.security import hash_password
from app.models.class_ import SchoolClass
from app.models.user import AppUser

SOURCE_DIR = Path("/root/UML图工具/四个模型班级")


def _cell(row, idx: int) -> str:
    if idx >= len(row) or row[idx] is None:
        return ""
    return str(row[idx]).strip()


def _class_code_from_filename(path: Path) -> str:
    name = path.stem.replace(" ", "")
    return name.replace("(1)", "")


def _rows_from_xlsx(path: Path) -> list[tuple[str, str, str]]:
    wb = load_workbook(path, read_only=False, data_only=True)
    rows: list[tuple[str, str, str]] = []
    for ws in wb.worksheets:
        values = list(ws.iter_rows(values_only=True))
        if not values:
            continue
        header = [str(v or "").strip() for v in values[0]]
        code_idx = header.index("学号") if "学号" in header else 0
        name_idx = header.index("姓名") if "姓名" in header else 1
        class_idx = header.index("班级") if "班级" in header else -1
        for row in values[1:]:
            code = _cell(row, code_idx)
            name = _cell(row, name_idx)
            class_code = _cell(row, class_idx) if class_idx >= 0 else ""
            if not code or code == "学号":
                continue
            rows.append((code, name, class_code))
    return rows


async def main() -> None:
    files = sorted(SOURCE_DIR.glob("*.xlsx"))
    if not files:
        print(f"未找到 xlsx: {SOURCE_DIR}")
        return

    maker = get_sessionmaker()
    total_created = 0
    total_updated = 0
    total_rows = 0

    async with maker() as session:
        for path in files:
            rows = _rows_from_xlsx(path)
            print(f"{path.name}: {len(rows)} 人")
            total_rows += len(rows)
            if not rows:
                continue
            fallback_class_code = _class_code_from_filename(path)

            for username, display_name, row_class_code in rows:
                class_code = row_class_code or fallback_class_code
                cls = (await session.execute(
                    select(SchoolClass).where(SchoolClass.code == class_code)
                )).scalar_one_or_none()
                if cls is None:
                    cls = SchoolClass(code=class_code, name=class_code)
                    session.add(cls)
                    await session.flush()

                user = (await session.execute(
                    select(AppUser).where(AppUser.username == username)
                )).scalar_one_or_none()
                if user is None:
                    user = AppUser(
                        username=username,
                        display_name=display_name or username,
                        hashed_password=hash_password(username + "123"),
                        role="student",
                        class_id=cls.id,
                        experiment_group="agent_a",
                        session_group="multi_model_a",
                    )
                    session.add(user)
                    total_created += 1
                else:
                    user.display_name = display_name or user.display_name or username
                    user.class_id = cls.id
                    user.experiment_group = user.experiment_group or "agent_a"
                    user.session_group = "multi_model_a"
                    session.add(user)
                    total_updated += 1

        await session.commit()

    print("完成")
    print(f"读取学生行数: {total_rows}")
    print(f"新建: {total_created}")
    print(f"更新: {total_updated}")
    if total_rows == 0:
        print("注意：当前 xlsx 只有表头，没有可导入学生数据。请替换为包含学号/姓名的名单后重新运行。")


if __name__ == "__main__":
    asyncio.run(main())
