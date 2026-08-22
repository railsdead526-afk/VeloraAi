import logging
import time

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.api.v1 import agent_stream, auth, system, conversations, rag, payments
from app.core.config import settings
from app.core.observability import log_request, set_request_id
from app.core.rate_limit import limiter

logger = logging.getLogger("veloraai")

app = FastAPI(title=settings.app_name)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

if settings.cors_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
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
    started = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception:
        duration_ms = int((time.perf_counter() - started) * 1000)
        log_request(method=request.method, path=request.url.path, status_code=500, duration_ms=duration_ms)
        raise
    duration_ms = int((time.perf_counter() - started) * 1000)
    response.headers["X-Request-ID"] = request_id
    log_request(method=request.method, path=request.url.path, status_code=response.status_code, duration_ms=duration_ms)
    return response


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
    if settings.is_production:
        response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
    return response


# Native agent streaming must win for the canonical /messages/stream route.
# The legacy conversations router still exposes the old implementation as a fallback.
app.include_router(agent_stream.router, prefix="/api/v1")
app.include_router(conversations.router, prefix="/api/v1")
app.include_router(system.router, prefix="/api/v1")
app.include_router(auth.router, prefix="/api/v1")
app.include_router(rag.router, prefix="/api/v1")
app.include_router(payments.router, prefix="/api/v1")
