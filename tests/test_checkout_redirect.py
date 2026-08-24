"""The checkout redirect URL must never leave the provider unvalidated.

`CheckoutSession.redirect_url` is returned to the browser, which assigns it to
`window.location`. A `javascript:` or `data:` URL there executes in our own
origin, and access tokens live in localStorage, so the consequence is session
theft rather than a broken link.

The value originates in the gateway's response and was previously passed
through untouched. The frontend validates it too (web/lib/navigation.ts); this
is the layer at the source.
"""

from __future__ import annotations

import pytest

from app.services.payments.base import PaymentProviderError, validate_redirect_url

HOSTILE = [
    "javascript:alert(1)",
    "JavaScript:alert(1)",
    "  javascript:alert(1)  ",
    "data:text/html,<script>alert(1)</script>",
    "vbscript:msgbox(1)",
    "file:///etc/passwd",
    "http://checkout.example.com/pay",
    "//checkout.example.com/pay",
    "/relative/path",
    "checkout.example.com",
    "https://",
    "",
    "   ",
]

ACCEPTED = [
    "https://app.midtrans.com/snap/v3/redirection/abc123",
    "https://app.sandbox.midtrans.com/snap/v2/vtweb/xyz",
    "https://checkout.example.com/pay?order=1#top",
]


@pytest.mark.parametrize("value", HOSTILE)
def test_hostile_redirect_urls_are_rejected(value):
    with pytest.raises(PaymentProviderError):
        validate_redirect_url(value)


@pytest.mark.parametrize("value", ACCEPTED)
def test_hosted_checkout_pages_are_accepted(value):
    assert validate_redirect_url(value) == value


def test_surrounding_whitespace_is_trimmed():
    assert validate_redirect_url("  https://pay.example.com/x  ") == "https://pay.example.com/x"


def test_midtrans_adapter_refuses_a_hostile_redirect(monkeypatch):
    """End to end through the adapter, not just the helper."""
    from app.services.payments import midtrans as midtrans_module

    class FakeService:
        def create_snap_transaction(self, **_kwargs):
            return {"token": "tok", "redirect_url": "javascript:alert(1)"}

    provider = midtrans_module.MidtransProvider()
    monkeypatch.setattr(provider, "_service", lambda: FakeService())

    with pytest.raises(PaymentProviderError, match="unsupported redirect URL"):
        provider.create_checkout(
            order_id="velora-1-1",
            amount=100_000,
            currency="IDR",
            customer_email="a@example.com",
            item_name="Pro",
        )


def test_midtrans_adapter_passes_a_valid_redirect_through(monkeypatch):
    from app.services.payments import midtrans as midtrans_module

    class FakeService:
        def create_snap_transaction(self, **_kwargs):
            return {"token": "tok", "redirect_url": "https://app.midtrans.com/snap/v3/x"}

    provider = midtrans_module.MidtransProvider()
    monkeypatch.setattr(provider, "_service", lambda: FakeService())

    session = provider.create_checkout(
        order_id="velora-1-1",
        amount=100_000,
        currency="IDR",
        customer_email="a@example.com",
        item_name="Pro",
    )
    assert session.redirect_url == "https://app.midtrans.com/snap/v3/x"


def test_a_missing_redirect_url_is_an_error():
    with pytest.raises(PaymentProviderError, match="no redirect URL"):
        validate_redirect_url("")
