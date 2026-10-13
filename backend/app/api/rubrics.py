"""指标体系：列表、详情、从 YAML 导入、切换激活版本。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.config import get_settings
from ..core.db import get_session
from ..core.security import require_non_student
from ..models.rubric import RubricCriterion, RubricVersion
from ..schemas.common import OkResponse
from ..schemas.rubric import CriterionOut, RubricDetailOut, RubricImportIn, RubricVersionOut
from ..services.grading.rubric_loader import load_rubric_from_yaml


router = APIRouter()


@router.get("/versions", response_model=list[RubricVersionOut])
async def list_versions(
    diagram_type: str | None = None,
    session: AsyncSession = Depends(get_session),
    _user=Depends(require_non_student),
) -> list[RubricVersion]:
    stmt = select(RubricVersion).order_by(
        RubricVersion.diagram_type, RubricVersion.is_active.desc(), RubricVersion.created_at.desc(),
    )
    if diagram_type:
        stmt = stmt.where(RubricVersion.diagram_type == diagram_type)
    return list((await session.execute(stmt)).scalars().all())


@router.get("/versions/{version_id}", response_model=RubricDetailOut)
async def get_version(
    version_id: int,
    session: AsyncSession = Depends(get_session),
    _user=Depends(require_non_student),
):
    rv = await session.get(RubricVersion, version_id)
    if rv is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    criteria = list(await rv.awaitable_attrs.criteria)
    return {
        **RubricVersionOut.model_validate(rv).model_dump(),
        "criteria": [CriterionOut.model_validate(c).model_dump() for c in criteria],
    }


@router.post("/import", response_model=RubricDetailOut)
async def import_rubric(
    body: RubricImportIn,
    session: AsyncSession = Depends(get_session),
    _user=Depends(require_non_student),
):
    settings = get_settings()
    path = settings.rubrics_dir / body.yaml_filename
    if not path.exists():
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"{path} not found")

    rubric = load_rubric_from_yaml(path, version_name=body.name)
    if rubric.diagram_type != body.diagram_type:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"yaml says diagram_type={rubric.diagram_type}, but body says {body.diagram_type}",
        )

    # 检查重名
    existing = (await session.execute(
        select(RubricVersion).where(
            RubricVersion.diagram_type == body.diagram_type,
            RubricVersion.name == body.name,
        )
    )).scalar_one_or_none()
    if existing:
        raise HTTPException(status.HTTP_409_CONFLICT, f"version '{body.name}' already exists")

    rv = RubricVersion(
        diagram_type=body.diagram_type,
        name=body.name,
        source_file=body.yaml_filename,
        is_active=body.activate,
        description="",
    )
    if body.activate:
        # 先把同类型其他版本置为 inactive
        await session.execute(
            update(RubricVersion)
            .where(RubricVersion.diagram_type == body.diagram_type)
            .values(is_active=False)
        )
    session.add(rv)
    await session.flush()

    for i, c in enumerate(rubric.criteria):
        session.add(RubricCriterion(
            rubric_version_id=rv.id,
            code=c.code,
            parent_code=c.parent_code,
            parent_name=c.parent_name,
            name=c.name,
            description=c.description,
            weight=c.weight,
            max_score=c.max_score,
            order_index=i,
            error_freq_total=c.error_freq_total,
            error_freq_by_class={},
            common_errors=c.common_errors,
            scoring_hint=c.scoring_hint,
            not_applicable_when=c.not_applicable_when,
        ))
    await session.commit()
    await session.refresh(rv)

    criteria_orm = list(await rv.awaitable_attrs.criteria)
    return {
        **RubricVersionOut.model_validate(rv).model_dump(),
        "criteria": [CriterionOut.model_validate(c).model_dump() for c in criteria_orm],
    }


@router.post("/versions/{version_id}/activate", response_model=OkResponse)
async def activate_version(
    version_id: int,
    session: AsyncSession = Depends(get_session),
    _user=Depends(require_non_student),
):
    rv = await session.get(RubricVersion, version_id)
    if rv is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    await session.execute(
        update(RubricVersion)
        .where(RubricVersion.diagram_type == rv.diagram_type)
        .values(is_active=False)
    )
    rv.is_active = True
    await session.commit()
    return OkResponse(message=f"activated {rv.diagram_type}/{rv.name}")
