"""OpenAI 以及 OpenAI 兼容 provider（DeepSeek / Qwen / vLLM 本地等）。

两类 provider 共享同一个 client 类，区别只是 base_url 和 api_key。
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

import httpx
from openai import AsyncOpenAI
from openai import APIError, APITimeoutError, AuthenticationError, RateLimitError

from .base import BaseLLMClient, ChatMessage, LLMCallError, LLMFatalError, LLMResponse, TokenUsage


@dataclass
class OpenAICompatClient(BaseLLMClient):
    api_key: str = ""  # 单个 key 或逗号/分号分隔的多个 key
    base_url: str | None = None  # None → 官方 openai.com
    _clients: list[AsyncOpenAI] = field(default_factory=list, init=False, repr=False)
    _rr_index: int = field(default=0, init=False, repr=False)

    def _parse_keys(self) -> list[str]:
        """将 api_key 拆分为多个 key（支持 , ; 空白 分隔）。"""
        if not self.api_key:
            return []
        raw = self.api_key.replace(";", ",").replace("\n", ",").replace(" ", ",")
        return [k.strip() for k in raw.split(",") if k.strip()]

    def _ensure_clients(self) -> list[AsyncOpenAI]:
        if not self._clients:
            keys = self._parse_keys()
            if not keys:
                raise LLMFatalError(f"[{self.name}] 缺少 api_key")
            for k in keys:
                kwargs: dict[str, Any] = {"api_key": k, "timeout": self.timeout}
                if self.base_url:
                    kwargs["base_url"] = self.base_url
                self._clients.append(AsyncOpenAI(**kwargs))
        return self._clients

    def _pick_client(self) -> AsyncOpenAI:
        """Round-robin 选取一个客户端。"""
        clients = self._ensure_clients()
        idx = self._rr_index % len(clients)
        self._rr_index = (self._rr_index + 1) % len(clients)
        return clients[idx]

    async def _chat_once(
        self,
        messages: list[ChatMessage],
        *,
        json_schema: dict | None = None,
    ) -> LLMResponse:
        client = self._pick_client()
        kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": [m.dict() for m in messages],
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
        }
        if self.seed is not None:
            kwargs["seed"] = self.seed

        # 尝试结构化输出
        if json_schema and self.supports_json_schema:
            # 先试 response_format=json_schema（OpenAI 新）
            try:
                kwargs["response_format"] = {
                    "type": "json_schema",
                    "json_schema": {
                        "name": json_schema.get("title", "output"),
                        "schema": json_schema,
                        "strict": False,
                    },
                }
            except Exception:
                kwargs["response_format"] = {"type": "json_object"}

        t0 = time.perf_counter()
        try:
            resp = await client.chat.completions.create(**kwargs)
        except AuthenticationError as e:
            raise LLMFatalError(f"[{self.name}] auth failed: {e}") from e
        except (APITimeoutError, RateLimitError, httpx.TransportError) as e:
            raise LLMCallError(f"[{self.name}] transient: {e}") from e
        except APIError as e:
            # response_format 不支持时 fallback 到纯文本
            if "response_format" in kwargs and "json_schema" in str(e).lower():
                kwargs["response_format"] = {"type": "json_object"}
                resp = await client.chat.completions.create(**kwargs)
            else:
                raise LLMCallError(f"[{self.name}] api: {e}") from e

        elapsed = time.perf_counter() - t0
        choice = resp.choices[0] if resp.choices else None
        text = choice.message.content if choice and choice.message else ""
        usage_obj = getattr(resp, "usage", None)
        usage = TokenUsage(
            prompt_tokens=getattr(usage_obj, "prompt_tokens", 0) or 0,
            completion_tokens=getattr(usage_obj, "completion_tokens", 0) or 0,
        )
        return LLMResponse(
            text=text or "",
            usage=usage,
            model=self.model,
            elapsed_seconds=elapsed,
            raw=resp.model_dump() if hasattr(resp, "model_dump") else None,
        )
