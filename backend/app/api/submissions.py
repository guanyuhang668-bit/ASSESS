"""学生提交（mdj 上传 + 自动解析为 IR）。"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.config import get_settings
from ..core.db import get_session
from ..core.security import get_current_user, require_non_student
from ..models.class_ import SchoolClass
from ..models.grading import GradingResult
from ..models.student import Student
from ..models.submission import Submission
from ..schemas.common import Page, PageMeta
from ..schemas.submission import (
    ClassOut, CriterionScoreOut, GradingFeedbackOut, GradingStatusItem,
    StudentOut, SubmissionDetailOut, SubmissionOut,
)
from ..services.auto_grade import auto_grade_submission_sync
from ..services.parser_svc import parse_submission, pick_diagram


# 文件大小上限
MAX_MDJ_SIZE = 10 * 1024 * 1024   # 10 MB
MAX_IMAGE_SIZE = 10 * 1024 * 1024  # 10 MB

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp"}


def _save_image(image: UploadFile) -> str:
    """保存上传图片到 MinIO，返回 object key。

    同时保留本地 uploads/ 的兼容写入（可通过配置关闭）。
    """
    from ..core.minio_client import upload_file_to_minio

    ext = Path(image.filename or "img.png").suffix.lower()
    if ext not in IMAGE_EXTENSIONS:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"不支持的图片格式: {ext}")
    content = image.file.read()
    if len(content) > MAX_IMAGE_SIZE:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "图片文件过大，上限 10MB")

    ct = f"image/{ext.lstrip('.')}"
    if ext == ".jpg":
        ct = "image/jpeg"

    object_key = upload_file_to_minio(
        content, original_filename=image.filename or "img.png",
        prefix="images", content_type=ct,
    )
    return object_key


router = APIRouter()


# ---------- 班级 ----------

@router.get("/classes", response_model=list[ClassOut])
async def list_classes(session: AsyncSession = Depends(get_session), _u=Depends(get_current_user)):
    rows = (await session.execute(select(SchoolClass).order_by(SchoolClass.code))).scalars().all()
    return list(rows)


@router.post("/classes", response_model=ClassOut)
async def create_class(
    code: str = Form(..., min_length=1, max_length=32),
    name: str = Form(""),
    session: AsyncSession = Depends(get_session),
    _u=Depends(require_non_student),
):
    exists = (await session.execute(
        select(SchoolClass).where(SchoolClass.code == code)
    )).scalar_one_or_none()
    if exists:
        return exists
    cls_ = SchoolClass(code=code, name=name)
    session.add(cls_)
    await session.commit()
    await session.refresh(cls_)
    return cls_


# ---------- 上传 ----------

@router.post("/upload", response_model=SubmissionOut, status_code=status.HTTP_201_CREATED)
async def upload_submission(
    file: UploadFile = File(..., description="学生 .mdj 文件"),
    class_id: int = Form(...),
    student_code: str = Form(...),
    student_name: str = Form(""),
    diagram_type: str = Form(..., description="use_case|class|sequence|swimlane"),
    problem_code: str = Form(""),
    problem_statement: str = Form(""),
    image: UploadFile | None = File(None, description="UML 图截图（可选）"),
    session: AsyncSession = Depends(get_session),
    _u=Depends(require_non_student),
):
    if diagram_type not in ("use_case", "class", "sequence", "swimlane"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"bad diagram_type: {diagram_type}")

    cls_ = await session.get(SchoolClass, class_id)
    if cls_ is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "class not found")

    # 读文件
    raw_bytes = await file.read()
    if len(raw_bytes) > MAX_MDJ_SIZE:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "mdj 文件过大，上限 10MB")
    try:
        raw_data = json.loads(raw_bytes.decode("utf-8"))
    except Exception as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"invalid mdj JSON: {e}")

    # upsert student
    stmt = select(Student).where(
        Student.class_id == class_id, Student.student_code == student_code,
    )
    student = (await session.execute(stmt)).scalar_one_or_none()
    if student is None:
        student = Student(class_id=class_id, student_code=student_code, name=student_name)
        session.add(student)
        await session.flush()
    elif student_name and not student.name:
        student.name = student_name

    # 先看是否已有同 (student, type, problem) 的提交，有则覆盖
    stmt2 = select(Submission).where(
        Submission.student_id == student.id,
        Submission.diagram_type == diagram_type,
        Submission.problem_code == problem_code,
    )
    sub = (await session.execute(stmt2)).scalar_one_or_none()
    if sub is None:
        sub = Submission(
            student_id=student.id,
            diagram_type=diagram_type,
            problem_code=problem_code,
        )
        session.add(sub)

    sub.problem_statement = problem_statement
    sub.original_filename = file.filename or ""
    sub.source_format = "mdj"
    sub.raw_data = raw_data

    # 保存图片
    if image and image.filename:
        sub.image_filename = _save_image(image)

    # 解析
    try:
        diagrams = parse_submission(raw_data)
        picked = pick_diagram(diagrams, diagram_type)
        if picked is None:
            sub.parse_error = f"no {diagram_type} diagram found in mdj"
            sub.ir_data = {}
            sub.ir_textual = ""
            sub.element_count = 0
            sub.relation_count = 0
            sub.container_count = 0
        else:
            sub.parse_error = ""
            sub.ir_data = picked.model_dump()
            sub.ir_textual = picked.to_textual()
            sub.element_count = len(picked.elements)
            sub.relation_count = len(picked.relations)
            sub.container_count = len(picked.containers)
    except Exception as e:
        sub.parse_error = f"parse failed: {e}"[:1900]
        sub.ir_data = {}
        sub.ir_textual = ""

    await session.commit()
    await session.refresh(sub)
    return sub


# ---------- 列表 / 详情 ----------

@router.get("", response_model=Page[SubmissionOut])
async def list_submissions(
    class_id: int | None = None,
    diagram_type: str | None = None,
    page: int = 1, page_size: int = 50,
    session: AsyncSession = Depends(get_session), _u=Depends(require_non_student),
):
    from sqlalchemy import func
    from sqlalchemy.orm import selectinload

    base = select(Submission).join(Student, Submission.student_id == Student.id)
    if class_id:
        base = base.where(Student.class_id == class_id)
    if diagram_type:
        base = base.where(Submission.diagram_type == diagram_type)

    total = (await session.execute(
        select(func.count()).select_from(base.subquery())
    )).scalar_one()

    rows = (await session.execute(
        base.options(selectinload(Submission.student), selectinload(Submission.grading_results))
        .order_by(Submission.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )).scalars().all()

    items = []
    for sub in rows:
        d = SubmissionOut.model_validate(sub).model_dump()
        d["student_code"] = sub.student.student_code if sub.student else ""
        d["student_name"] = sub.student.name if sub.student else ""
        # 每个 model_key 只保留最新一条结果（按 id 倒序）
        latest: dict[str, "GradingResult"] = {}
        for gr in sorted(sub.grading_results, key=lambda g: g.id, reverse=True):
            if gr.model_key not in latest:
                latest[gr.model_key] = gr
        d["grading_status"] = [
            GradingStatusItem(
                model_key=gr.model_key,
                status=gr.status.value if hasattr(gr.status, "value") else str(gr.status),
                score=gr.normalized_score,
            ).model_dump()
            for gr in latest.values()
        ]
        items.append(d)

    return {
        "meta": PageMeta(total=total, page=page, page_size=page_size).model_dump(),
        "items": items,
    }


# ---------- 学生查看自己的提交历史 ----------

@router.get("/my-submissions")
async def my_submissions(
    session: AsyncSession = Depends(get_session),
    current_user=Depends(get_current_user),
):
    """学生查看自己的所有提交。"""
    if current_user.role != "student":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "此接口仅限学生使用")

    from sqlalchemy.orm import selectinload
    from ..models.grading import CriterionScore

    student_code = current_user.username
    stmt = (
        select(Submission)
        .join(Student, Submission.student_id == Student.id)
        .where(Student.student_code == student_code)
        .options(
            selectinload(Submission.grading_results)
            .selectinload(GradingResult.criterion_scores)
        )
        .order_by(Submission.created_at.desc())
    )
    rows = (await session.execute(stmt)).scalars().all()

    items = []
    for sub in rows:
        latest: dict[str, GradingResult] = {}
        for gr in sorted(sub.grading_results, key=lambda g: g.id, reverse=True):
            if gr.model_key not in latest:
                latest[gr.model_key] = gr

        # 选最高分的那条结果
        best_gr = None
        best_score = None
        for gr in latest.values():
            if gr.status.value == "success":
                if best_score is None or gr.normalized_score > best_score:
                    best_score = gr.normalized_score
                    best_gr = gr

        grading_feedback = None
        if best_gr:
            grading_feedback = {
                "normalized_score": best_gr.normalized_score,
                "overall_comment": best_gr.overall_comment or "",
                "criteria": [
                    {
                        "code": cs.code,
                        "score": cs.score,
                        "max_score": cs.max_score,
                        "reasoning": cs.reasoning or "",
                    }
                    for cs in sorted(best_gr.criterion_scores, key=lambda c: c.code)
                ],
            }

        items.append({
            "id": sub.id,
            "diagram_type": sub.diagram_type,
            "problem_code": sub.problem_code,
            "problem_statement": sub.problem_statement,
            "original_filename": sub.original_filename,
            "image_filename": sub.image_filename,
            "element_count": sub.element_count,
            "relation_count": sub.relation_count,
            "parse_error": sub.parse_error,
            "best_score": best_score,
            "grading_feedback": grading_feedback,
            "created_at": sub.created_at,
        })

    return items


@router.get("/{sub_id}", response_model=SubmissionDetailOut)
async def get_submission(
    sub_id: int,
    session: AsyncSession = Depends(get_session), _u=Depends(require_non_student),
):
    sub = await session.get(Submission, sub_id)
    if sub is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    return sub


@router.get("/by-class/{class_id}/students", response_model=list[StudentOut])
async def list_students(
    class_id: int,
    session: AsyncSession = Depends(get_session), _u=Depends(require_non_student),
):
    rows = (await session.execute(
        select(Student).where(Student.class_id == class_id).order_by(Student.student_code)
    )).scalars().all()
    return list(rows)


# ---------- 学生自助上传（必须上传图片） ----------

@router.post("/student-upload", response_model=SubmissionOut, status_code=status.HTTP_201_CREATED)
async def student_upload(
    file: UploadFile = File(..., description="学生 .mdj 文件"),
    image: UploadFile = File(..., description="UML 图截图（必须）"),
    diagram_type: str = Form(..., description="use_case|class|sequence|swimlane"),
    problem_code: str = Form(..., min_length=1, description="题目编号，如 1、实验报告-1"),
    problem_statement: str = Form(..., min_length=1, description="题目描述"),
    session: AsyncSession = Depends(get_session),
    current_user=Depends(get_current_user),
):
    """学生自助上传：必须同时提交 mdj 文件和 UML 图截图。班级从账号绑定获取。"""
    if current_user.role != "student":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "此接口仅限学生使用")

    class_id = current_user.class_id
    if class_id is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "你的账号尚未分配班级，请联系管理员")

    if not image.filename:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "必须上传 UML 图截图")

    if diagram_type not in ("use_case", "class", "sequence", "swimlane"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"bad diagram_type: {diagram_type}")

    cls_ = await session.get(SchoolClass, class_id)
    if cls_ is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "class not found")

    # 使用当前用户的 username 作为 student_code
    student_code = current_user.username

    raw_bytes = await file.read()
    if len(raw_bytes) > MAX_MDJ_SIZE:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "mdj 文件过大，上限 10MB")
    try:
        raw_data = json.loads(raw_bytes.decode("utf-8"))
    except Exception as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"invalid mdj JSON: {e}")

    # upsert student
    stmt = select(Student).where(
        Student.class_id == class_id, Student.student_code == student_code,
    )
    student = (await session.execute(stmt)).scalar_one_or_none()
    if student is None:
        student = Student(
            class_id=class_id, student_code=student_code,
            name=current_user.display_name,
        )
        session.add(student)
        await session.flush()

    # 检查是否已有同 (student, type, problem) 的提交，不允许重复
    stmt2 = select(Submission).where(
        Submission.student_id == student.id,
        Submission.diagram_type == diagram_type,
        Submission.problem_code == problem_code,
    )
    existing = (await session.execute(stmt2)).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"你已提交过该题目（图类型={diagram_type}, 编号={problem_code}），不允许重复提交",
        )

    sub = Submission(
        student_id=student.id,
        diagram_type=diagram_type,
        problem_code=problem_code,
    )
    session.add(sub)

    sub.problem_statement = problem_statement
    sub.original_filename = file.filename or ""
    sub.source_format = "mdj"
    sub.raw_data = raw_data
    sub.image_filename = _save_image(image)

    # 解析
    try:
        diagrams = parse_submission(raw_data)
        picked = pick_diagram(diagrams, diagram_type)
        if picked is None:
            sub.parse_error = f"no {diagram_type} diagram found in mdj"
            sub.ir_data = {}
            sub.ir_textual = ""
            sub.element_count = 0
            sub.relation_count = 0
            sub.container_count = 0
        else:
            sub.parse_error = ""
            sub.ir_data = picked.model_dump()
            sub.ir_textual = picked.to_textual()
            sub.element_count = len(picked.elements)
            sub.relation_count = len(picked.relations)
            sub.container_count = len(picked.containers)
    except Exception as e:
        sub.parse_error = f"parse failed: {e}"[:1900]
        sub.ir_data = {}
        sub.ir_textual = ""

    await session.commit()
    await session.refresh(sub)

    # 同步批改：让学生立即获得评分反馈
    grading_result = None
    if not sub.parse_error:
        grading_result = await auto_grade_submission_sync(session, sub.id)

    # 构造返回（含评分反馈）
    grading_status = []
    grading_feedback = None
    if grading_result is not None:
        grading_status = [GradingStatusItem(
            model_key=grading_result.model_key,
            status=grading_result.status.value if hasattr(grading_result.status, 'value') else str(grading_result.status),
            score=grading_result.normalized_score,
        )]
        if grading_result.status.value == "success":
            # 加载 criterion_scores
            from ..models.grading import CriterionScore as OrmCriterionScore
            cs_rows = (await session.execute(
                select(OrmCriterionScore).where(
                    OrmCriterionScore.grading_result_id == grading_result.id
                )
            )).scalars().all()
            criteria = [
                CriterionScoreOut(
                    code=cs.code,
                    name="",
                    score=cs.score,
                    max_score=cs.max_score,
                    reasoning=cs.reasoning or "",
                )
                for cs in cs_rows
            ]
            grading_feedback = GradingFeedbackOut(
                model_key=grading_result.model_key,
                status=grading_result.status.value,
                total_score=grading_result.total_score,
                max_total_score=grading_result.max_total_score,
                normalized_score=grading_result.normalized_score,
                overall_comment=grading_result.overall_comment or "",
                criteria=criteria,
            )

    return SubmissionOut(
        id=sub.id,
        student_id=sub.student_id,
        student_code=student_code,
        student_name=current_user.display_name,
        diagram_type=sub.diagram_type,
        problem_code=sub.problem_code,
        problem_statement=sub.problem_statement,
        original_filename=sub.original_filename,
        image_filename=sub.image_filename,
        source_format=sub.source_format,
        element_count=sub.element_count,
        relation_count=sub.relation_count,
        container_count=sub.container_count,
        parse_error=sub.parse_error,
        created_at=sub.created_at,
        grading_status=grading_status,
        grading_feedback=grading_feedback,
    )
