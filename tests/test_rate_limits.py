"""Rate limits must actually be attached to the endpoints that need them.

This file exists because of a real gap. app/core/rate_limit.py configures
``default_limits``, which reads as though every endpoint is covered. It is not:
those defaults only apply through SlowAPIMiddleware, and that middleware never
fires on this FastAPI version - it resolves the handler by walking ``app.routes``,
which now holds nested ``_IncludedRouter`` objects instead of endpoints, so
``Limiter._check_request_limit`` is never reached. Measured before the fix, 200
consecutive posts to the unauthenticated payment webhook produced zero 429s.

Protection therefore comes from explicit decorators, and these tests fail if one
is ever dropped.

Note the ordering: a ``@limiter.limit`` decorator wraps the endpoint function,
which FastAPI calls only after dependencies have resolved. An anonymous flood of
an authenticated route is still rejected with 401 before the limiter sees it, so
these tests authenticate first.
"""

from __future__ import annotations

import pytest

from app.core.config import settings
from app.core.rate_limit import limiter
from tests.conftest import client


@pytest.fixture(autouse=True)
def reset_limiter():
    """Each test needs a clean window; limiter storage is process-wide."""
    limiter.reset()
    yield
    limiter.reset()


@pytest.fixture
def auth_headers():
    email = "rate-limit-probe@example.com"
    password = "Str0ng!Passw0rd"
    client.post("/api/v1/auth/register", json={"email": email, "password": password})
    response = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _statuses(call, count):
    seen: dict[int, int] = {}
    for _ in range(count):
        code = call().status_code
        seen[code] = seen.get(code, 0) + 1
    return seen


def _budget(value: str) -> int:
    return int(value.split("/")[0])


def test_payment_webhook_is_rate_limited():
    """Public and unauthenticated, so the limiter is the only thing in the way."""
    budget = _budget(settings.rate_limit_webhook)
    seen = _statuses(
        lambda: client.post("/api/v1/payments/notification", json={"order_id": "x"}),
        budget + 10,
    )
    assert seen.get(429, 0) >= 1, seen
    assert sum(count for code, count in seen.items() if code != 429) <= budget


def test_conversation_creation_is_rate_limited(auth_headers):
    """Unlimited creation lets a single account fill the database."""
    budget = _budget(settings.rate_limit_default)
    seen = _statuses(
        lambda: client.post("/api/v1/conversations", json={"title": "x"}, headers=auth_headers),
        budget + 10,
    )
    assert seen.get(429, 0) >= 1, seen


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("delete", "/api/v1/integrations/github"),
        ("delete", "/api/v1/rag/documents/1"),
        ("get", "/api/v1/rag/usage"),
        ("delete", "/api/v1/conversations/1"),
    ],
)
def test_repeatable_endpoints_start_returning_429(auth_headers, method, path):
    budget = _budget(settings.rate_limit_default)
    call = getattr(client, method)
    seen = _statuses(lambda: call(path, headers=auth_headers), budget + 10)
    assert seen.get(429, 0) >= 1, f"{method.upper()} {path} is unlimited: {seen}"


#: Endpoints whose first successful call changes state - logging out revokes the
#: token, deleting the account removes it - so they cannot be driven to 429 in a
#: loop. Their decorator is asserted structurally instead.
STATEFUL_ENDPOINTS = [
    "app.api.v1.auth.logout",
    "app.api.v1.auth.delete_account",
    "app.api.v1.conversations.rename_conversation",
]


@pytest.mark.parametrize("endpoint", STATEFUL_ENDPOINTS)
def test_stateful_endpoints_have_a_registered_limit(endpoint):
    assert endpoint in limiter._route_limits, f"{endpoint} lost its rate limit"


def test_every_mutating_endpoint_is_registered():
    """A new POST/PATCH/DELETE without a limit should fail review here."""
    import app.main  # noqa: F401  (ensures the routers are attached)

    expected = {
        "app.api.v1.agent_stream.stream_native_message",
        "app.api.v1.auth.change_password",
        "app.api.v1.auth.confirm_password_reset",
        "app.api.v1.auth.delete_account",
        "app.api.v1.auth.login",
        "app.api.v1.auth.logout",
        "app.api.v1.auth.refresh",
        "app.api.v1.auth.register",
        "app.api.v1.auth.request_password_reset",
        "app.api.v1.auth.resend_verification",
        "app.api.v1.auth.verify_email",
        "app.api.v1.conversations.create_new_conversation",
        "app.api.v1.conversations.remove_conversation",
        "app.api.v1.conversations.rename_conversation",
        "app.api.v1.conversations.send_message",
        "app.api.v1.integrations.connect_provider",
        "app.api.v1.integrations.disconnect_provider",
        "app.api.v1.payments.create_payment",
        "app.api.v1.payments.payment_notification",
        "app.api.v1.payments.refund_payment",
        "app.api.v1.rag.create_document",
        "app.api.v1.rag.delete_one_document",
        "app.api.v1.rag.reindex_one_document",
        "app.api.v1.rag.upload_document",
    }
    missing = expected - set(limiter._route_limits)
    assert missing == set(), f"endpoints lost their rate limit: {sorted(missing)}"


def test_health_probe_is_not_rate_limited():
    """An orchestrator polling readiness must never be throttled."""
    seen = _statuses(lambda: client.get("/api/v1/health"), 300)
    assert 429 not in seen, seen
