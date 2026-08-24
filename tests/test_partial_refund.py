"""Partial refunds.

The endpoint previously always returned everything outstanding. Supporting a
partial amount is not just a new parameter: two pieces of existing logic were
wrong for anything less than a full refund.

* The duplicate guard keyed off the provider's refund *status*. The first
  partial refund set that status, so every later call was rejected as
  "already_refunded" while money was still outstanding.
* Any successful refund cancelled the subscription. A pro-rata adjustment would
  therefore have revoked a plan the customer is still paying for.

Both are now driven by the amount refunded so far.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.models.billing import Payment, Subscription
from app.models.user import User
from app.services.payments.base import PaymentOutcome, RefundResult
from tests.conftest import TestingSessionLocal, client

PASSWORD = "Str0ng!Passw0rd"
AMOUNT = 100_000


def _admin_headers(email: str) -> dict:
    client.post("/api/v1/auth/register", json={"email": email, "password": PASSWORD})
    session = TestingSessionLocal()
    try:
        user = session.query(User).filter(User.email == email).one()
        user.role = "admin"
        session.commit()
    finally:
        session.close()
    response = client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _plain_headers(email: str) -> dict:
    client.post("/api/v1/auth/register", json={"email": email, "password": PASSWORD})
    response = client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _settled_payment(email: str, *, with_subscription: bool = True) -> int:
    session = TestingSessionLocal()
    try:
        user = session.query(User).filter(User.email == email).one()
        subscription = None
        if with_subscription:
            now = datetime.now(UTC)
            subscription = Subscription(
                user_id=user.id,
                plan="pro",
                provider="midtrans",
                status="active",
                current_period_start=now,
                current_period_end=now + timedelta(days=30),
                grace_until=now + timedelta(days=33),
            )
            session.add(subscription)
            session.flush()
        payment = Payment(
            user_id=user.id,
            provider="midtrans",
            provider_order_id=f"order-{email}",
            amount=AMOUNT,
            tax_amount=0,
            currency="IDR",
            plan="pro",
            status="settlement",
            refund_amount=0,
            subscription_id=subscription.id if subscription else None,
        )
        session.add(payment)
        session.commit()
        return payment.id
    finally:
        session.close()


@pytest.fixture
def refunding_provider(monkeypatch):
    """Stands in for Midtrans; records what it was asked to refund."""
    calls: list[dict] = []

    class Provider:
        name = "midtrans"
        supports_refund = True

        def refund(self, *, order_id, amount, reason):
            calls.append({"order_id": order_id, "amount": amount, "reason": reason})
            return RefundResult(
                outcome=PaymentOutcome.REFUNDED,
                raw_status="200",
                amount=amount,
                reference="rf-1",
            )

    monkeypatch.setattr("app.api.v1.payments.get_provider", lambda _name=None: Provider())
    return calls


def _payment_row(payment_id: int) -> Payment:
    session = TestingSessionLocal()
    try:
        return session.query(Payment).filter(Payment.id == payment_id).one()
    finally:
        session.close()


def test_refund_requires_an_admin(refunding_provider):
    """The endpoint moves money; the role gate is not optional."""
    headers = _plain_headers("refund-plain@example.com")
    payment_id = _settled_payment("refund-plain@example.com")

    response = client.post(f"/api/v1/payments/{payment_id}/refund", headers=headers, json={})

    assert response.status_code == 403
    assert refunding_provider == [], "no refund may be attempted for a non-admin"


def test_omitting_the_amount_refunds_everything_outstanding(refunding_provider):
    headers = _admin_headers("refund-full@example.com")
    payment_id = _settled_payment("refund-full@example.com")

    response = client.post(f"/api/v1/payments/{payment_id}/refund", headers=headers, json={})

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["refund_amount"] == AMOUNT
    assert body["remaining"] == 0
    assert body["fully_refunded"] is True
    assert refunding_provider[0]["amount"] == AMOUNT


def test_a_partial_refund_leaves_the_rest_outstanding(refunding_provider):
    headers = _admin_headers("refund-partial@example.com")
    payment_id = _settled_payment("refund-partial@example.com")

    response = client.post(
        f"/api/v1/payments/{payment_id}/refund", headers=headers, json={"amount": 30_000}
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["refund_amount"] == 30_000
    assert body["refunded_total"] == 30_000
    assert body["remaining"] == 70_000
    assert body["fully_refunded"] is False
    assert refunding_provider[0]["amount"] == 30_000


def test_a_partial_refund_does_not_cancel_the_subscription(refunding_provider):
    """A pro-rata adjustment must not revoke a plan still being paid for."""
    headers = _admin_headers("refund-keeps-plan@example.com")
    payment_id = _settled_payment("refund-keeps-plan@example.com")

    client.post(f"/api/v1/payments/{payment_id}/refund", headers=headers, json={"amount": 25_000})

    session = TestingSessionLocal()
    try:
        payment = session.query(Payment).filter(Payment.id == payment_id).one()
        assert payment.status == "partially_refunded"
        assert payment.subscription.status == "active"
        user = session.query(User).filter(User.id == payment.user_id).one()
        assert user.role == "admin"  # unchanged by the partial refund
    finally:
        session.close()


def test_partial_refunds_accumulate_until_fully_refunded(refunding_provider):
    """The old duplicate guard rejected the second call outright."""
    headers = _admin_headers("refund-accumulate@example.com")
    payment_id = _settled_payment("refund-accumulate@example.com")
    url = f"/api/v1/payments/{payment_id}/refund"

    first = client.post(url, headers=headers, json={"amount": 40_000})
    assert first.status_code == 200, first.text
    assert first.json()["refunded_total"] == 40_000

    second = client.post(url, headers=headers, json={"amount": 60_000})
    assert second.status_code == 200, second.text
    body = second.json()
    assert body["refunded_total"] == AMOUNT
    assert body["remaining"] == 0
    assert body["fully_refunded"] is True

    session = TestingSessionLocal()
    try:
        payment = session.query(Payment).filter(Payment.id == payment_id).one()
        assert payment.status == "refunded"
        assert payment.refunded_at is not None
        assert payment.subscription.status == "canceled"
    finally:
        session.close()


def test_refunding_more_than_outstanding_is_rejected(refunding_provider):
    headers = _admin_headers("refund-toomuch@example.com")
    payment_id = _settled_payment("refund-toomuch@example.com")

    response = client.post(
        f"/api/v1/payments/{payment_id}/refund", headers=headers, json={"amount": AMOUNT + 1}
    )

    assert response.status_code == 400
    assert "outstanding" in response.json()["detail"]
    assert refunding_provider == [], "nothing may be sent to the provider"


def test_a_second_refund_cannot_exceed_the_remainder(refunding_provider):
    headers = _admin_headers("refund-remainder@example.com")
    payment_id = _settled_payment("refund-remainder@example.com")
    url = f"/api/v1/payments/{payment_id}/refund"

    client.post(url, headers=headers, json={"amount": 90_000})
    response = client.post(url, headers=headers, json={"amount": 20_000})

    assert response.status_code == 400
    assert _payment_row(payment_id).refund_amount == 90_000


def test_a_fully_refunded_payment_cannot_be_refunded_again(refunding_provider):
    headers = _admin_headers("refund-twice@example.com")
    payment_id = _settled_payment("refund-twice@example.com")
    url = f"/api/v1/payments/{payment_id}/refund"

    client.post(url, headers=headers, json={})
    response = client.post(url, headers=headers, json={})

    assert response.status_code == 409
    assert _payment_row(payment_id).refund_amount == AMOUNT


def test_zero_and_negative_amounts_are_rejected(refunding_provider):
    headers = _admin_headers("refund-zero@example.com")
    payment_id = _settled_payment("refund-zero@example.com")
    url = f"/api/v1/payments/{payment_id}/refund"

    for amount in (0, -1):
        response = client.post(url, headers=headers, json={"amount": amount})
        assert response.status_code == 422, amount
    assert refunding_provider == []


def test_a_pending_refund_records_nothing_as_returned(monkeypatch):
    """Only a settled refund may reduce the outstanding balance."""

    class PendingProvider:
        name = "midtrans"
        supports_refund = True

        def refund(self, *, order_id, amount, reason):
            return RefundResult(
                outcome=PaymentOutcome.PENDING,
                raw_status="pending",
                amount=0,
                reference="rf-2",
            )

    monkeypatch.setattr("app.api.v1.payments.get_provider", lambda _name=None: PendingProvider())

    headers = _admin_headers("refund-pending@example.com")
    payment_id = _settled_payment("refund-pending@example.com")

    response = client.post(
        f"/api/v1/payments/{payment_id}/refund", headers=headers, json={"amount": 10_000}
    )

    assert response.status_code == 200, response.text
    assert response.json()["refunded_total"] == 0
    payment = _payment_row(payment_id)
    assert payment.refund_amount == 0
    assert payment.status == "settlement"
