"""CoT 三步评分执行器：
Step 1 [Parse]    代码层面把 mdj → IR（不走 LLM，保证可复现）。
Step 2 [Rubric]   按一级指标分组分批喂 LLM，每批产出若干 CriterionScore。
Step 3 [Summary]  汇总各条 → total_score + overall_comment。
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, StrictUndefined, select_autoescape

from ...core.config import get_settings
from ...uml_grader.grader.schema import (
    CriterionScore, GradingResult, Issue, TokenUsage,
)
from ...uml_grader.ir import UmlDiagram
from ..llm.base import BaseLLMClient, ChatMessage
from .repair import repair_json
from .rubric_loader import CriterionDef, RubricDef


logger = logging.getLogger(__name__)


_DIAGRAM_CN = {
    "use_case": "用例图",
    "class": "类图",
    "sequence": "时序图",
    "swimlane": "泳道图",
}


def _jinja_env() -> Environment:
    settings = get_settings()
    return Environment(
        loader=FileSystemLoader(str(settings.prompts_dir)),
        autoescape=select_autoescape(enabled_extensions=()),
        undefined=StrictUndefined,
        trim_blocks=True,
        lstrip_blocks=True,
    )


@dataclass
class CotRunner:
    """一次 (diagram, rubric, model) 的 CoT 执行器。"""

    client: BaseLLMClient
    rubric: RubricDef
    diagram: UmlDiagram
    problem_statement: str = ""
    # 学生信息（写入结果表）
    student_id: str = ""

    # 运行参数
    max_repair_rounds: int = 2
    batch_strategy: str = "by_parent"
    # 可选: 'by_parent' | 'single'

    _env: Environment = field(default_factory=_jinja_env, init=False)

    # ---- 入口 ----

    async def run(self) -> GradingResult:
        t0 = time.perf_counter()
        system_msg = self._render("system.j2", {})
        all_scores: list[CriterionScore] = []
        total_prompt = 0
        total_completion = 0
        errors: list[str] = []

        # --- Step 2: 按分组分批 ---
        groups = (
            self.rubric.group_by_parent()
            if self.batch_strategy == "by_parent"
            else [[c] for c in self.rubric.criteria]
        )
        for group in groups:
            scores, pt, ct, err = await self._run_rubric_batch(system_msg, group)
            all_scores.extend(scores)
            total_prompt += pt
            total_completion += ct
            if err:
                errors.append(err)

        # --- Step 3: 汇总 ---
        total_score, comment, pt, ct, err = await self._run_summary(system_msg, all_scores)
        total_prompt += pt
        total_completion += ct
        if err:
            errors.append(err)

        # 排除 not_applicable 的指标
        applicable = [c for c in all_scores if not c.not_applicable]
        max_total = sum(c.max_score for c in applicable) or 1.0

        return GradingResult(
            student_id=self.student_id,
            diagram_type=self.diagram.diagram_type,
            model=self.client.name,
            criteria=all_scores,
            total_score=total_score,
            max_total_score=max_total,
            overall_comment=comment,
            raw_response="",  # 详细 raw 存在每一 batch 里，此处留空
            cost_tokens=TokenUsage(
                prompt_tokens=total_prompt,
                completion_tokens=total_completion,
                total_tokens=total_prompt + total_completion,
            ),
            elapsed_seconds=time.perf_counter() - t0,
            error=";".join(errors) if errors else None,
        )

    # ---- 内部 ----

    def _render(self, template: str, ctx: dict[str, Any]) -> str:
        return self._env.get_template(template).render(**ctx)

    async def _run_rubric_batch(
        self, system_msg: str, batch: list[CriterionDef],
    ) -> tuple[list[CriterionScore], int, int, str | None]:
        if not batch:
            return [], 0, 0, None

        diagram_type_cn = _DIAGRAM_CN.get(self.diagram.diagram_type, self.diagram.diagram_type)
        prompt = self._render("rubric_step.j2", {
            "diagram_type_cn": diagram_type_cn,
            "problem_statement": self.problem_statement,
            "ir_textual": self.diagram.to_textual(),
            "parent_code": batch[0].parent_code,
            "parent_name": batch[0].parent_name,
            "criteria": batch,
        })
        messages = [
            ChatMessage("system", system_msg),
            ChatMessage("user", prompt),
        ]

        pt = ct = 0
        last_error: str | None = None
        for attempt in range(self.max_repair_rounds + 1):
            resp = await self.client.chat(messages)
            pt += resp.usage.prompt_tokens
            ct += resp.usage.completion_tokens

            parsed, err = repair_json(resp.text)
            if parsed is not None and "criteria" in parsed:
                scores = self._parse_batch_scores(parsed, batch)
                return scores, pt, ct, None

            last_error = err or "missing 'criteria' in output"
            logger.warning(
                "[%s][%s] repair attempt %d: %s",
                self.client.name, batch[0].parent_code, attempt + 1, last_error,
            )
            # 追加 repair 指令
            messages.append(ChatMessage("assistant", resp.text))
            messages.append(ChatMessage(
                "user",
                "上次输出无法解析为合法 JSON，请**只**输出一个 JSON 对象，"
                "顶层 key 必须是 `criteria`，不要任何前言后话。",
            ))

        # repair 失败：对本批产出"失败占位"的 CriterionScore
        placeholder = [
            CriterionScore(
                code=c.code, score=0.0, max_score=c.max_score,
                reasoning=f"[repair failed] {last_error}",
                not_applicable=False, issues=[],
            )
            for c in batch
        ]
        return placeholder, pt, ct, f"batch {batch[0].parent_code} repair failed"

    def _parse_batch_scores(
        self, parsed: dict[str, Any], batch: list[CriterionDef],
    ) -> list[CriterionScore]:
        out: list[CriterionScore] = []
        by_code = {c.code: c for c in batch}
        seen: set[str] = set()
        for raw in parsed.get("criteria", []):
            code = raw.get("code", "")
            if code not in by_code or code in seen:
                continue
            seen.add(code)
            c = by_code[code]
            issues = []
            for r in (raw.get("issues") or []):
                sev = r.get("severity", "minor")
                if sev not in ("minor", "major", "critical"):
                    sev = "minor"
                issues.append(Issue(
                    element_ref=list(r.get("element_ref") or []),
                    description=r.get("description", "") or "",
                    severity=sev,
                    suggestion=r.get("suggestion", "") or "",
                ))
            raw_score = float(raw.get("score", 0.0))
            # 防护：clamp 到 [0, max_score]
            if raw_score > c.max_score:
                logger.warning("[%s] score %.2f > %.1f for %s, clamping", self.client.name, raw_score, c.max_score, code)
            raw_score = max(0.0, min(c.max_score, raw_score))
            out.append(CriterionScore(
                code=code,
                score=raw_score,
                max_score=c.max_score,
                reasoning=raw.get("reasoning", "") or "",
                not_applicable=bool(raw.get("not_applicable", False)),
                issues=issues,
            ))
        # 补齐缺失的 code
        for c in batch:
            if c.code not in seen:
                out.append(CriterionScore(
                    code=c.code, score=0.0, max_score=c.max_score,
                    reasoning="[missing from model output]",
                    not_applicable=False, issues=[],
                ))
        return out

    async def _run_summary(
        self, system_msg: str, scores: list[CriterionScore],
    ) -> tuple[float, str, int, int, str | None]:
        diagram_type_cn = _DIAGRAM_CN.get(self.diagram.diagram_type, self.diagram.diagram_type)
        # 为 prompt 准备更可读的字段
        rows = []
        name_by_code = {c.code: c.name for c in self.rubric.criteria}
        for s in scores:
            rows.append({
                "code": s.code,
                "name": name_by_code.get(s.code, ""),
                "score": s.score,
                "max_score": s.max_score,
                "issues": [{"description": i.description} for i in s.issues],
            })
        prompt = self._render("summary_step.j2", {
            "diagram_type_cn": diagram_type_cn,
            "criterion_scores": rows,
        })
        messages = [
            ChatMessage("system", system_msg),
            ChatMessage("user", prompt),
        ]
        resp = await self.client.chat(messages)
        parsed, err = repair_json(resp.text)
        if parsed and "total_score" in parsed:
            return (
                float(parsed.get("total_score", 0.0)),
                str(parsed.get("overall_comment", "")),
                resp.usage.prompt_tokens,
                resp.usage.completion_tokens,
                None,
            )
        # 失败：用加权计算（排除 not_applicable）
        applicable = [s for s in scores if not s.not_applicable]
        fallback = sum(s.score for s in applicable) / max(
            sum(s.max_score for s in applicable), 1e-9
        ) * 100
        return (
            fallback,
            "(auto) summary parse failed, fallback to weighted average",
            resp.usage.prompt_tokens,
            resp.usage.completion_tokens,
            err,
        )


async def run_grading(
    *, client: BaseLLMClient, rubric: RubricDef, diagram: UmlDiagram,
    problem_statement: str = "", student_id: str = "",
) -> GradingResult:
    """便捷入口。"""
    runner = CotRunner(
        client=client, rubric=rubric, diagram=diagram,
        problem_statement=problem_statement, student_id=student_id,
    )
    return await runner.run()
