"""Login must not reveal whether an email address has an account.

Argon2 is deliberately expensive - about 90 ms on this hardware. The login
handler used to short-circuit it when no user matched:

    password_ok = user is not None and verify_password(...)

so an unregistered address answered in 9 ms and a registered one in 114 ms.
That is a 12x gap: one request, no statistics needed, and an attacker can
enumerate which addresses are customers. Under UU PDP that is personal data
leaking, and it makes targeted credential stuffing much cheaper.

The fix runs a verification against a throwaway hash on the not-found branch so
both paths pay the same cost.
"""

from __future__ import annotations

import statistics
import time

import pytest

from app.core.config import settings
from app.core.rate_limit import limiter
from app.core.security import get_password_hash, verify_password, verify_password_dummy
from tests.conftest import client

REGISTERED = "timing-known@example.com"
UNKNOWN = "timing-unknown@example.com"
PASSWORD = "Str0ng!Passw0rd"
WRONG = "WrongPassword!12345"


def test_dummy_verification_always_fails():
    assert verify_password_dummy(PASSWORD) is False
    assert verify_password_dummy("") is False


def test_dummy_verification_costs_about_the_same_as_a_real_one():
    """If the dummy were cheap it would not close the gap."""
    stored = get_password_hash(PASSWORD)

    def median(call, n=5):
        samples = []
        for _ in range(n):
            started = time.perf_counter()
            call()
            samples.append(time.perf_counter() - started)
        return statistics.median(samples)

    real = median(lambda: verify_password(WRONG, stored))
    dummy = median(lambda: verify_password_dummy(WRONG))

    ratio = max(real, dummy) / max(min(real, dummy), 1e-9)
    assert ratio < 2.0, f"dummy verification is {ratio:.1f}x off a real one"


@pytest.fixture
def unlimited(monkeypatch):
    """Repeated failures would otherwise trip two separate defences.

    The auth limiter allows 10/minute, and the per-email lockout fires after 8
    failed attempts and answers 429 without hashing anything - which is exactly
    the fast path this test is trying to measure the absence of.
    """
    limiter.reset()
    limiter.enabled = False
    monkeypatch.setattr(settings, "login_max_failed_attempts", 10_000)
    try:
        yield
    finally:
        limiter.enabled = True
        limiter.reset()


@pytest.fixture
def registered_account(unlimited):
    client.post("/api/v1/auth/register", json={"email": REGISTERED, "password": PASSWORD})
    return REGISTERED


def _median_login_ms(email: str, samples: int = 9) -> float:
    timings = []
    for _ in range(samples):
        started = time.perf_counter()
        response = client.post("/api/v1/auth/login", json={"email": email, "password": WRONG})
        timings.append((time.perf_counter() - started) * 1000)
        # A 429 would measure the rate limiter rather than the hash.
        assert response.status_code != 429, "rate limited; the measurement is meaningless"
    return statistics.median(timings)


def test_login_timing_does_not_reveal_whether_an_account_exists(registered_account):
    # Warm the lazily built dummy hash so the first miss is not an outlier.
    client.post("/api/v1/auth/login", json={"email": "warmup@example.com", "password": WRONG})

    known = _median_login_ms(registered_account)
    unknown = _median_login_ms(UNKNOWN)

    ratio = max(known, unknown) / max(min(known, unknown), 1e-9)
    assert ratio < 2.0, (
        f"login leaks account existence by timing: known={known:.1f}ms "
        f"unknown={unknown:.1f}ms ({ratio:.1f}x)"
    )


def test_login_response_is_identical_either_way(registered_account):
    known = client.post("/api/v1/auth/login", json={"email": registered_account, "password": WRONG})
    unknown = client.post("/api/v1/auth/login", json={"email": UNKNOWN, "password": WRONG})

    assert known.status_code == unknown.status_code
    assert known.json() == unknown.json()
