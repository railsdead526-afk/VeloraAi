from __future__ import annotations

import json
import logging
import time
from contextvars import ContextVar
from uuid import uuid4

request_id_var: ContextVar[str] = ContextVar("request_id", default="-")
logger = logging.getLogger("veloraai.request")


def new_request_id() -> str:
    return uuid4().hex


def set_request_id(request_id: str | None = None) -> str:
    value = request_id or new_request_id()
    request_id_var.set(value)
    return value


def get_request_id() -> str:
    return request_id_var.get()


def log_request(*, method: str, path: str, status_code: int, duration_ms: int) -> None:
    logger.info(
        json.dumps(
            {
                "event": "http_request",
                "request_id": get_request_id(),
                "method": method,
                "path": path,
                "status_code": status_code,
                "duration_ms": duration_ms,
            },
            separators=(",", ":"),
        )
    )
