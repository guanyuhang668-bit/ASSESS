"""本地合成输出的 mock 客户端，不联网，用于端到端调试与并发压测。

策略：从 prompt 中抽取待评分的 `criteria.code` 列表，
合成一个符合 schema 的 JSON 对象返回。
"""

from __future__ import annotations

import asyncio
import json
import random
import re
import time
from dataclasses import dataclass

from .base import BaseLLMClient, ChatMessage, LLMResponse, TokenUsage


# 从 rubric_step prompt 抽 code：兼容 `### UC1.1 ...` / `- UC1.1 ...` / `"code": "UC1.1"`
_CODE_RE = re.compile(
    r"(?:^\s*(?:#+|[-*])\s*|[\"']code[\"']\s*:\s*[\"'])([A-Z]{1,4}\d+(?:\.\d+)?)\b",
    re.MULTILINE,
)


@dataclass
class MockClient(BaseLLMClient):
    latency_ms: int = 50

    async def _chat_once(
        self,
        messages: list[ChatMessage],
        *,
        json_schema: dict | None = None,
    ) -> LLMResponse:
        text_all = "\n".join(m.content for m in messages)
        # 抽 code 并去重（同一 code 在 prompt 的标题与 JSON 骨架里会重复出现）
        codes: list[str] = []
        seen: set[str] = set()
        for c in _CODE_RE.findall(text_all):
            if c not in seen:
                seen.add(c)
                codes.append(c)

        # 在 rubric_step prompt 里会用 [Elements] 列出元素，挑 1 个当 element_ref
        element_ids = re.findall(r"\b-\s*(AAAA[A-Za-z0-9+/=]+)\b", text_all)
        sample_ref = element_ids[0] if element_ids else ""

        rng = random.Random(hash(text_all) & 0xFFFFFFFF)

        # 判断这是 rubric 批还是 summary 步
        is_summary = "汇总" in text_all or "overall" in text_all.lower() or not codes

        if is_summary:
            payload = {
                "total_score": round(rng.uniform(60, 95), 2),
                "overall_comment": "(mock) 整体完成度尚可，存在若干冗余与命名问题。",
            }
        else:
            criteria = []
            for c in codes:
                s = round(rng.uniform(0.5, 1.0), 2)
                criteria.append({
                    "code": c,
                    "score": s,
                    "reasoning": f"(mock) 对 {c} 的推理：观察到若干元素，按标准判定得分 {s}.",
                    "not_applicable": False,
                    "issues": (
                        []
                        if s > 0.85 or not sample_ref
                        else [{
                            "element_ref": [sample_ref],
                            "description": f"(mock) {c} 存在问题",
                            "severity": "minor",
                            "suggestion": "(mock) 请核对命名与粒度。",
                        }]
                    ),
                })
            payload = {"criteria": criteria}

        await asyncio.sleep(self.latency_ms / 1000)
        text_out = json.dumps(payload, ensure_ascii=False)
        usage = TokenUsage(
            prompt_tokens=len(text_all) // 4,
            completion_tokens=len(text_out) // 4,
        )
        return LLMResponse(
            text=text_out, usage=usage,
            model=self.model, elapsed_seconds=self.latency_ms / 1000,
            raw={"mock": True},
        )
