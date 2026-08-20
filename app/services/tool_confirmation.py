from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from typing import Any

from app.core.config import settings

CONFIRMATION_TTL_SECONDS = 300


def _secret() -> bytes:
    value = settings.secret_key or "velora-ci-confirmation-secret"
    return value.encode("utf-8")


def _encode(payload: dict[str, Any]) -> str:
    raw = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    body = base64.urlsafe_b64encode(raw).rstrip(b"=")
    signature = hmac.new(_secret(), body, hashlib.sha256).digest()
    encoded_signature = base64.urlsafe_b64encode(signature).rstrip(b"=")
    return f"{body.decode()}.{encoded_signature.decode()}"


def _decode(token: str) -> dict[str, Any] | None:
    try:
        body, encoded_signature = token.split(".", 1)
        expected = hmac.new(_secret(), body.encode("ascii"), hashlib.sha256).digest()
        supplied = base64.urlsafe_b64decode(encoded_signature + "===")
        if not hmac.compare_digest(expected, supplied):
            return None
        payload = json.loads(base64.urlsafe_b64decode(body + "===").decode("utf-8"))
        if not isinstance(payload, dict):
            return None
        return payload
    except (ValueError, TypeError, UnicodeDecodeError, json.JSONDecodeError):
        return None


def argument_fingerprint(arguments: dict[str, Any]) -> str:
    raw = json.dumps(arguments, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def create_confirmation_token(
    *,
    user_id: int,
    conversation_id: int,
    tool_name: str,
    arguments: dict[str, Any],
) -> str:
    payload = {
        "sub": user_id,
        "conversation_id": conversation_id,
        "tool": tool_name,
        "args": argument_fingerprint(arguments),
        "exp": int(time.time()) + CONFIRMATION_TTL_SECONDS,
    }
    return _encode(payload)


def verify_confirmation_token(
    token: str | None,
    *,
    user_id: int,
    conversation_id: int,
    tool_name: str,
    arguments: dict[str, Any],
) -> bool:
    if not token:
        return False
    payload = _decode(token)
    if payload is None:
        return False
    if int(payload.get("exp", 0)) < int(time.time()):
        return False
    return (
        payload.get("sub") == user_id
        and payload.get("conversation_id") == conversation_id
        and payload.get("tool") == tool_name
        and payload.get("args") == argument_fingerprint(arguments)
    )
