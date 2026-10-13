"""LLM 客户端抽象基类。

- 统一 `chat()` 接口
- 带自动重试（tenacity）、超时（asyncio.wait_for）、信号量限流
- 子类实现 `_chat_once`
"""

from __future__ import annotations

import asyncio
import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Literal

from tenacity import (
    AsyncRetrying,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)


logger = logging.getLogger(__name__)


Role = Literal["system", "user", "assistant"]


@dataclass
class ChatMessage:
    role: Role
    content: str

    def dict(self) -> dict[str, str]:
        return {"role": self.role, "content": self.content}


@dataclass
class TokenUsage:
    prompt_tokens: int = 0
    completion_tokens: int = 0

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens


@dataclass
class LLMResponse:
    text: str
    usage: TokenUsage
    model: str
    elapsed_seconds: float
    raw: Any = None
    error: str | None = None


class LLMCallError(Exception):
    """可重试错误（网络超时、临时限流）。"""


class LLMFatalError(Exception):
    """致命错误（鉴权失败、prompt 过长）。"""


@dataclass
class BaseLLMClient(ABC):
    """所有 LLM 客户端的基类。

    `semaphore` 由 factory 注入，控制此模型的全局并发上限。
    """

    name: str
    model: str
    temperature: float = 0.0
    max_tokens: int = 4096
    timeout: float = 120.0
    seed: int | None = 42
    supports_json_schema: bool = False
    extra: dict[str, Any] = field(default_factory=dict)
    _semaphore: asyncio.Semaphore | None = None

    def set_semaphore(self, sem: asyncio.Semaphore) -> None:
        self._semaphore = sem

    @abstractmethod
    async def _chat_once(
        self,
        messages: list[ChatMessage],
        *,
        json_schema: dict | None = None,
    ) -> LLMResponse:
        """实际 API 调用。失败抛 LLMCallError / LLMFatalError。"""

    async def chat(
        self,
        messages: list[ChatMessage],
        *,
        json_schema: dict | None = None,
        max_attempts: int = 3,
    ) -> LLMResponse:
        """带重试 / 限流 / 超时的统一入口。"""

        async def _inner() -> LLMResponse:
            async for attempt in AsyncRetrying(
                stop=stop_after_attempt(max_attempts),
                wait=wait_exponential(multiplier=1, min=1, max=10),
                retry=retry_if_exception_type(LLMCallError),
                reraise=True,
            ):
                with attempt:
                    try:
                        t0 = time.perf_counter()
                        resp = await asyncio.wait_for(
                            self._chat_once(messages, json_schema=json_schema),
                            timeout=self.timeout,
                        )
                        resp.elapsed_seconds = time.perf_counter() - t0
                        return resp
                    except asyncio.TimeoutError as e:
                        raise LLMCallError(f"timeout after {self.timeout}s") from e
            raise LLMCallError("exhausted retries")

        if self._semaphore is not None:
            async with self._semaphore:
                return await _inner()
        return await _inner()
