"""Request-scoped resolution of third-party credentials for tool execution.

Before this module existed, every tool read its token from `os.environ`, which
meant *every* user's tool call authenticated as the operator. That is a tenant
isolation failure, not a configuration detail.

Tools now call `resolve_credential(provider)`, which reads a `ContextVar` bound
to the user driving the current request. `ContextVar` is the right primitive
here because `asyncio.to_thread` (used by the tool executor for sync handlers)
copies the calling context into the worker thread, so the binding survives the
hop without threading an argument through ~50 handler signatures.

Outside production, `ALLOW_ENV_TOOL_CREDENTIALS=true` restores the old
environment lookup for local development. Production refuses that flag at boot.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar, Token
from dataclasses import dataclass
from typing import Protocol

from app.core.config import settings
from app.tools.errors import ToolProviderError

#: provider -> legacy environment variable, used only in development.
ENV_FALLBACK_VARS: dict[str, str] = {
    "github": "GITHUB_TOKEN",
    "vercel": "VERCEL_TOKEN",
    "railway": "RAILWAY_TOKEN",
    "cloudflare": "CLOUDFLARE_API_TOKEN",
    "supabase": "SUPABASE_ACCESS_TOKEN",
}


class SecretLookup(Protocol):
    def __call__(self, provider: str) -> str: ...


@dataclass(frozen=True)
class CredentialContext:
    """Identifies whose credentials the current tool call may use."""

    user_id: int
    lookup: SecretLookup


_context: ContextVar[CredentialContext | None] = ContextVar("tool_credentials", default=None)


def current_context() -> CredentialContext | None:
    return _context.get()


def bind(context: CredentialContext) -> Token:
    return _context.set(context)


def unbind(token: Token) -> None:
    _context.reset(token)


@contextmanager
def credential_scope(context: CredentialContext) -> Iterator[CredentialContext]:
    token = bind(context)
    try:
        yield context
    finally:
        unbind(token)


@contextmanager
def user_credential_scope(user_id: int) -> Iterator[CredentialContext]:
    """Bind the given user's stored credentials for the duration of the block.

    Each lookup opens its own short-lived session. Tool handlers may run in a
    worker thread (`asyncio.to_thread`), and SQLAlchemy sessions are not safe
    to share across threads, so reusing the request session here would be a
    latent concurrency bug.
    """
    from app.core.database import SessionLocal
    from app.services.credential_service import get_secret

    def lookup(provider: str) -> str:
        session = SessionLocal()
        try:
            return get_secret(session, user_id=user_id, provider=provider)
        finally:
            session.close()

    with credential_scope(CredentialContext(user_id=user_id, lookup=lookup)) as ctx:
        yield ctx


def _env_fallback(provider: str) -> str | None:
    if settings.is_production or not settings.allow_env_tool_credentials:
        return None
    var = ENV_FALLBACK_VARS.get(provider)
    if not var:
        return None
    return os.getenv(var, "").strip() or None


def resolve_credential(provider: str) -> str:
    """Return the current user's secret for `provider`.

    Raises `ToolProviderError` when no user context is bound or the user has
    not connected that provider. It never falls back to a shared operator
    token in production.
    """
    provider = provider.strip().lower()
    context = _context.get()

    if context is not None:
        try:
            secret = context.lookup(provider)
        except Exception as exc:
            raise ToolProviderError(str(exc)) from exc
        if secret:
            return secret

    fallback = _env_fallback(provider)
    if fallback:
        return fallback

    if context is None:
        raise ToolProviderError(
            f"No user credential context is bound; {provider} tools cannot run without one"
        )
    raise ToolProviderError(f"No {provider} credential is connected for this account")
