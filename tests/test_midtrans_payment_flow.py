from unittest.mock import patch

from app.models.billing import Payment, Subscription
from app.models.user import User
from tests.conftest import TestingSessionLocal, client


def register_login(email: str):
    password = "securepass123"
    assert client.post("/api/v1/auth/register", json={"email": email, "password": password}).status_code == 201
    login = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert login.status_code == 200
    token = login.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_midtrans_pending_failed_settlement_duplicate_webhook_flow(monkeypatch):
    headers = register_login("midtrans-flow@example.com")
    monkeypatch.setattr("app.api.v1.payments.settings.pro_price_idr", 19900)
    monkeypatch.setattr(
        "app.services.midtrans_service.MidtransService.create_snap_transaction",
        lambda self, **kwargs: {"token": "sandbox-token", "redirect_url": "https://sandbox.example/pay"},
    )

    created = client.post("/api/v1/payments/create", headers=headers, json={"plan": "pro"})
    assert created.status_code == 200
    order_id = created.json()["order_id"]

    def verified(status):
        return {
            "order_id": order_id,
            "gross_amount": "19900",
            "transaction_id": f"tx-{status}",
            "transaction_status": status,
            "payment_type": "gopay",
        }

    payload = {"order_id": order_id, "status_code": "201", "gross_amount": "19900", "signature_key": "valid"}
    with patch("app.api.v1.payments.MidtransService.verify_notification_signature", return_value=True), \
         patch("app.api.v1.payments.MidtransService.get_transaction_status", side_effect=[verified("pending"), verified("deny"), verified("settlement"), verified("settlement")]):
        pending = client.post("/api/v1/payments/notification", json=payload)
        failed = client.post("/api/v1/payments/notification", json=payload)
        settled = client.post("/api/v1/payments/notification", json=payload)
        duplicate = client.post("/api/v1/payments/notification", json=payload)

    assert pending.status_code == 200
    assert failed.status_code == 200
    assert settled.status_code == 200
    assert duplicate.status_code == 200

    db = TestingSessionLocal()
    try:
        payment = db.query(Payment).filter(Payment.provider_order_id == order_id).one()
        user = db.query(User).filter(User.id == payment.user_id).one()
        subscription = db.query(Subscription).filter(Subscription.user_id == user.id).one()
        assert payment.status == "settlement"
        assert user.role == "pro"
        assert subscription.status == "active"
        assert db.query(Subscription).filter(Subscription.user_id == user.id).count() == 1
    finally:
        db.close()


def test_midtrans_failed_payment_does_not_activate_subscription(monkeypatch):
    headers = register_login("midtrans-failed@example.com")
    monkeypatch.setattr("app.api.v1.payments.settings.pro_price_idr", 19900)
    monkeypatch.setattr(
        "app.services.midtrans_service.MidtransService.create_snap_transaction",
        lambda self, **kwargs: {"token": "sandbox-token", "redirect_url": "https://sandbox.example/pay"},
    )

    created = client.post("/api/v1/payments/create", headers=headers, json={"plan": "pro"})
    order_id = created.json()["order_id"]
    with patch("app.api.v1.payments.MidtransService.verify_notification_signature", return_value=True), \
         patch("app.api.v1.payments.MidtransService.get_transaction_status", return_value={
             "order_id": order_id,
             "gross_amount": "19900",
             "transaction_id": "tx-deny",
             "transaction_status": "deny",
             "payment_type": "gopay",
         }):
        response = client.post(
            "/api/v1/payments/notification",
            json={"order_id": order_id, "status_code": "202", "gross_amount": "19900", "signature_key": "valid"},
        )
    assert response.status_code == 200

    db = TestingSessionLocal()
    try:
        payment = db.query(Payment).filter(Payment.provider_order_id == order_id).one()
        user = db.query(User).filter(User.id == payment.user_id).one()
        assert payment.status == "deny"
        assert user.role == "free"
        assert db.query(Subscription).filter(Subscription.user_id == user.id).count() == 0
    finally:
        db.close()


def test_midtrans_refund_marks_subscription_canceled(monkeypatch):
    headers = register_login("midtrans-refund-flow@example.com")
    db = TestingSessionLocal()
    try:
        user = db.query(User).filter(User.email == "midtrans-refund-flow@example.com").one()
        user.role = "pro"
        subscription = Subscription(user_id=user.id, plan="pro", provider="midtrans", status="active")
        db.add(subscription)
        db.flush()
        payment = Payment(
            user_id=user.id,
            subscription_id=subscription.id,
            provider="midtrans",
            provider_order_id="refund-e2e-order",
            amount=19900,
            currency="IDR",
            plan="pro",
            status="settlement",
        )
        db.add(payment)
        db.commit()
        payment_id = payment.id
    finally:
        db.close()

    monkeypatch.setattr(
        "app.services.midtrans_service.MidtransService.refund_transaction",
        lambda self, order_id, amount, reason: {"status_code": "200", "refund_key": "refund-e2e-1"},
    )

    response = client.post(f"/api/v1/payments/{payment_id}/refund", headers=headers)
    assert response.status_code == 403

    db = TestingSessionLocal()
    try:
        user = db.query(User).filter(User.email == "midtrans-refund-flow@example.com").one()
        user.role = "admin"
        db.commit()
    finally:
        db.close()

    login = client.post(
        "/api/v1/auth/login",
        json={"email": "midtrans-refund-flow@example.com", "password": "securepass123"},
    )
    admin_headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    response = client.post(f"/api/v1/payments/{payment_id}/refund", headers=admin_headers)
    assert response.status_code == 200

    db = TestingSessionLocal()
    try:
        payment = db.query(Payment).filter(Payment.id == payment_id).one()
        subscription = db.query(Subscription).filter(Subscription.id == payment.subscription_id).one()
        assert payment.status == "refunded"
        assert payment.refund_status == "200"
        assert payment.refund_amount == 19900
        assert payment.refunded_at is not None
        assert subscription.status == "canceled"
    finally:
        db.close()
