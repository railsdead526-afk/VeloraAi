from __future__ import annotations

import secrets

from fastapi import Response

from app.core.config import settings

ACCESS_TOKEN_COOKIE = "velora_access_token"
CSRF_COOKIE = "velora_csrf"


def issue_csrf_token() -> str:
    return secrets.token_urlsafe(32)


def set_auth_cookies(response: Response, access_token: str, csrf_token: str) -> None:
    secure = settings.app_env == "production"
    samesite = "none" if secure else "lax"
    response.set_cookie(
        ACCESS_TOKEN_COOKIE,
        access_token,
        httponly=True,
        secure=secure,
        samesite=samesite,
        max_age=settings.access_token_expire_minutes * 60,
        path="/",
    )
    response.set_cookie(
        CSRF_COOKIE,
        csrf_token,
        httponly=False,
        secure=secure,
        samesite=samesite,
        max_age=settings.access_token_expire_minutes * 60,
        path="/",
    )


def clear_auth_cookies(response: Response) -> None:
    response.delete_cookie(ACCESS_TOKEN_COOKIE, path="/")
    response.delete_cookie(CSRF_COOKIE, path="/")
