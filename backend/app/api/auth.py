"""登录 / 我是谁。"""

from __future__ import annotations

import time
from collections import defaultdict

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.config import get_settings
from ..core.db import get_session
from ..core.security import (
    create_access_token,
    get_current_user,
    hash_password,
    verify_password,
)
from ..models.user import AppUser
from ..schemas.auth import LoginIn, TokenOut, UserOut


router = APIRouter()


# ---- 简易内存限流 ----
_RATE_LIMITS: dict[str, list[float]] = defaultdict(list)
_RATE_WINDOW = 60          # 窗口秒数
_RATE_MAX_LOGIN = 5        # 每个用户名每分钟最多 5 次登录
_RATE_MAX_IP = 100         # 单 IP 每分钟最多 100 次（适应课堂场景）


def _check_rate(key: str, limit: int) -> None:
    now = time.monotonic()
    attempts = _RATE_LIMITS[key]
    # 清理过期记录
    while attempts and attempts[0] < now - _RATE_WINDOW:
        attempts.pop(0)
    if len(attempts) >= limit:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            f"请求过于频繁，请 {_RATE_WINDOW} 秒后重试",
        )
    attempts.append(now)


@router.post("/login", response_model=TokenOut)
async def login(request: Request, body: LoginIn, session: AsyncSession = Depends(get_session)) -> TokenOut:
    _check_rate(f"login:ip:{request.client.host}", _RATE_MAX_IP)
    _check_rate(f"login:user:{body.username}", _RATE_MAX_LOGIN)
    stmt = select(AppUser).where(AppUser.username == body.username)
    user = (await session.execute(stmt)).scalar_one_or_none()
    if not user or not verify_password(body.password, user.hashed_password):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid username or password")
    if not user.is_active:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "User inactive")
    settings = get_settings()
    token = create_access_token(user.id, {"role": user.role, "name": user.display_name})
    return TokenOut(access_token=token, expires_in_min=settings.jwt_expire_minutes)


@router.get("/me", response_model=UserOut)
async def me(current=Depends(get_current_user)) -> AppUser:
    return current


class ChangePasswordIn(BaseModel):
    old_password: str
    new_password: str = Field(min_length=6, max_length=128)


@router.put("/password")
async def change_password(
    body: ChangePasswordIn,
    session: AsyncSession = Depends(get_session),
    current_user=Depends(get_current_user),
):
    """修改当前用户密码。"""
    if not verify_password(body.old_password, current_user.hashed_password):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "原密码错误")
    current_user.hashed_password = hash_password(body.new_password)
    session.add(current_user)
    await session.commit()
    return {"ok": True, "message": "密码修改成功"}
