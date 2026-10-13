"""Anthropic Claude 客户端。"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from anthropic import AsyncAnthropic
from anthropic import APIError, APITimeoutError, AuthenticationError, RateLimitError

from .base import BaseLLMClient, ChatMessage, LLMCallError, LLMFatalError, LLMResponse, TokenUsage


@dataclass
class AnthropicClient(BaseLLMClient):
    api_key: str = ""
    _client: AsyncAnthropic | None = field(default=None, init=False, repr=False)

    def _ensure_client(self) -> AsyncAnthropic:
        if self._client is None:
            if not self.api_key:
                raise LLMFatalError(f"[{self.name}] 缺少 ANTHROPIC_API_KEY")
            self._client = AsyncAnthropic(api_key=self.api_key, timeout=self.timeout)
        return self._client

    async def _chat_once(
        self,
        messages: list[ChatMessage],
        *,
        json_schema: dict | None = None,
    ) -> LLMResponse:
        client = self._ensure_client()

        # Anthropic 把 system 单独作为参数，其余 messages 只能是 user/assistant
        system_parts = [m.content for m in messages if m.role == "system"]
        body_msgs = [m.dict() for m in messages if m.role != "system"]

        kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": body_msgs,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
        }
        if system_parts:
            kwargs["system"] = "\n\n".join(system_parts)

        t0 = time.perf_counter()
        try:
            resp = await client.messages.create(**kwargs)
        except AuthenticationError as e:
            raise LLMFatalError(f"[{self.name}] auth: {e}") from e
        except (APITimeoutError, RateLimitError) as e:
            raise LLMCallError(f"[{self.name}] transient: {e}") from e
        except APIError as e:
            raise LLMCallError(f"[{self.name}] api: {e}") from e

        elapsed = time.perf_counter() - t0
        text_parts: list[str] = []
        for block in (resp.content or []):
            if getattr(block, "type", "") == "text":
                text_parts.append(block.text)
        text = "".join(text_parts)

        usage = TokenUsage(
            prompt_tokens=getattr(resp.usage, "input_tokens", 0) or 0,
            completion_tokens=getattr(resp.usage, "output_tokens", 0) or 0,
        )
        return LLMResponse(
            text=text,
            usage=usage,
            model=self.model,
            elapsed_seconds=elapsed,
            raw=resp.model_dump() if hasattr(resp, "model_dump") else None,
        )
