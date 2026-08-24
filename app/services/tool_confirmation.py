from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
import time
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import delete, update
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.tool_confirmation import ToolConfirmation

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
        return payload if isinstance(payload, dict) else None
    except (ValueError, TypeError, UnicodeDecodeError, json.JSONDecodeError, binascii.Error):
        return None


def argument_fingerprint(arguments: dict[str, Any]) -> str:
    raw = json.dumps(arguments, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def create_confirmation_token(
    db: Session,
    *,
    user_id: int,
    conversation_id: int,
    tool_name: str,
    arguments: dict[str, Any],
) -> str:
    expires_at = int(time.time()) + CONFIRMATION_TTL_SECONDS
    payload = {
        "sub": user_id,
        "conversation_id": conversation_id,
        "tool": tool_name,
        "args": argument_fingerprint(arguments),
        "exp": expires_at,
    }
    token = _encode(payload)
    now = datetime.now(UTC)
    db.execute(delete(ToolConfirmation).where(ToolConfirmation.expires_at < now))
    db.add(
        ToolConfirmation(
            token_hash=_token_hash(token),
            user_id=user_id,
            conversation_id=conversation_id,
            tool_name=tool_name,
            arguments_hash=payload["args"],
            expires_at=datetime.fromtimestamp(expires_at, tz=UTC),
        )
    )
    db.commit()
    return token


def verify_confirmation_token(
    db: Session,
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
    try:
        expires_at = int(payload.get("exp", 0))
    except (TypeError, ValueError):
        return False
    if expires_at < int(time.time()):
        return False

    arguments_hash = argument_fingerprint(arguments)
    if (
        payload.get("sub") != user_id
        or payload.get("conversation_id") != conversation_id
        or payload.get("tool") != tool_name
        or payload.get("args") != arguments_hash
    ):
        return False

    now = datetime.now(UTC)
    result = db.execute(
        update(ToolConfirmation)
        .where(
            ToolConfirmation.token_hash == _token_hash(token),
            ToolConfirmation.user_id == user_id,
            ToolConfirmation.conversation_id == conversation_id,
            ToolConfirmation.tool_name == tool_name,
            ToolConfirmation.arguments_hash == arguments_hash,
            ToolConfirmation.used_at.is_(None),
            ToolConfirmation.expires_at >= now,
        )
        .values(used_at=now)
    )
    db.commit()
    return result.rowcount == 1
