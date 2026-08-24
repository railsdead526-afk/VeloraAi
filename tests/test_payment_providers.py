"""The payment provider abstraction.

The point of this suite is to prove the claim the abstraction makes: that the
billing flow works with a gateway that is not Midtrans. It does that by
registering a provider built entirely for the test and driving the real API
endpoints through it.
"""

from collections.abc import Mapping
from typing import Any

import pytest

from app.core.config import settings
from app.services.payments import (
    CheckoutSession,
    NotificationEnvelope,
    PaymentOutcome,
    PaymentProvider,
    PaymentProviderError,
    RefundResult,
    TransactionStatus,
    available_providers,
    get_provider,
    register_provider,
)
from app.services.payments.midtrans import MidtransProvider, classify
from tests.conftest import client

STRONG_PASSWORD = "Str0ng!Passw0rd"


class FakeGateway:
    """A provider with no relationship to Midtrans whatsoever."""

    name = "fakepay"
    supports_refund = True

    #: Test hooks.
    next_outcome = PaymentOutcome.PAID
    next_raw_status = "captured"
    signature_valid = True
    fail_checkout = False

    def client_config(self) -> dict[str, Any]:
        return {"provider": self.name, "currency": "IDR", "hosted": True}

    def create_checkout(
        self, *, order_id, amount, currency, customer_email, item_name
    ) -> CheckoutSession:
        if type(self).fail_checkout:
            raise PaymentProviderError("gateway unavailable")
        return CheckoutSession(
            order_id=order_id,
            token=None,  # deliberately tokenless: not every gateway has a widget
            redirect_url=f"https://fakepay.test/checkout/{order_id}",
            amount=amount,
            currency=currency,
        )

    def parse_notification(self, payload: Mapping[str, Any]) -> NotificationEnvelope:
        order_id = str(payload.get("reference", "")).strip()
        if not order_id:
            raise PaymentProviderError("reference is required")
        return NotificationEnvelope(
            order_id=order_id,
            gross_amount=str(payload.get("total", "")) or None,
            signature_valid=type(self).signature_valid,
        )

    def fetch_transaction(self, order_id: str) -> TransactionStatus:
        return TransactionStatus(
            order_id=order_id,
            outcome=type(self).next_outcome,
            raw_status=type(self).next_raw_status,
            gross_amount="19900",
            transaction_id=f"fake-{order_id}",
            payment_type="fakewallet",
        )

    def refund(self, *, order_id, amount, reason) -> RefundResult:
        return RefundResult(
            outcome=PaymentOutcome.REFUNDED,
            raw_status="reversed",
            amount=amount,
            reference=f"refund-{order_id}",
        )


@pytest.fixture
def fake_provider(monkeypatch):
    register_provider("fakepay", FakeGateway)
    monkeypatch.setattr(settings, "payment_provider", "fakepay")
    monkeypatch.setattr(settings, "pro_price_idr", 19900)
    FakeGateway.next_outcome = PaymentOutcome.PAID
    FakeGateway.next_raw_status = "captured"
    FakeGateway.signature_valid = True
    FakeGateway.fail_checkout = False
    return FakeGateway


def _headers(email: str) -> dict[str, str]:
    client.post("/api/v1/auth/register", json={"email": email, "password": STRONG_PASSWORD})
    token = client.post(
        "/api/v1/auth/login", json={"email": email, "password": STRONG_PASSWORD}
    ).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


# --------------------------------------------------------------------------- #
# Contract
# --------------------------------------------------------------------------- #


def test_midtrans_satisfies_the_provider_protocol():
    assert isinstance(MidtransProvider(), PaymentProvider)


def test_fake_gateway_satisfies_the_provider_protocol():
    assert isinstance(FakeGateway(), PaymentProvider)


def test_registry_resolves_the_configured_provider(monkeypatch):
    monkeypatch.setattr(settings, "payment_provider", "midtrans")
    assert get_provider().name == "midtrans"
    assert "midtrans" in available_providers()


def test_unknown_provider_fails_loudly(monkeypatch):
    monkeypatch.setattr(settings, "payment_provider", "nope")
    with pytest.raises(PaymentProviderError, match="Unknown payment provider"):
        get_provider()


# --------------------------------------------------------------------------- #
# Midtrans status mapping
#
# This vocabulary used to live in billing_service, where it silently defined
# the meaning of "paid" for the whole system.
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("settlement", PaymentOutcome.PAID),
        ("capture", PaymentOutcome.PAID),
        ("SETTLEMENT", PaymentOutcome.PAID),
        ("pending", PaymentOutcome.PENDING),
        ("authorize", PaymentOutcome.PENDING),
        ("deny", PaymentOutcome.FAILED),
        ("cancel", PaymentOutcome.FAILED),
        ("expire", PaymentOutcome.FAILED),
        ("failure", PaymentOutcome.FAILED),
        ("refund", PaymentOutcome.REFUNDED),
        ("chargeback", PaymentOutcome.REFUNDED),
    ],
)
def test_midtrans_status_mapping(raw, expected):
    assert classify(raw) == expected


