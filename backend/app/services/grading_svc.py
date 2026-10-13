"""批改服务：从 DB 取 submission + rubric → 跑 CoT → 写 DB。

被 ARQ worker 和 API 同步端点共用。
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.grading import (
    CriterionScore as OrmCriterionScore,
    GradingResult as OrmGradingResult,
    GradingResultStatus,
    Issue as OrmIssue,
)
from ..models.submission import Submission
from ..models.token_usage import TokenUsage as OrmTokenUsage
from ..uml_grader.ir import UmlDiagram
from .grading.cot_runner import run_grading
from .grading.rubric_loader import load_rubric_from_db
from .llm.factory import get_llm_pool


logger = logging.getLogger(__name__)


async def grade_one(
    session: AsyncSession,
    *,
    result_id: int,
) -> None:
    """根据已创建的 grading_result（状态 pending/running）执行一次批改。

    out-of-band 由 ARQ worker 调用；把状态与结果全部写回数据库。
    """
    result = await session.get(OrmGradingResult, result_id)
    if result is None:
        logger.error("grading_result %s not found", result_id)
        return

    result.status = GradingResultStatus.RUNNING
    result.started_at = datetime.now(timezone.utc)
    await session.commit()

    try:
        submission = await session.get(Submission, result.submission_id)
        if submission is None:
            raise RuntimeError("submission missing")

        # 从 ir_data 恢复 UmlDiagram
        diagram = UmlDiagram.model_validate(submission.ir_data)

        # 从 DB 加载 rubric
        rubric = await load_rubric_from_db(session, result.rubric_version_id)

        # 取 LLM
        pool = await get_llm_pool()
        if result.model_key not in pool:
            raise RuntimeError(f"model {result.model_key} not in pool")
        client = pool[result.model_key]

        gr = await run_grading(
            client=client, rubric=rubric, diagram=diagram,
            problem_statement=submission.problem_statement,
            student_id=str(submission.student_id),
        )

        # 写 OrmCriterionScore + OrmIssue
        for cs in gr.criteria:
            orm_cs = OrmCriterionScore(
                grading_result_id=result.id,
                code=cs.code,
                score=cs.score,
                max_score=cs.max_score,
                not_applicable=cs.not_applicable,
                reasoning=cs.reasoning,
            )
            session.add(orm_cs)
            await session.flush()
            for iss in cs.issues:
                session.add(OrmIssue(
                    criterion_score_id=orm_cs.id,
                    element_refs=list(iss.element_ref),
                    description=iss.description,
                    severity=iss.severity,
                    suggestion=iss.suggestion,
                ))

        # 汇总
        result.total_score = gr.total_score
        result.max_total_score = gr.max_total_score
        result.normalized_score = gr.total_score  # summary step 已是 0-100
        result.overall_comment = gr.overall_comment
        result.prompt_tokens = gr.cost_tokens.prompt_tokens
        result.completion_tokens = gr.cost_tokens.completion_tokens
        result.elapsed_seconds = gr.elapsed_seconds
        result.status = (
            GradingResultStatus.SUCCESS if not gr.error else GradingResultStatus.FAILED
        )
        result.error = gr.error or ""
        result.finished_at = datetime.now(timezone.utc)

        # token_usage 审计
        session.add(OrmTokenUsage(
            grading_result_id=result.id,
            model_key=result.model_key,
            phase="full",
            prompt_tokens=gr.cost_tokens.prompt_tokens,
            completion_tokens=gr.cost_tokens.completion_tokens,
            total_tokens=gr.cost_tokens.total_tokens,
            elapsed_seconds=gr.elapsed_seconds,
        ))

        await session.commit()
    except Exception as e:  # noqa: BLE001
        logger.exception("grade_one failed result_id=%s", result_id)
        result.status = GradingResultStatus.FAILED
        result.error = str(e)[:1900]
        result.finished_at = datetime.now(timezone.utc)
        await session.commit()
