"""Health, readiness, metrics, and build information.

`/health` is a liveness probe and must stay cheap. `/ready` is a *deep* check:
it verifies every dependency the process needs to serve real traffic, so a
deployment that cannot reach Redis or the AI provider fails its rollout instead
of silently erroring for users.
"""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import httpx
from fastapi import APIRouter, Depends, Header, HTTPException, Response, status
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core import metrics
from app.core.config import settings
from app.core.database import get_db
from app.services.maintenance_state import maintenance_health, seconds_since_last_success

router = APIRouter(tags=["System"])

_CHECK_TIMEOUT_SECONDS = 3.0


def _check_database(db: Session) -> dict[str, Any]:
    started = time.perf_counter()
    try:
        db.execute(text("SELECT 1"))
        return {"status": "ok", "latency_ms": int((time.perf_counter() - started) * 1000)}
    except Exception as exc:
        return {"status": "error", "detail": type(exc).__name__}


def _check_rate_limit_storage() -> dict[str, Any]:
    uri = settings.rate_limit_storage_uri
    if uri.startswith("memory://"):
        return {
            "status": "ok" if not settings.is_production else "error",
            "detail": "in-process storage",
        }
    if not uri.startswith(("redis://", "rediss://")):
        return {"status": "unknown", "detail": "unsupported storage scheme"}
    try:
        import redis

        client = redis.Redis.from_url(uri, socket_connect_timeout=_CHECK_TIMEOUT_SECONDS)
        client.ping()
        return {"status": "ok"}
    except Exception as exc:
        return {"status": "error", "detail": type(exc).__name__}


def _check_ai_provider() -> dict[str, Any]:
    if settings.ai_provider == "mock":
        return {"status": "ok", "detail": "mock provider"}
    base_url = (
        settings.openai_base_url if settings.ai_provider == "openai" else settings.llama_base_url
    )
    if not base_url:
        return {"status": "error", "detail": "base url not configured"}
    try:
        response = httpx.get(
            f"{base_url}/models", timeout=_CHECK_TIMEOUT_SECONDS, headers=_ai_headers()
        )
        # 401/403 still proves the endpoint is reachable and speaking HTTP.
        healthy = response.status_code < 500
        return {"status": "ok" if healthy else "error", "http_status": response.status_code}
    except Exception as exc:
        return {"status": "error", "detail": type(exc).__name__}


def _ai_headers() -> dict[str, str]:
    key = settings.openai_api_key if settings.ai_provider == "openai" else settings.llama_api_key
    return {"Authorization": f"Bearer {key}"} if key else {}


def _check_credential_encryption() -> dict[str, Any]:
    if not settings.credential_encryption_keys:
        return {
            "status": "error" if settings.is_production else "disabled",
            "detail": "CREDENTIAL_ENCRYPTION_KEYS not configured",
        }
    try:
        from app.core.crypto import get_secret_box

        box = get_secret_box()
        probe = box.encrypt("readiness-probe", associated_data="readiness")
        # A real comparison, not an assert: asserts are stripped under
        # `python -O`, which would silently disable this self-test.
        if box.decrypt(probe, associated_data="readiness") != "readiness-probe":
            return {"status": "error", "detail": "encryption round-trip mismatch"}
        return {"status": "ok", "keys": len(box.keys)}
    except Exception as exc:
        return {"status": "error", "detail": type(exc).__name__}


def _check_sandbox() -> dict[str, Any]:
    import os

    base_url = os.getenv("TERMINAL_SANDBOX_URL", "").rstrip("/")
    if not base_url:
        return {"status": "disabled", "detail": "terminal sandbox not configured"}
    try:
        response = httpx.get(f"{base_url}/health", timeout=_CHECK_TIMEOUT_SECONDS)
        return {
            "status": "ok" if response.status_code < 500 else "error",
            "http_status": response.status_code,
        }
    except Exception as exc:
        return {"status": "error", "detail": type(exc).__name__}


@router.get("/health")
def health_check():
    """Liveness. Must not touch dependencies."""
    return {
        "status": "ok",
        "service": settings.app_name,
        "environment": settings.app_env,
        "version": settings.app_version,
    }


@router.get("/ready")
def readiness_check(response: Response, db: Session = Depends(get_db)):
    """Deep readiness across every dependency required to serve traffic."""
    checks: dict[str, Any] = {
        "database": _check_database(db),
        # Never fatal: a fresh deployment has legitimately never run the job,
        # and failing readiness would block the deploy that installs the
        # schedule. "stale" is the signal to alert on.
        "maintenance": maintenance_health(db),
    }

    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = {
            "rate_limit_storage": pool.submit(_check_rate_limit_storage),
            "ai_provider": pool.submit(_check_ai_provider),
            "credential_encryption": pool.submit(_check_credential_encryption),
            "sandbox": pool.submit(_check_sandbox),
        }
        for name, future in futures.items():
            try:
                checks[name] = future.result(timeout=_CHECK_TIMEOUT_SECONDS + 2)
            except Exception as exc:
                checks[name] = {"status": "error", "detail": type(exc).__name__}

    failed = [name for name, check in checks.items() if check.get("status") == "error"]
    ready = not failed

    if not ready:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    return {
        "status": "ready" if ready else "not_ready",
        "service": settings.app_name,
        "environment": settings.app_env,
        "version": settings.app_version,
        "failed": failed,
        "checks": checks,
    }


@router.get("/info")
def info():
    return {
        "service": settings.app_name,
        "environment": settings.app_env,
        "version": settings.app_version,
        "commit": settings.git_sha,
    }


@router.get("/metrics", include_in_schema=False)
def prometheus_metrics(
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    """Prometheus scrape endpoint.

    Protected by a bearer token whenever one is configured, because request
    volumes and error rates are commercially sensitive.
    """
    if not settings.metrics_enabled:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    if settings.metrics_token:
        expected = f"Bearer {settings.metrics_token}"
        if not authorization or not _constant_time_equals(authorization, expected):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid metrics token"
            )

    # Sampled at scrape time: the job runs in a separate process, so its
    # freshness can only be read from the database.
    age = seconds_since_last_success(db)
    metrics.maintenance_age_seconds.set(-1 if age is None else age)

    payload, content_type = metrics.render()
    return Response(content=payload, media_type=content_type)


def _constant_time_equals(left: str, right: str) -> bool:
    import hmac

    return hmac.compare_digest(left, right)