def test_authorize_is_not_treated_as_paid():
    """Funds are only reserved, not captured. Granting a plan here is a loss."""
    assert classify("authorize") is PaymentOutcome.PENDING


def test_unrecognised_status_is_unknown_not_failed():
    """A status we have never seen must not revoke a paying customer's plan."""
    assert classify("some_future_status") is PaymentOutcome.UNKNOWN
    assert classify("") is PaymentOutcome.UNKNOWN


# --------------------------------------------------------------------------- #
# The API works with a non-Midtrans gateway
# --------------------------------------------------------------------------- #


def test_config_is_shaped_by_the_active_provider(fake_provider):
    """The response model whitelists keys.

    A provider cannot smuggle extra fields to the browser, so a future slip
    like a credential landing in `client_config` is dropped instead of leaked.
    The fake provider returns `{"provider": "fakepay", "currency": "IDR",
    "hosted": True}`; only the schema-approved keys survive.
    """
    headers = _headers("cfg-fake@example.com")
    body = client.get("/api/v1/payments/config", headers=headers).json()
    assert body == {
        "provider": "fakepay",
        "enabled": True,
        "is_production": None,
        "pro_price_idr": None,
        "max_price_idr": None,
        "reason": None,
    }


def test_checkout_runs_through_the_active_provider(fake_provider):
    headers = _headers("checkout-fake@example.com")
    response = client.post("/api/v1/payments/create", headers=headers, json={"plan": "pro"})

    assert response.status_code == 200
    body = response.json()
    assert body["redirect_url"].startswith("https://fakepay.test/checkout/")
    assert body["amount"] == 19900
    # A tokenless gateway must not break the response contract.
    assert body["checkout_token"] is None


def test_payment_is_recorded_against_the_active_provider(fake_provider, db):
    from app.models.billing import Payment

    headers = _headers("record-fake@example.com")
    order_id = client.post("/api/v1/payments/create", headers=headers, json={"plan": "pro"}).json()[
        "order_id"
    ]

    payment = db.query(Payment).filter(Payment.provider_order_id == order_id).one()
    assert payment.provider == "fakepay"


def test_gateway_failure_surfaces_as_bad_gateway(fake_provider):
    FakeGateway.fail_checkout = True
    headers = _headers("fail-fake@example.com")
    response = client.post("/api/v1/payments/create", headers=headers, json={"plan": "pro"})
    assert response.status_code == 502


def test_webhook_grants_the_plan_through_a_foreign_gateway(fake_provider, db):
    from app.models.user import User

    headers = _headers("webhook-fake@example.com")
    order_id = client.post("/api/v1/payments/create", headers=headers, json={"plan": "pro"}).json()[
        "order_id"
    ]

    response = client.post(
        "/api/v1/payments/notification",
        json={"reference": order_id, "total": "19900"},
    )
    assert response.status_code == 200

    db.expire_all()
    user = db.query(User).filter(User.email == "webhook-fake@example.com").one()
    assert user.role == "pro"


def test_webhook_rejects_an_unsigned_notification(fake_provider):
    headers = _headers("unsigned-fake@example.com")
    order_id = client.post("/api/v1/payments/create", headers=headers, json={"plan": "pro"}).json()[
        "order_id"
    ]

    FakeGateway.signature_valid = False
    response = client.post(
        "/api/v1/payments/notification",
        json={"reference": order_id, "total": "19900"},
    )
    assert response.status_code == 403


def test_webhook_rejects_a_mismatched_amount(fake_provider):
    headers = _headers("amount-fake@example.com")
    order_id = client.post("/api/v1/payments/create", headers=headers, json={"plan": "pro"}).json()[
        "order_id"
    ]

    response = client.post(
        "/api/v1/payments/notification",
        json={"reference": order_id, "total": "1"},
    )
    assert response.status_code == 400


def test_unknown_outcome_does_not_revoke_entitlement(fake_provider, db):
    """The dangerous case: a status the adapter does not recognise."""
    from app.models.user import User

    headers = _headers("unknown-fake@example.com")
    order_id = client.post("/api/v1/payments/create", headers=headers, json={"plan": "pro"}).json()[
        "order_id"
    ]

    client.post("/api/v1/payments/notification", json={"reference": order_id, "total": "19900"})

    FakeGateway.next_outcome = PaymentOutcome.UNKNOWN
    FakeGateway.next_raw_status = "under_review"
    client.post("/api/v1/payments/notification", json={"reference": order_id, "total": "19900"})

    db.expire_all()
    user = db.query(User).filter(User.email == "unknown-fake@example.com").one()
    assert user.role == "pro", "an unrecognised status must not cost a paying customer their plan"


