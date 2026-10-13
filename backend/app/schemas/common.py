"""通用 schema。"""

from __future__ import annotations

from datetime import datetime
from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict

T = TypeVar("T")


class ORMBase(BaseModel):
    """所有响应模型的基类，from_attributes=True 允许 ORM → pydantic。"""

    model_config = ConfigDict(from_attributes=True)


class PageMeta(BaseModel):
    total: int
    page: int
    page_size: int


class Page(ORMBase, Generic[T]):
    meta: PageMeta
    items: list[T]


class OkResponse(BaseModel):
    ok: bool = True
    message: str = ""
