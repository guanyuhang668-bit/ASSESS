"""三种 Agent 反馈策略实现。

Agent A（单次反馈）：一次性给出完整的评分与全部缺陷列表
Agent B（多轮引导）：每轮只指出 1–2 个问题，循环直到通过
Agent C（渐进式反馈）：先给方向不给答案，修改未成功则逐步深入
对照组（control）：不提供 Agent 反馈，由教师批改
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass

from ..services.llm.base import BaseLLMClient, ChatMessage
from .grading.repair import repair_json

logger = logging.getLogger(__name__)

PASS_THRESHOLD = 80.0  # 达到 80 分视为通过


@dataclass
class AgentResponse:
    """Agent 策略产出。"""
    content: str
    score: float | None = None
    passed: bool = False
    prompt_tokens: int = 0
    completion_tokens: int = 0


@dataclass
class StructuredAgentResponse(AgentResponse):
    criteria: list[dict] | None = None
    raw_response: str = ""


def _build_ir_context(ir_textual: str, diagram_type: str) -> str:
    """构建 IR 上下文给 LLM。"""
    type_cn = {
        "use_case": "用例图", "class": "类图",
        "sequence": "时序图", "swimlane": "泳道图",
    }.get(diagram_type, diagram_type)
    return f"## 学生提交的{type_cn}（IR 解析结果）\n\n{ir_textual}"


def build_rubric_prompt_text(criteria) -> str:
    """将评分指标列表格式化为 Agent prompt 可用的文本。

    criteria: CriterionDef 对象列表（来自 rubric_loader）。
    """
    if not criteria:
        return ""
    lines = [
        "## 评分指标体系",
        "",
        "请严格按照以下指标评估学生的 UML 图，并在反馈中引用指标编号（如 UC1.1）。",
        "每条指标满分 1 分，最终总分按百分制折算。",
        "",
    ]
    current_parent = None
    for c in criteria:
        pc = getattr(c, "parent_code", "") or ""
        pn = getattr(c, "parent_name", "") or ""
        parent_key = f"{pc} {pn}".strip()
        if parent_key and parent_key != current_parent:
            current_parent = parent_key
            lines.append(f"\n### {parent_key}")
        code = getattr(c, "code", "")
        name = getattr(c, "name", "")
        desc = getattr(c, "description", "")
        entry = f"- **{code} {name}**：{desc}"
        na = getattr(c, "not_applicable_when", "")
        if na:
            entry += f"（不适用条件：{na}）"
        lines.append(entry)
    return "\n".join(lines)


def _system_prompt_base() -> str:
    return (
        "你是一位专业的 UML 建模教学助手。你的任务是帮助学生提升 UML 建模能力。\n"
        "学生会上传 .mdj 文件（StarUML 格式），系统已自动解析为结构化的中间表示（IR）。\n"
        "你需要根据 IR 中的信息评价学生的 UML 图质量，并给出反馈。\n"
        "请使用中文回复。回复格式要清晰、有条理。\n"
    )


async def run_agent_a(
    client: BaseLLMClient,
    ir_textual: str,
    diagram_type: str,
    problem_statement: str,
    history: list[dict[str, str]],
    rubric_text: str = "",
) -> AgentResponse:
    """Agent A: 单次完整反馈。

    一次性给出完整评分 + 全部缺陷列表，学生自行修改后重新提交（不再有反馈）。
    """
    rubric_section = f"\n{rubric_text}\n" if rubric_text else ""
    system = (
        _system_prompt_base()
        + rubric_section
        + "\n你是 Agent A（单次反馈模式）。请一次性给出完整、详细的评估：\n"
        "1. 给出总体评分（0-100）\n"
        "2. 逐条对照指标，列出所有发现的问题和缺陷（引用指标编号，按严重程度排序）\n"
        "3. 对每个问题给出具体的修改建议\n"
        "4. 给出总结性评语\n\n"
        "请在回复的最后一行以如下格式给出评分：\n"
        "【评分】XX/100\n"
    )

    messages = [ChatMessage("system", system)]

    # 用户消息
    ir_ctx = _build_ir_context(ir_textual, diagram_type)
    user_msg = f"题目要求：{problem_statement}\n\n{ir_ctx}"
    messages.append(ChatMessage("user", user_msg))

    resp = await client.chat(messages)
    score = _extract_score(resp.text)

    return AgentResponse(
        content=resp.text,
        score=score,
        passed=score is not None and score >= PASS_THRESHOLD,
        prompt_tokens=resp.usage.prompt_tokens,
        completion_tokens=resp.usage.completion_tokens,
    )


async def run_agent_a_structured(
    client: BaseLLMClient,
    ir_textual: str,
    diagram_type: str,
    problem_statement: str,
    history: list[dict[str, str]],
    rubric_text: str = "",
    rubric_criteria=None,
) -> StructuredAgentResponse:
    rubric_section = f"\n{rubric_text}\n" if rubric_text else ""
    criteria_lines = "\n".join(
        f"{getattr(c, 'code', '')}: {getattr(c, 'name', '')} - {getattr(c, 'description', '')}"
        for c in (rubric_criteria or [])
    )
    valid_codes = {getattr(c, "code", "") for c in (rubric_criteria or [])}
    schema = {
        "type": "object",
        "properties": {
            "total_score": {"type": "number"},
            "student_feedback": {"type": "string"},
            "criterion_scores": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "code": {"type": "string"},
                        "score": {"type": "number"},
                        "na": {"type": "boolean"},
                        "issue": {"type": "boolean"},
                        "brief": {"type": "string"},
                        "reasoning": {"type": "string"},
                    },
                    "required": ["code", "score", "na", "issue", "brief"],
                },
            },
        },
        "required": ["total_score", "student_feedback", "criterion_scores"],
    }
    system = (
        _system_prompt_base()
        + rubric_section
        + "\n你是 Agent A（单次反馈模式）。请严格根据评分指标一次性完成评分和反馈。\n"
        "必须只输出合法 JSON 对象，不要 Markdown，不要代码块，不要任何额外解释。\n"
        "JSON 字段：\n"
        "- total_score: 0~100 的总分。\n"
        "- student_feedback: 面向学生的中文反馈，必须按指标编号说明主要优点、问题和修改建议。\n"
        "- criterion_scores: 每条指标一个对象。\n"
        "criterion_scores 字段：code 为指标编号；score 为 0.0~1.0；na 表示不适用；issue 表示是否存在问题；brief 为简短问题；reasoning 为评分依据。\n"
    )
    ir_ctx = _build_ir_context(ir_textual, diagram_type)
    user_msg = (
        f"题目要求：{problem_statement}\n\n"
        f"{ir_ctx}\n\n"
        f"指标清单：\n{criteria_lines}\n\n"
        "请按上述 JSON 格式输出。"
    )
    resp = await client.chat([
        ChatMessage("system", system),
        ChatMessage("user", user_msg),
    ], json_schema=schema)
    parsed, err = repair_json(resp.text)
    if err or not isinstance(parsed, dict):
        logger.warning("run_agent_a_structured repair_json failed: %s", err)
        fallback_score = _extract_score(resp.text)
        return StructuredAgentResponse(
            content=resp.text,
            score=fallback_score,
            passed=fallback_score is not None and fallback_score >= PASS_THRESHOLD,
            prompt_tokens=resp.usage.prompt_tokens,
            completion_tokens=resp.usage.completion_tokens,
            criteria=[],
            raw_response=resp.text,
        )
    try:
        score = max(0.0, min(100.0, float(parsed.get("total_score", 0))))
    except Exception:
        score = None
    feedback = str(parsed.get("student_feedback", "")).strip()
    criteria = []
    for item in parsed.get("criterion_scores", []) or []:
        if not isinstance(item, dict):
            continue
        code = str(item.get("code", "")).strip()
        if valid_codes and code not in valid_codes:
            continue
        try:
            item_score = max(0.0, min(1.0, float(item.get("score", 0))))
        except Exception:
            item_score = 0.0
        criteria.append({
            "code": code,
            "score": item_score,
            "not_applicable": bool(item.get("na", False)),
            "has_issue": bool(item.get("issue", False)),
            "brief": str(item.get("brief", ""))[:500],
            "reasoning": str(item.get("reasoning", item.get("brief", "")))[:2000],
        })
    if not feedback:
        feedback = json.dumps(parsed, ensure_ascii=False)
    if score is not None and "【评分】" not in feedback:
        feedback = f"{feedback}\n\n【评分】{score:.0f}/100"
    return StructuredAgentResponse(
        content=feedback,
        score=score,
        passed=score is not None and score >= PASS_THRESHOLD,
        prompt_tokens=resp.usage.prompt_tokens,
        completion_tokens=resp.usage.completion_tokens,
        criteria=criteria,
        raw_response=resp.text,
    )


AGENT_B_PASS_THRESHOLD = 95.0  # Agent B 需要更高的分数才自动通过


async def run_agent_b(
    client: BaseLLMClient,
    ir_textual: str,
    diagram_type: str,
    problem_statement: str,
    history: list[dict[str, str]],
    round_number: int,
    ir_changed: bool = True,
    prev_score: float | None = None,
    rubric_text: str = "",
) -> AgentResponse:
    """Agent B: 多轮引导反馈。

    每轮只指出 1-2 个问题，学生修改后重新提交，循环直到所有问题解决。
    具备上下文记忆：记住之前指出的问题，已修正的不重复，未修正的继续指出。
    关键：通过 IR 结构化对比检测学生是否真正修改了图。
    """
    # --- 未做修改时直接拒绝，不调用 LLM ---
    if round_number > 0 and not ir_changed:
        content = (
            "⚠️ **检测到你提交的文件与上一轮完全相同，没有做任何修改。**\n\n"
            "请根据上面的反馈建议修改你的 UML 图后再重新提交。\n"
            "具体需要修改的内容请参考我上一轮给出的问题和建议。\n\n"
            "---\n\n"
        )
        if prev_score is not None:
            content += f"【评分】{prev_score:.0f}/100\n"
        else:
            content += "【评分】请先修改后再评分\n"
        return AgentResponse(
            content=content,
            score=prev_score,  # 分数不变
            passed=False,
            prompt_tokens=0,
            completion_tokens=0,
        )

    rubric_section = f"\n{rubric_text}\n" if rubric_text else ""
    system = (
        _system_prompt_base()
        + rubric_section
        + "\n你是 Agent B（多轮引导模式）。你的反馈策略是分批次、循环引导：\n"
        "\n## 核心原则\n"
        "1. **每轮只指出 1-2 个最重要的问题**（引用指标编号），不要一次列出所有问题\n"
        "2. **严格基于 IR 结构分析**：你的评分和反馈必须严格基于当前提交的 IR 内容。\n"
        "   - 仔细对比当前 IR 与之前轮次的 IR 内容\n"
        "   - 如果某个问题在 IR 中仍然存在（元素/关系/命名未改变），则该问题**未修正**\n"
        "   - 只有 IR 中确实体现了修改（新增元素、删除错误关系、重命名等），才能认为问题已修正\n"
        "   - **绝对禁止**：IR 内容相同却声称问题已修正、或无根据地提高分数\n"
        "3. **上下文记忆**：你必须记住之前各轮指出的问题：\n"
        "   - 如果之前指出的问题在当前 IR 中已修正 → 给予肯定\n"
        "   - 如果之前指出的问题在当前 IR 中未修正 → 再次指出，给更具体提示\n"
        "4. **评分一致性**：如果图没有实质改进，评分不应提高。相同的问题 = 相同的分数\n"
        "5. **逐批推进**：当前批次的问题确认修正后，再指出下一批新问题\n"
        "\n## 回复格式\n"
        "- 先明确说明本轮对比结果：哪些地方在 IR 中发生了变化、哪些没有变化\n"
        "- 对于确实修正的问题给予肯定\n"
        "- 对于未修正的问题再次指出\n"
        "- 列出本轮需要修改的 1-2 个问题及修改方向\n"
        "- 最后一行给出评分：【评分】XX/100\n"
        "\n## 完成条件\n"
        "当所有重要问题都已修正、图质量达到优秀水平（≥95分）时：\n"
        "- 给出总结性肯定\n"
        "- 在最后输出 **【全部通过】** 标记\n"
        "- 只有确认没有任何需要修改的问题时才输出此标记\n"
        "\n⚠️ 重要：如果还有任何问题未修正或有新的问题，不要输出【全部通过】，继续引导修改。\n"
        "⚠️ 严禁欺骗：评分必须真实反映当前 IR 的质量。如果学生没有改进，分数绝对不能提高！\n"
    )

    messages = [ChatMessage("system", system)]

    # 注入历史对话（完整上下文记忆）
    for h in history:
        messages.append(ChatMessage(h["role"], h["content"]))

    # 当前轮的 IR
    ir_ctx = _build_ir_context(ir_textual, diagram_type)
    if round_number == 0:
        user_msg = f"题目要求：{problem_statement}\n\n{ir_ctx}\n\n请检查我的 UML 图，每次只指出 1-2 个最重要的问题。"
    else:
        user_msg = (
            f"我已修改了图，请再次检查：\n\n{ir_ctx}\n\n"
            f"请严格对比当前 IR 与之前的 IR 内容，只有实际发生变化的地方才能认为是修正。"
            f"告诉我哪些确实改了、哪些没改，然后指出下一步需要改进的 1-2 个问题。"
        )
        if prev_score is not None:
            user_msg += f"\n（上一轮评分为 {prev_score:.0f} 分，如果没有实质改进，评分不应提高）"
    messages.append(ChatMessage("user", user_msg))

    resp = await client.chat(messages)
    score = _extract_score(resp.text)

    # 安全检查：如果 IR 变化很小但分数提高超过 15 分，强制限制
    if prev_score is not None and score is not None:
        if score > prev_score + 15:
            logger.warning(
                "Agent B score jump too large: %s -> %s, capping",
                prev_score, score,
            )
            score = prev_score + 10  # 最多每轮提升 10 分

    # Agent B 的通过判定：显式标记 或 分数 >= 95
    all_passed = "【全部通过】" in resp.text
    passed = all_passed or (score is not None and score >= AGENT_B_PASS_THRESHOLD)

    return AgentResponse(
        content=resp.text,
        score=score,
        passed=passed,
        prompt_tokens=resp.usage.prompt_tokens,
        completion_tokens=resp.usage.completion_tokens,
    )


async def run_agent_c(
    client: BaseLLMClient,
    ir_textual: str,
    diagram_type: str,
    problem_statement: str,
    history: list[dict[str, str]],
    round_number: int,
    prev_score: float | None,
    ir_changed: bool = True,
    rubric_text: str = "",
) -> AgentResponse:
    """Agent C: 渐进式反馈。

    先给出问题方向（不给具体答案）→
    学生修改后重新提交：
      - 修改成功 → 总结肯定并结束
      - 修改未成功 → 逐步深入指出具体问题，继续引导
    """
    # --- 未做修改时直接拒绝 ---
    if round_number > 0 and not ir_changed:
        content = (
            "⚠️ **检测到你提交的文件与上一轮完全相同，没有做任何修改。**\n\n"
            "请根据我之前的提示，思考并修改你的 UML 图后再重新提交。\n\n"
            "---\n\n"
        )
        if prev_score is not None:
            content += f"【评分】{prev_score:.0f}/100\n"
        return AgentResponse(
            content=content,
            score=prev_score,
            passed=False,
            prompt_tokens=0,
            completion_tokens=0,
        )

    rubric_section = f"\n{rubric_text}\n" if rubric_text else ""
    system = (
        _system_prompt_base()
        + rubric_section
        + "\n你是 Agent C（渐进式反馈模式）。你的反馈策略是循序渐进的：\n"
        "- 第一轮：只给出涉及的指标方向和大致范围（引用指标编号），不给具体答案，让学生自己思考\n"
        "- 如果学生修改后有改进（IR 内容确实发生变化）：给予肯定，并指出剩余问题方向\n"
        "- 如果学生修改后没有改进或改错了：逐步深入，给出更具体的提示\n"
        "- 随着轮次增加，提示越来越具体，直到学生理解并修改正确\n"
        "- 当图达到较好水平时，给予总结性肯定并告知通过\n\n"
        "⚠️ 重要：你的评分必须严格基于当前 IR 的实际质量。如果 IR 没有实质改进，分数不应提高！\n\n"
        "请在回复的最后一行以如下格式给出当前评分：\n"
        "【评分】XX/100\n"
    )

    messages = [ChatMessage("system", system)]

    # 注入历史
    for h in history:
        messages.append(ChatMessage(h["role"], h["content"]))

    # 当前轮
    ir_ctx = _build_ir_context(ir_textual, diagram_type)
    if round_number == 0:
        user_msg = f"题目要求：{problem_statement}\n\n{ir_ctx}\n\n请检查我的 UML 图。"
    else:
        improved = ""
        if prev_score is not None:
            improved = f"（上一轮评分为 {prev_score:.0f} 分，如果没有实质改进评分不应提高）\n"
        user_msg = f"我已修改了图，请再次检查：\n{improved}\n{ir_ctx}"
    messages.append(ChatMessage("user", user_msg))

    resp = await client.chat(messages)
    score = _extract_score(resp.text)

    # 安全检查：限制单轮最大提分
    if prev_score is not None and score is not None:
        if score > prev_score + 15:
            logger.warning("Agent C score jump too large: %s -> %s, capping", prev_score, score)
            score = prev_score + 10

    return AgentResponse(
        content=resp.text,
        score=score,
        passed=score is not None and score >= PASS_THRESHOLD,
        prompt_tokens=resp.usage.prompt_tokens,
        completion_tokens=resp.usage.completion_tokens,
    )


async def extract_criterion_scores(
    client: BaseLLMClient,
    agent_feedback: str,
    ir_textual: str,
    rubric_criteria,
) -> list[dict] | None:
    """从 Agent 反馈 + IR 中提取逐条指标的结构化评分。

    额外调用一次 LLM，要求仅输出 JSON 数组。
    失败时返回 None（不阻塞主流程）。
    """
    if not rubric_criteria or not agent_feedback:
        return None

    # 紧凑的指标清单
    criteria_lines = "\n".join(
        f"{getattr(c, 'code', '')}: {getattr(c, 'name', '')}"
        for c in rubric_criteria
    )
    valid_codes = {getattr(c, "code", "") for c in rubric_criteria}

    ir_short = ir_textual[:3000] if ir_textual else ""

    prompt = (
        "根据以下 UML 图的 IR 和评估反馈，对每条指标给出结构化评分。\n\n"
        f"## 学生 IR\n{ir_short}\n\n"
        f"## 评估反馈\n{agent_feedback}\n\n"
        f"## 指标清单\n{criteria_lines}\n\n"
        "请输出 JSON 数组，每条指标一个对象，格式：\n"
        '[{"code":"UC1.1","score":0.8,"na":false,"issue":true,"brief":"缺少管理员"}]\n\n'
        "字段：\n"
        "- code: 指标编号（必须与指标清单中的编号一致）\n"
        "- score: 0.0~1.0（1.0=完全满足，0.0=完全不满足）\n"
        "- na: 不适用时 true，score 设 0\n"
        "- issue: 存在问题时 true\n"
        "- brief: ≤20字简述，无问题可留空\n\n"
        "仅输出 JSON 数组，不要任何其他内容。"
    )

    try:
        resp = await client.chat([
            ChatMessage("system", "你是一个 JSON 评分提取器。仅输出合法 JSON 数组，不要任何解释。"),
            ChatMessage("user", prompt),
        ])

        scores, err = repair_json(resp.text)
        if err or scores is None:
            logger.warning("extract_criterion_scores: repair_json failed: %s", err)
            return None
        if not isinstance(scores, list):
            logger.warning("extract_criterion_scores: expected list, got %s", type(scores))
            return None

        result = []
        for item in scores:
            if not isinstance(item, dict):
                continue
            code = str(item.get("code", ""))
            if code not in valid_codes:
                continue
            result.append({
                "code": code,
                "score": max(0.0, min(1.0, float(item.get("score", 0)))),
                "not_applicable": bool(item.get("na", False)),
                "has_issue": bool(item.get("issue", False)),
                "brief": str(item.get("brief", ""))[:500],
            })

        logger.info("extract_criterion_scores: got %d/%d criteria", len(result), len(valid_codes))
        return result if result else None
    except Exception as e:
        logger.warning("extract_criterion_scores failed: %s", e)
        return None


def _extract_score(text: str) -> float | None:
    """从 Agent 回复中提取【评分】XX/100 格式的分数。"""
    import re
    # 匹配 【评分】85/100 或 【评分】85 等格式
    patterns = [
        r"【评分】\s*(\d+(?:\.\d+)?)\s*/\s*100",
        r"【评分】\s*(\d+(?:\.\d+)?)",
        r"\*\*评分\*\*[：:]\s*(\d+(?:\.\d+)?)\s*/\s*100",
        r"评分[：:]\s*(\d+(?:\.\d+)?)\s*/\s*100",
    ]
    for pat in patterns:
        m = re.search(pat, text)
        if m:
            score = float(m.group(1))
            return max(0.0, min(100.0, score))
    return None