def test_provider_without_refund_support_is_refused(monkeypatch, db):
    """Google Play and the app stores settle refunds out of band."""

    class NoRefundGateway(FakeGateway):
        name = "norefund"
        supports_refund = False

    register_provider("norefund", NoRefundGateway)
    monkeypatch.setattr(settings, "payment_provider", "norefund")
    monkeypatch.setattr(settings, "pro_price_idr", 19900)

    from app.models.billing import Payment
    from app.models.user import User

    headers = _headers("norefund@example.com")
    order_id = client.post("/api/v1/payments/create", headers=headers, json={"plan": "pro"}).json()[
        "order_id"
    ]
    client.post("/api/v1/payments/notification", json={"reference": order_id, "total": "19900"})

    payment = db.query(Payment).filter(Payment.provider_order_id == order_id).one()
    admin = db.query(User).filter(User.email == "norefund@example.com").one()
    admin.role = "admin"
    db.commit()

    response = client.post(f"/api/v1/payments/{payment.id}/refund", headers=headers)
    assert response.status_code == 400
    assert "outside VeloraAi" in response.json()["detail"]


# --------------------------------------------------------------------------- #
# Running with payments switched off
#
# A deployment that is not selling yet must be a supported state, not a
# half-configured one. Blank credentials plus zero prices is how a system ends
# up granting paid plans for free.
# --------------------------------------------------------------------------- #


@pytest.fixture
def payments_off(monkeypatch):
    monkeypatch.setattr(settings, "payment_provider", "disabled")
    return settings


def test_disabled_provider_satisfies_the_protocol():
    from app.services.payments.disabled import DisabledProvider

    assert isinstance(DisabledProvider(), PaymentProvider)


def test_payments_enabled_reflects_configuration(monkeypatch):
    from app.services.payments import payments_enabled

    monkeypatch.setattr(settings, "payment_provider", "disabled")
    assert payments_enabled() is False
    monkeypatch.setattr(settings, "payment_provider", "midtrans")
    assert payments_enabled() is True


def test_config_reports_disabled_instead_of_erroring(payments_off):
    """The UI needs an honest 'unavailable' state, not a 500."""
    headers = _headers("cfg-off@example.com")
    body = client.get("/api/v1/payments/config", headers=headers).json()
    assert body["enabled"] is False
    assert "not enabled" in body["reason"]


def test_config_disabled_shape_never_carries_prices(payments_off):
    """A disabled deployment must not imply a purchasable plan to the client."""
    headers = _headers("cfg-shape@example.com")
    body = client.get("/api/v1/payments/config", headers=headers).json()
    assert body["provider"] == "disabled"
    assert body["pro_price_idr"] is None
    assert body["max_price_idr"] is None
    assert body["is_production"] is None


def test_config_enabled_shape_carries_prices(monkeypatch):
    monkeypatch.setattr(settings, "payment_provider", "midtrans")
    monkeypatch.setattr(settings, "pro_price_idr", 19900)
    monkeypatch.setattr(settings, "max_price_idr", 49900)
    headers = _headers("cfg-on@example.com")
    body = client.get("/api/v1/payments/config", headers=headers).json()
    assert body["provider"] == "midtrans"
    assert body["enabled"] is True
    assert body["pro_price_idr"] == 19900
    assert body["max_price_idr"] == 49900
    assert body["reason"] is None


def test_checkout_is_refused_when_payments_are_off(payments_off):
    monkeypatch_price = settings.pro_price_idr
    settings.pro_price_idr = 19900
    try:
        headers = _headers("checkout-off@example.com")
        response = client.post("/api/v1/payments/create", headers=headers, json={"plan": "pro"})
        assert response.status_code == 502
        assert "not enabled" in response.json()["detail"]
    finally:
        settings.pro_price_idr = monkeypatch_price


def test_webhook_is_refused_when_payments_are_off(payments_off):
    response = client.post("/api/v1/payments/notification", json={"reference": "x", "total": "1"})
    assert response.status_code == 400


def test_production_does_not_demand_a_gateway_when_payments_are_off():
    """Otherwise 'we are not selling yet' would block the deploy entirely."""
    from tests.test_production_config_gates import _production_settings

    config = _production_settings()
    config.payment_provider = "disabled"
    config.midtrans_server_key = ""
    config.midtrans_client_key = ""
    config.pro_price_idr = 0
    config.max_price_idr = 0
    config.validate()


def test_production_still_demands_a_gateway_when_payments_are_on():
    from tests.test_production_config_gates import _production_settings

    config = _production_settings()
    config.payment_provider = "midtrans"
    config.midtrans_server_key = ""
    with pytest.raises(RuntimeError, match="Midtrans credentials"):
        config.validate()
