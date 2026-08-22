import logging
import time

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.api.v1 import (
    agent_stream,
    auth,
    conversations,
    integrations,
    payments,
    rag,
    system,
)
from app.core import metrics
from app.core.config import settings
from app.core.observability import configure_logging, log_request, set_request_id
from app.core.rate_limit import limiter

configure_logging(settings.log_level)
logger = logging.getLogger("veloraai")

app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    docs_url=None if settings.is_production else "/docs",
    redoc_url=None if settings.is_production else "/redoc",
    openapi_url=None if settings.is_production else "/openapi.json",
)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

if settings.trusted_hosts:
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.trusted_hosts)

app.add_middleware(GZipMiddleware, minimum_size=1024)

if settings.cors_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
        expose_headers=["X-Request-ID"],
        max_age=600,
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    request_id = set_request_id(request.headers.get("X-Request-ID"))
    logger.exception(
        "Unhandled application error: %s %s request_id=%s",
        request.method,
        request.url.path,
        request_id,
    )
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error", "request_id": request_id},
        headers={"X-Request-ID": request_id},
    )


@app.middleware("http")
async def observability(request: Request, call_next):
    request_id = set_request_id(request.headers.get("X-Request-ID"))
    route = metrics.normalize_path(request.url.path)
    started = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception:
        duration_ms = int((time.perf_counter() - started) * 1000)
        log_request(
            method=request.method, path=request.url.path, status_code=500, duration_ms=duration_ms
        )
        metrics.http_requests_total.labels(request.method, route, "500").inc()
        metrics.http_request_duration_seconds.labels(request.method, route).observe(
            duration_ms / 1000
        )
        raise
    duration_ms = int((time.perf_counter() - started) * 1000)
    response.headers["X-Request-ID"] = request_id
    log_request(
        method=request.method,
        path=request.url.path,
        status_code=response.status_code,
        duration_ms=duration_ms,
    )
    metrics.http_requests_total.labels(request.method, route, str(response.status_code)).inc()
    metrics.http_request_duration_seconds.labels(request.method, route).observe(duration_ms / 1000)
    return response


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    response.headers.setdefault(
        "Permissions-Policy", "camera=(), microphone=(), geolocation=(), payment=()"
    )
    response.headers.setdefault("Cross-Origin-Opener-Policy", "same-origin")
    response.headers.setdefault("Cross-Origin-Resource-Policy", "same-site")
    response.headers.setdefault(
        "Content-Security-Policy",
        "default-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'",
    )
    if settings.is_production:
        response.headers.setdefault(
            "Strict-Transport-Security", "max-age=31536000; includeSubDomains; preload"
        )
    return response


@app.on_event("startup")
async def on_startup() -> None:
    logger.info(
        "starting %s version=%s env=%s commit=%s",
        settings.app_name,
        settings.app_version,
        settings.app_env,
        settings.git_sha,
    )
    if settings.sentry_dsn:
        try:
            import sentry_sdk

            sentry_sdk.init(
                dsn=settings.sentry_dsn,
                environment=settings.app_env,
                release=settings.app_version,
                traces_sample_rate=0.1,
                send_default_pii=False,
            )
            logger.info("sentry error reporting enabled")
        except ImportError:
            logger.warning("SENTRY_DSN is set but sentry-sdk is not installed")


# Native agent streaming must win for the canonical /messages/stream route.
# The legacy conversations router still exposes the old implementation as a fallback.
app.include_router(agent_stream.router, prefix="/api/v1")
app.include_router(conversations.router, prefix="/api/v1")
app.include_router(system.router, prefix="/api/v1")
app.include_router(auth.router, prefix="/api/v1")
app.include_router(rag.router, prefix="/api/v1")
app.include_router(payments.router, prefix="/api/v1")
app.include_router(integrations.router, prefix="/api/v1")
