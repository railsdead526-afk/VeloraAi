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


def test_manual_payment_create_and_admin_approve(monkeypatch):
    headers = register_login("manual-flow@example.com")
    monkeypatch.setattr("app.api.v1.payments.settings.payment_provider", "manual")
    monkeypatch.setattr("app.api.v1.payments.settings.pro_price_idr", 19900)
    monkeypatch.setattr("app.api.v1.payments.settings.manual_payment_instructions", "Transfer ke rekening admin")

    created = client.post("/api/v1/payments/create", headers=headers, json={"plan": "pro"})
    assert created.status_code == 200
    body = created.json()
    assert body["payment_provider"] == "manual"
    assert body["snap_token"] is None
    assert body["manual_instructions"] == "Transfer ke rekening admin"
    order_id = body["order_id"]

    db = TestingSessionLocal()
    try:
        payment = db.query(Payment).filter(Payment.provider_order_id == order_id).one()
        payment_id = payment.id
        user = db.query(User).filter(User.id == payment.user_id).one()
        user.role = "admin"
        db.commit()
    finally:
        db.close()

    denied = client.post(f"/api/v1/payments/{payment_id}/approve", headers=headers)
    assert denied.status_code == 403

    login = client.post(
        "/api/v1/auth/login",
        json={"email": "manual-flow@example.com", "password": "securepass123"},
    )
    admin_headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    approved = client.post(f"/api/v1/payments/{payment_id}/approve", headers=admin_headers)
    assert approved.status_code == 200
    assert approved.json()["status"] == "settlement"
    assert approved.json()["user_role"] == "pro"

    again = client.post(f"/api/v1/payments/{payment_id}/approve", headers=admin_headers)
    assert again.status_code == 409

    db = TestingSessionLocal()
    try:
        payment = db.query(Payment).filter(Payment.id == payment_id).one()
        user = db.query(User).filter(User.id == payment.user_id).one()
        subscription = db.query(Subscription).filter(Subscription.user_id == payment.user_id).one()
        assert payment.status == "settlement"
        assert user.role == "pro"
        assert subscription.status == "active"
    finally:
        db.close()


def test_midtrans_provider_still_works_by_default(monkeypatch):
    headers = register_login("default-provider@example.com")
    monkeypatch.setattr("app.api.v1.payments.settings.pro_price_idr", 19900)
    monkeypatch.setattr(
        "app.services.midtrans_service.MidtransService.create_snap_transaction",
        lambda self, **kwargs: {"token": "sandbox-token", "redirect_url": "https://sandbox.example/pay"},
    )

    created = client.post("/api/v1/payments/create", headers=headers, json={"plan": "pro"})
    assert created.status_code == 200
    body = created.json()
    assert body["payment_provider"] == "midtrans"
    assert body["snap_token"] == "sandbox-token"
    assert body["manual_instructions"] is None