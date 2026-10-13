"""LLM 客户端抽象基类。

约束所有 provider 必须实现一个统一 `chat` 接口，返回文本 + token 用量。
把 retry / 限流 / 日志放在这里，具体 provider 只关心协议转换。
"""

from __future__ import annotations

import asyncio
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Literal

from tenacity import (
    AsyncRetrying,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from ..grader.schema import TokenUsage


logger = logging.getLogger(__name__)


Role = Literal["system", "user", "assistant"]


@dataclass
class ChatMessage:
    role: Role
    content: str


@dataclass
class LLMResponse:
    text: str                  # 模型回复正文
    usage: TokenUsage          # token 用量
    model: str                 # 实际使用的模型名
    elapsed_seconds: float     # 本次调用耗时
    raw: Any = None            # provider 原始 response，便于调试
    error: str | None = None   # 非致命错误（被 retry 吃掉的）


class LLMCallError(Exception):
    """标记可重试的调用错误。"""


class LLMFatalError(Exception):
    """标记不可重试的致命错误（如鉴权失败）。"""


@dataclass
class BaseLLMClient(ABC):
    """所有 LLM 客户端共享的骨架。

    子类需实现 `_chat_once`，基类负责重试与超时控制。
    """

    name: str                           # 在 models.yaml 中的 key，例如 "gpt4o_mini"
    model: str                          # provider 端的真实 model 名
    temperature: float = 0.0
    max_tokens: int = 4096
    timeout: float = 120.0
    seed: int | None = 42
    supports_json_schema: bool = False
    extra: dict[str, Any] = field(default_factory=dict)

    # --- 子类实现 ---

    @abstractmethod
    async def _chat_once(
        self,
        messages: list[ChatMessage],
        *,
        json_schema: dict | None = None,
    ) -> LLMResponse:
        """实际的一次 API 调用；失败应抛 LLMCallError / LLMFatalError。"""

    # --- 公共入口：带重试 ---

    async def chat(
        self,
        messages: list[ChatMessage],
        *,
        json_schema: dict | None = None,
        max_attempts: int = 3,
    ) -> LLMResponse:
        """重试式 chat；网络错误会指数退避重试，致命错误立即抛出。"""
        last_exc: Exception | None = None
        async for attempt in AsyncRetrying(
            stop=stop_after_attempt(max_attempts),
            wait=wait_exponential(multiplier=1, min=1, max=10),
            retry=retry_if_exception_type(LLMCallError),
            reraise=True,
        ):
            with attempt:
                try:
                    return await asyncio.wait_for(
                        self._chat_once(messages, json_schema=json_schema),
                        timeout=self.timeout,
                    )
                except asyncio.TimeoutError as e:
                    last_exc = e
                    logger.warning("[%s] timeout after %.0fs, retrying...", self.name, self.timeout)
                    raise LLMCallError(f"timeout after {self.timeout}s") from e
        # 理论不会到这里
        raise LLMCallError(f"exhausted retries: {last_exc}")
