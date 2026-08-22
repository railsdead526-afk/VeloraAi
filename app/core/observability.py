from __future__ import annotations

import json
import logging
import re
import sys
from contextvars import ContextVar
from uuid import uuid4

request_id_var: ContextVar[str] = ContextVar("request_id", default="-")
logger = logging.getLogger("veloraai.request")
_REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")

#: Anything matching these is never allowed into a log line.
_SECRET_PATTERNS = (
    re.compile(r"(?i)(bearer\s+)[A-Za-z0-9._\-]{12,}"),
    re.compile(r"(?i)\b(gh[pousr]_[A-Za-z0-9]{16,})\b"),
    re.compile(r"(?i)\b(sk-[A-Za-z0-9]{16,})\b"),
    re.compile(
        r"(?i)(\"?(?:api[_-]?key|secret|token|password|authorization)\"?\s*[:=]\s*\"?)([^\s\",}]{6,})"
    ),
)


def redact(text: str) -> str:
    """Strip credential-shaped substrings from a log payload."""
    for pattern in _SECRET_PATTERNS:
        text = pattern.sub(lambda m: m.group(1) + "***REDACTED***", text)
    return text


def new_request_id() -> str:
    return uuid4().hex


def set_request_id(request_id: str | None = None) -> str:
    candidate = request_id.strip() if request_id else ""
    value = candidate if _REQUEST_ID_RE.fullmatch(candidate) else new_request_id()
    request_id_var.set(value)
    return value


def get_request_id() -> str:
    return request_id_var.get()


class JsonFormatter(logging.Formatter):
    """One JSON object per line, with the request id attached and secrets removed."""

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "level": record.levelname,
            "logger": record.name,
            "request_id": get_request_id(),
            "message": record.getMessage(),
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        for key in ("event", "user_id", "duration_ms", "status_code", "path", "method"):
            value = getattr(record, key, None)
            if value is not None:
                payload[key] = value
        return redact(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))


def configure_logging(level: str = "INFO") -> None:
    """Install JSON logging on the root logger. Safe to call more than once."""
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())

    root = logging.getLogger()
    for existing in list(root.handlers):
        root.removeHandler(existing)
    root.addHandler(handler)
    root.setLevel(getattr(logging, level.upper(), logging.INFO))

    # Uvicorn duplicates access logs; the middleware already emits them.
    logging.getLogger("uvicorn.access").handlers = []
    logging.getLogger("uvicorn.access").propagate = False


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
