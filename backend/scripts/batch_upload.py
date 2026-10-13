"""批量上传 .mdj 文件到系统。

用法（backend 根目录下）：
    python scripts/batch_upload.py --dir /root/UML图工具/合集/用例图 --class-code class01 --diagram-type use_case
    python scripts/batch_upload.py --dir /root/UML图工具/完整/时序图 --class-code class01 --diagram-type sequence
    python scripts/batch_upload.py --all   # 自动按目录类型上传所有
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select  # noqa: E402

from app.core.db import get_sessionmaker, init_db  # noqa: E402
from app.models.class_ import SchoolClass  # noqa: E402
from app.models.student import Student  # noqa: E402
from app.models.submission import Submission  # noqa: E402
from app.services.parser_svc import parse_submission, pick_diagram  # noqa: E402


# 目录名 → diagram_type 映射
DIR_MAP = {
    "用例图": "use_case",
    "类图": "class",
    "类图-错误图": "class",
    "时序图": "sequence",
    "泳道图": "swimlane",
}


async def ensure_class(session, code: str) -> SchoolClass:
    stmt = select(SchoolClass).where(SchoolClass.code == code)
    cls = (await session.execute(stmt)).scalar_one_or_none()
    if cls:
        return cls
    cls = SchoolClass(code=code, name=code)
    session.add(cls)
    await session.flush()
    return cls


async def ensure_student(session, class_id: int, student_code: str) -> Student:
    stmt = select(Student).where(
        Student.class_id == class_id, Student.student_code == student_code
    )
    stu = (await session.execute(stmt)).scalar_one_or_none()
    if stu:
        return stu
    stu = Student(class_id=class_id, student_code=student_code, name=student_code)
    session.add(stu)
    await session.flush()
    return stu


async def upload_one(
    session, *, path: Path, class_id: int, diagram_type: str, problem_code: str = ""
) -> str:
    """上传一个 mdj 文件，返回状态消息。"""
    student_code = path.stem.split("_")[0] if "_" in path.stem else path.stem

    # 检查是否已上传
    stu = await ensure_student(session, class_id, student_code)
    exists = (await session.execute(
        select(Submission).where(
            Submission.student_id == stu.id,
            Submission.diagram_type == diagram_type,
            Submission.problem_code == problem_code,
        )
    )).scalar_one_or_none()
    if exists:
        return f"[=] skip (exists): {path.name}"

    raw_text = path.read_text(encoding="utf-8")
    try:
        raw_data = json.loads(raw_text)
    except json.JSONDecodeError as e:
        return f"[!] JSON error: {path.name}: {e}"

    # 解析
    diagrams = parse_submission(raw_data)
    diagram = pick_diagram(diagrams, diagram_type)

    sub = Submission(
        student_id=stu.id,
        diagram_type=diagram_type,
        problem_code=problem_code,
        problem_statement="",
        original_filename=path.name,
        source_format="mdj",
        raw_data=raw_data,
        ir_data=diagram.model_dump() if diagram else {},
        ir_textual=diagram.to_textual() if diagram and hasattr(diagram, "to_textual") else str(diagram),
        element_count=len(diagram.elements) if diagram else 0,
        relation_count=len(diagram.relations) if diagram else 0,
        container_count=len(diagram.containers) if diagram and hasattr(diagram, "containers") else 0,
        parse_error="" if diagram else "no matching diagram found",
    )
    session.add(sub)
    await session.flush()
    return f"[+] #{sub.id} {path.name} ({sub.element_count}e/{sub.relation_count}r)"


async def upload_dir(
    session, *, dir_path: Path, class_id: int, diagram_type: str, problem_code: str = ""
):
    files = sorted(dir_path.glob("*.mdj"))
    if not files:
        print(f"[!] no .mdj files in {dir_path}")
        return
    print(f"\n--- {dir_path.name} ({diagram_type}) : {len(files)} files ---")
    for f in files:
        msg = await upload_one(
            session, path=f, class_id=class_id,
            diagram_type=diagram_type, problem_code=problem_code,
        )
        print(msg)
    await session.commit()


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", type=Path, help="上传单个目录")
    ap.add_argument("--class-code", default="default", help="班级编号")
    ap.add_argument("--diagram-type", help="图类型 (use_case/class/sequence/swimlane)")
    ap.add_argument("--all", action="store_true", help="自动扫描 合集/ 和 完整/ 目录")
    args = ap.parse_args()

    await init_db()
    Session = get_sessionmaker()

    async with Session() as session:
        cls = await ensure_class(session, args.class_code)
        await session.commit()

        if args.all:
            base_dirs = [
                Path("/root/UML图工具/合集"),
                Path("/root/UML图工具/完整"),
            ]
            for base in base_dirs:
                if not base.exists():
                    print(f"[!] {base} not found, skip")
                    continue
                for sub_dir in sorted(base.iterdir()):
                    if not sub_dir.is_dir():
                        continue
                    dt = DIR_MAP.get(sub_dir.name)
                    if not dt:
                        print(f"[?] unknown dir: {sub_dir.name}, skip")
                        continue
                    await upload_dir(
                        session, dir_path=sub_dir, class_id=cls.id, diagram_type=dt,
                    )
        elif args.dir:
            if not args.diagram_type:
                # 从目录名推断
                dt = DIR_MAP.get(args.dir.name)
                if not dt:
                    print(f"[!] cannot infer diagram_type from dir name '{args.dir.name}', use --diagram-type")
                    return
            else:
                dt = args.diagram_type
            await upload_dir(
                session, dir_path=args.dir, class_id=cls.id, diagram_type=dt,
            )
        else:
            print("please use --dir or --all")


if __name__ == "__main__":
    asyncio.run(main())
