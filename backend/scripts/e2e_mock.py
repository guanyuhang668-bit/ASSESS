"""端到端离线验证：用 mock LLM 跑一份样本 mdj 的完整 CoT 批改，不依赖数据库/Redis。

用法（backend 根目录下）：
    python scripts/e2e_mock.py ../../完整/用例图/1.0.mdj --rubric configs/rubrics/use_case.yaml

输出：每条指标的分数 + 整体得分 + 用时/token。
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services.grading.cot_runner import run_grading  # noqa: E402
from app.services.grading.rubric_loader import load_rubric_from_yaml  # noqa: E402
from app.services.llm.mock_client import MockClient  # noqa: E402
from app.services.parser_svc import parse_submission, pick_diagram  # noqa: E402


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("mdj", type=Path, help="学生 .mdj 文件")
    ap.add_argument(
        "--rubric", type=Path, required=True,
        help="YAML 指标文件（如 configs/rubrics/use_case.yaml）",
    )
    ap.add_argument(
        "--diagram-type", default=None,
        help="若不指定，默认从 rubric 文件名推断",
    )
    ap.add_argument("--problem", default="", help="题目文本（可选）")
    args = ap.parse_args()

    if not args.mdj.exists():
        print(f"[!] mdj not found: {args.mdj}")
        sys.exit(1)
    if not args.rubric.exists():
        print(f"[!] rubric not found: {args.rubric}")
        sys.exit(1)

    diagram_type = args.diagram_type or args.rubric.stem
    print(f"[·] parsing {args.mdj.name} as {diagram_type}")

    with args.mdj.open(encoding="utf-8") as f:
        raw = json.load(f)
    diagrams = parse_submission(raw)
    diag = pick_diagram(diagrams, diagram_type)
    if diag is None:
        print(f"[!] no {diagram_type} diagram found; got: {[d.diagram_type for d in diagrams]}")
        sys.exit(1)

    print(f"[·] parsed: {len(diag.elements)} elements, {len(diag.relations)} relations,"
          f" {len(diag.containers)} containers")

    # 加载 rubric
    rubric = load_rubric_from_yaml(args.rubric, version_name="v1")
    print(f"[·] rubric: {rubric.diagram_type} / {rubric.version_name} · {len(rubric.criteria)} criteria")

    # Mock client，无信号量限制
    client = MockClient(name="mock", model="mock-v1", supports_json_schema=True)
    import asyncio as _a
    client.set_semaphore(_a.Semaphore(10))

    print("[·] running CoT…")
    result = await run_grading(
        client=client, rubric=rubric, diagram=diag,
        problem_statement=args.problem, student_id="e2e-test",
    )

    # 用加权法独立算一个"原始分/满分"，与 LLM 给的百分制对比
    weighted = sum(s.score * s.max_score for s in result.criteria)
    weighted_max = sum(s.max_score for s in result.criteria) or 1.0
    weighted_pct = weighted / weighted_max * 100

    print()
    print("=" * 60)
    print(f"LLM 百分制总分 : {result.total_score:.2f} / 100")
    print(f"按指标加权     : {weighted:.2f} / {weighted_max:.2f}  "
          f"({weighted_pct:.1f}%)")
    print(f"评语           : {result.overall_comment}")
    print(f"Tokens         : prompt={result.cost_tokens.prompt_tokens} "
          f"completion={result.cost_tokens.completion_tokens}")
    print(f"Elapsed        : {result.elapsed_seconds:.2f}s")
    if result.error:
        print(f"Errors         : {result.error}")
    print("-" * 60)
    for cs in result.criteria:
        na = " [N/A]" if cs.not_applicable else ""
        print(f"  {cs.code:<8} {cs.score:.2f}/{cs.max_score:.2f}{na}  "
              f"issues={len(cs.issues)}")
        if cs.reasoning:
            print(f"      reasoning: {cs.reasoning[:100]}")
        for iss in cs.issues[:2]:
            print(f"      issue: [{iss.severity}] {iss.description} "
                  f"(refs={iss.element_ref})")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
