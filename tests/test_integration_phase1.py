from unittest.mock import patch

from app.models.billing import Payment, Subscription
from app.models.user import User
from app.services.ai_service import AIResult
from tests.conftest import TestingSessionLocal, client


def _register_and_login(email: str, password: str = "securepass123") -> tuple[str, dict]:
    assert client.post("/api/v1/auth/register", json={"email": email, "password": password}).status_code == 201
    response = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200
    token = response.json()["access_token"]
    return token, {"Authorization": f"Bearer {token}"}


def _set_role(email: str, role: str) -> None:
    db = TestingSessionLocal()
    try:
        user = db.query(User).filter(User.email == email).one()
        user.role = role
        db.commit()
    finally:
        db.close()


def test_auth_plan_and_conversation_flow():
    _token, headers = _register_and_login("phase1-auth@example.com")
    assert client.get("/api/v1/auth/me", headers=headers).json()["role"] == "free"
    assert client.get("/api/v1/auth/premium-only", headers=headers).status_code == 403

    _set_role("phase1-auth@example.com", "pro")
    login = client.post("/api/v1/auth/login", json={"email": "phase1-auth@example.com", "password": "securepass123"})
    pro_headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    assert client.get("/api/v1/auth/premium-only", headers=pro_headers).status_code == 200
    assert client.post("/api/v1/conversations", headers=pro_headers, json={"title": "Phase 1"}).status_code == 201


def test_plan_matrix_is_available_to_core_services():
    from app.core.plans import get_plan_policy

    expected = {"free": (100_000, 100), "pro": (1_000_000, 1_000), "max": (5_000_000, 10_000)}
    for role, (tokens, requests) in expected.items():
        policy = get_plan_policy(role)
        assert policy.monthly_token_limit == tokens
        assert policy.monthly_request_limit == requests


def test_ai_chat_and_streaming_flow():
    _token, headers = _register_and_login("phase1-ai@example.com")
    conversation = client.post("/api/v1/conversations", headers=headers, json={"title": "AI integration"})
    assert conversation.status_code == 201
    conversation_id = conversation.json()["id"]

    with patch("app.api.v1.conversations.settings.ai_provider", "mock"):
        response = client.post(f"/api/v1/conversations/{conversation_id}/messages", headers=headers, json={"content": "Hello VeloraAi", "use_rag": False, "confirm_tools": False})
        assert response.status_code == 201
        assert response.json()["assistant_message"]["role"] == "assistant"

        stream = client.post(f"/api/v1/conversations/{conversation_id}/messages/stream", headers=headers, json={"content": "Stream hello", "use_rag": False, "confirm_tools": False})
        assert stream.status_code == 200
        assert "text/event-stream" in stream.headers["content-type"]
        assert '"type": "done"' in stream.text


def test_tools_registry_integration_contract():
    result = AIResult(content="tool result", input_tokens=10, output_tokens=5, model="mock-model")
    with patch("app.api.v1.conversations.settings.ai_provider", "openai"), patch("app.api.v1.conversations.generate_ai_reply_with_tools", return_value=result) as mocked:
        _token, headers = _register_and_login("phase1-tools@example.com")
        conversation = client.post("/api/v1/conversations", headers=headers, json={"title": "Tools"}).json()
        response = client.post(f"/api/v1/conversations/{conversation['id']}/messages", headers=headers, json={"content": "inspect repository", "use_rag": False, "confirm_tools": False})
        assert response.status_code == 201
        mocked.assert_called_once()
        assert mocked.call_args.kwargs["plan"] == "free"


def test_rag_document_ownership_and_lifecycle():
    _token_a, headers_a = _register_and_login("phase1-rag-a@example.com")
    _token_b, headers_b = _register_and_login("phase1-rag-b@example.com")

    with patch("app.api.v1.rag.process_document_index"):
        created = client.post("/api/v1/rag/documents", headers=headers_a, json={"name": "notes", "content": "private document content", "source": "text"})
    assert created.status_code == 201
    document_id = created.json()["id"]
    assert created.json()["status"] == "queued"
    assert any(item["id"] == document_id for item in client.get("/api/v1/rag/documents", headers=headers_a).json())
    assert all(item["id"] != document_id for item in client.get("/api/v1/rag/documents", headers=headers_b).json())
    assert client.delete(f"/api/v1/rag/documents/{document_id}", headers=headers_b).status_code == 404
    assert client.delete(f"/api/v1/rag/documents/{document_id}", headers=headers_a).status_code == 204


def test_payment_create_and_duplicate_settlement_is_idempotent(monkeypatch):
    _token, headers = _register_and_login("phase1-payment@example.com")
    monkeypatch.setattr("app.api.v1.payments.settings.pro_price_idr", 19900)
    monkeypatch.setattr("app.services.midtrans_service.MidtransService.create_snap_transaction", lambda self, **kwargs: {"token": "snap-token", "redirect_url": "https://example.test/pay"})
    created = client.post("/api/v1/payments/create", headers=headers, json={"plan": "pro"})
    assert created.status_code == 200
    order_id = created.json()["order_id"]

    with patch("app.api.v1.payments.MidtransService.get_transaction_status", return_value={"order_id": order_id, "gross_amount": "19900", "transaction_id": "tx-1", "transaction_status": "settlement", "payment_type": "gopay"}), patch("app.api.v1.payments.MidtransService.verify_notification_signature", return_value=True):
        payload = {"order_id": order_id, "status_code": "200", "gross_amount": "19900", "signature_key": "valid"}
        assert client.post("/api/v1/payments/notification", json=payload).status_code == 200
        assert client.post("/api/v1/payments/notification", json=payload).status_code == 200

    db = TestingSessionLocal()
    try:
        payment = db.query(Payment).filter(Payment.provider_order_id == order_id).one()
        subscription = db.query(Subscription).filter(Subscription.user_id == payment.user_id).one()
        user = db.query(User).filter(User.id == payment.user_id).one()
        assert payment.status == "settlement"
        assert subscription.status == "active"
        assert subscription.plan == "pro"
        assert user.role == "pro"
        assert db.query(Subscription).filter(Subscription.user_id == payment.user_id).count() == 1
    finally:
        db.close()


def test_refund_requires_admin(monkeypatch):
    _token, headers = _register_and_login("phase1-refund-user@example.com")
    db = TestingSessionLocal()
    try:
        user = db.query(User).filter(User.email == "phase1-refund-user@example.com").one()
        payment = Payment(user_id=user.id, provider="midtrans", provider_order_id="refund-order", amount=19900, currency="IDR", plan="pro", status="settlement")
        db.add(payment)
        db.commit()
        payment_id = payment.id
    finally:
        db.close()

    monkeypatch.setattr("app.services.midtrans_service.MidtransService.refund_transaction", lambda self, order_id, amount, reason: {"status_code": "200", "refund_key": "refund-1"})
    assert client.post(f"/api/v1/payments/{payment_id}/refund", headers=headers).status_code == 403

    _set_role("phase1-refund-user@example.com", "admin")
    login = client.post("/api/v1/auth/login", json={"email": "phase1-refund-user@example.com", "password": "securepass123"})
    admin_headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    refunded = client.post(f"/api/v1/payments/{payment_id}/refund", headers=admin_headers)
    assert refunded.status_code == 200
    assert refunded.json()["status"] == "200"


def test_protected_surfaces_require_authentication():
    for path in ("/api/v1/auth/me", "/api/v1/conversations", "/api/v1/rag/documents", "/api/v1/rag/search", "/api/v1/payments/config"):
        assert client.get(path).status_code in (401, 403, 405)
