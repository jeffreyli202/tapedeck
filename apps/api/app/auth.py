"""Single-user auth. With AUTH_ENABLED=false everything runs as "local"; with
it on, the configured admin logs in for a JWT."""

from __future__ import annotations

import hmac
from datetime import UTC, datetime, timedelta

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer

from app.config import settings

LOCAL_USER = "local"
oauth2 = OAuth2PasswordBearer(tokenUrl="/auth/token", auto_error=False)


def check_password(username: str, password: str) -> bool:
    return hmac.compare_digest(username, settings.admin_username) and hmac.compare_digest(
        password, settings.admin_password
    )


def create_token(username: str) -> str:
    exp = datetime.now(UTC) + timedelta(minutes=settings.jwt_expire_minutes)
    return jwt.encode({"sub": username, "exp": exp}, settings.jwt_secret, algorithm="HS256")


def decode_token(token: str | None) -> str | None:
    if not settings.auth_enabled:
        return LOCAL_USER
    if not token:
        return None
    try:
        return jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])["sub"]
    except jwt.PyJWTError:
        return None


async def current_user(token: str | None = Depends(oauth2)) -> str:
    user = decode_token(token)
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "not authenticated", {"WWW-Authenticate": "Bearer"})
    return user
