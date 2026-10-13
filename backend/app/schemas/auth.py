from __future__ import annotations

from pydantic import BaseModel, Field

from .common import ORMBase


class LoginIn(BaseModel):
    username: str
    password: str


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in_min: int


class UserOut(ORMBase):
    id: int
    username: str
    display_name: str
    role: str
    is_active: bool
    class_id: int | None = None
    experiment_group: str | None = None
    cohort_group: str | None = None
    problem_order: str | None = None
    session_group: str | None = None


class UserCreateIn(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    password: str = Field(min_length=6, max_length=128)
    display_name: str = ""
    role: str = "researcher"
