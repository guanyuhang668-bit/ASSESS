"""LLM 客户端工厂 + 全局池。

读 configs/models.yaml + 环境变量，为每个 provider 实例化客户端，
并注入 asyncio.Semaphore 限制并发。

使用方式：
    pool = await get_llm_pool()
    client = pool["deepseek_v4"]
    resp = await client.chat(messages)
"""

from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path
from typing import Any

import yaml

from ...core.config import get_settings
from .base import BaseLLMClient, LLMFatalError
from .anthropic_client import AnthropicClient
from .mock_client import MockClient
from .openai_compat import OpenAICompatClient


logger = logging.getLogger(__name__)

_POOL: dict[str, BaseLLMClient] | None = None
_POOL_LOCK = asyncio.Lock()


def _resolve_api_key(env_var: str | None) -> str:
    if not env_var:
        return ""
    settings = get_settings()
    # 允许通过 settings 字段读取（pydantic-settings 已从 .env 加载过了）
    direct = getattr(settings, env_var.lower(), None)
    if direct:
        return str(direct)
    return os.getenv(env_var, "")


def _build_client(
    key: str, spec: dict[str, Any], defaults: dict[str, Any],
) -> BaseLLMClient:
    provider = spec.get("provider")
    if not provider:
        raise LLMFatalError(f"[{key}] missing provider in models.yaml")

    common = dict(
        name=key,
        model=spec["model"],
        temperature=spec.get("temperature", defaults.get("temperature", 0.0)),
        max_tokens=spec.get("max_tokens", defaults.get("max_tokens", 4096)),
        timeout=spec.get("timeout", defaults.get("timeout", 120)),
        seed=spec.get("seed", defaults.get("seed", 42)),
        supports_json_schema=spec.get("supports_json_schema", False),
        extra={k: v for k, v in spec.items() if k not in {
            "provider", "model", "temperature", "max_tokens", "timeout",
            "seed", "supports_json_schema", "base_url", "env_var",
        }},
    )

    if provider == "mock":
        return MockClient(**common)

    if provider == "anthropic":
        api_key = _resolve_api_key(spec.get("env_var", "ANTHROPIC_API_KEY"))
        return AnthropicClient(**common, api_key=api_key)

    if provider in ("openai", "openai_compat"):
        api_key = _resolve_api_key(spec.get("env_var", "OPENAI_API_KEY"))
        base_url = spec.get("base_url")
        return OpenAICompatClient(**common, api_key=api_key, base_url=base_url)

    raise LLMFatalError(f"[{key}] unsupported provider: {provider}")


def load_client(
    key: str, config_path: Path | None = None,
) -> BaseLLMClient:
    """按 key 从 models.yaml 加载单个客户端（不装 semaphore）。"""
    path = config_path or get_settings().models_yaml
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    defaults = data.get("defaults", {})
    models = data.get("models", {})
    if key not in models:
        raise LLMFatalError(f"model key '{key}' not found in {path}")
    return _build_client(key, models[key], defaults)


def load_all_clients(
    config_path: Path | None = None, *, skip_missing_key: bool = True,
) -> dict[str, BaseLLMClient]:
    """加载 models.yaml 中所有客户端。

    skip_missing_key=True 时，无 api_key 的客户端被跳过（不报错），
    但 mock provider 始终创建。
    """
    path = config_path or get_settings().models_yaml
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    defaults = data.get("defaults", {})
    models = data.get("models", {})

    out: dict[str, BaseLLMClient] = {}
    for key, spec in models.items():
        try:
            out[key] = _build_client(key, spec, defaults)
        except LLMFatalError as e:
            if skip_missing_key and "api_key" in str(e).lower():
                logger.warning("skip %s: %s", key, e)
                continue
            raise

    # 为每个 client 装信号量
    settings = get_settings()
    default_n = settings.llm_concurrency_default
    per_model = settings.llm_concurrency_per_model
    for k, client in out.items():
        n = per_model.get(k, default_n)
        client.set_semaphore(asyncio.Semaphore(n))
    return out


async def get_llm_pool(
    config_path: Path | None = None,
) -> dict[str, BaseLLMClient]:
    """进程内单例池。"""
    global _POOL
    async with _POOL_LOCK:
        if _POOL is None:
            _POOL = load_all_clients(config_path)
            logger.info("LLM pool loaded: %s", list(_POOL.keys()))
        return _POOL
