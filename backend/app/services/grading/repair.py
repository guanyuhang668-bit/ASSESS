"""LLM 输出 JSON 的提取与修复。

LLM 即使被要求严格 JSON 也常会：
1. 在 JSON 外面包裹 ```json ... ``` 代码块
2. 在 JSON 前后加前言/后话
3. 用单引号 / Python 风格 True/False/None
4. 在最后一个元素后多加逗号

这个模块尽量不调 LLM 就修复；修不动才让 CoT runner 发 repair round。
"""

from __future__ import annotations

import json
import re
from typing import Any


_FENCE_RE = re.compile(r"```(?:json|JSON)?\s*([\s\S]*?)```")
_FIRST_OBJ_RE = re.compile(r"\{[\s\S]*\}")


def extract_json(text: str) -> str:
    """从模型回复中抽出 JSON 子串（不做合法性检查）。"""
    if not text:
        return ""
    m = _FENCE_RE.search(text)
    if m:
        return m.group(1).strip()
    # 没 fence 就取第一个 { 到最后一个 }
    stripped = text.strip()
    if stripped.startswith("{") and stripped.endswith("}"):
        return stripped
    m2 = _FIRST_OBJ_RE.search(stripped)
    if m2:
        return m2.group(0)
    return stripped


def _try_loads(s: str) -> Any:
    """修复常见小错后再 loads。"""
    try:
        return json.loads(s)
    except json.JSONDecodeError:
        pass

    # 替换 Python 风格常量
    fixed = (
        s.replace("True", "true").replace("False", "false").replace("None", "null")
    )
    # 去掉尾逗号
    fixed = re.sub(r",(\s*[}\]])", r"\1", fixed)
    # 单引号 -> 双引号（简单暴力，但注意：字符串内单引号会被误伤，故只在不含双引号时替换）
    if '"' not in fixed and "'" in fixed:
        fixed = fixed.replace("'", '"')

    try:
        return json.loads(fixed)
    except json.JSONDecodeError:
        raise


def repair_json(text: str) -> tuple[Any | None, str | None]:
    """对外入口：返回 (parsed, error)。

    针对模型偶尔输出 "JSON 后面再跟说明文字" 的情况，
    在首次解析失败（通常是 Extra data 错误）时，
    尝试截取首个完整的顶层对象/数组再解析一次。
    """

    raw = extract_json(text)

    try:
        return _try_loads(raw), None
    except json.JSONDecodeError as e:
        # 回退策略：如果是 "[ ... ] 后面多了一些字" 或 "{ ... } extra"，
        # 尝试仅保留从首个 '['/'{' 到最后一个对应的 ']'/' }' 的子串；
        # 若依然失败，再尝试将一串用逗号分隔的顶层对象视为数组包裹。
        stripped = raw.strip()
        candidate: str | None = None

        if stripped.startswith("["):
            end = stripped.rfind("]")
            if end != -1:
                candidate = stripped[: end + 1]
        elif stripped.startswith("{"):
            end = stripped.rfind("}")
            if end != -1:
                candidate = stripped[: end + 1]

        if candidate is not None and candidate != raw:
            try:
                return _try_loads(candidate), None
            except json.JSONDecodeError:
                # 继续走下面的 fallback
                pass

        # 进一步 fallback：模型有时会输出
        #   {"code": ...},
        #   {"code": ...},
        #   ...
        # 这种情况下视为数组，外面补上 [ ] 再解析。
        if stripped.startswith("{") and "}," in stripped:
            wrapped = f"[{stripped}]"
            try:
                return _try_loads(wrapped), None
            except json.JSONDecodeError as e2:  # noqa: PERF203
                return None, f"JSON parse failed: {e2}"

        return None, f"JSON parse failed: {e}"
    except Exception as e:  # noqa: BLE001
        return None, f"unexpected repair error: {e}"
