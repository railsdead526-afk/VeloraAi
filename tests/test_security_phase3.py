from unittest.mock import patch

from app.models.billing import Payment, Subscription
from app.models.user import User
from app.tools.bootstrap import get_registry
from app.tools.executor import ToolExecutionError, execute_tool
from tests.conftest import TestingSessionLocal, client


def _register_and_login(email: str, password: str = "securepass123") -> dict:
    assert client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": password},
    ).status_code == 201
    response = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
    )
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _set_role(email: str, role: str) -> None:
    db = TestingSessionLocal()
    try:
        user = db.query(User).filter(User.email == email).one()
        user.role = role
        db.commit()
    finally:
        db.close()


def test_conversation_idor_denied():
    owner_headers = _register_and_login("security-owner@example.com")
    attacker_headers = _register_and_login("security-attacker@example.com")

    created = client.post(
        "/api/v1/conversations",
        headers=owner_headers,
        json={"title": "private"},
    )
    assert created.status_code == 201
    conversation_id = created.json()["id"]

    assert client.get(
        f"/api/v1/conversations/{conversation_id}",
        headers=attacker_headers,
    ).status_code == 404
    assert client.get(
        f"/api/v1/conversations/{conversation_id}/messages",
        headers=attacker_headers,
    ).status_code == 404
    assert client.patch(
        f"/api/v1/conversations/{conversation_id}",
        headers=attacker_headers,
        json={"title": "stolen"},
    ).status_code == 404
    assert client.delete(
        f"/api/v1/conversations/{conversation_id}",
        headers=attacker_headers,
    ).status_code == 404


def test_rag_idor_denied_and_search_is_user_scoped():
    owner_headers = _register_and_login("security-rag-owner@example.com")
    attacker_headers = _register_and_login("security-rag-attacker@example.com")

    with patch("app.api.v1.rag.process_document_index"):
        created = client.post(
            "/api/v1/rag/documents",
            headers=owner_headers,
            json={"name": "secret", "content": "owner-only secret", "source": "text"},
        )
    assert created.status_code == 201
    document_id = created.json()["id"]

    assert client.delete(
        f"/api/v1/rag/documents/{document_id}",
        headers=attacker_headers,
    ).status_code == 404
    assert client.post(
        f"/api/v1/rag/documents/{document_id}/reindex",
        headers=attacker_headers,
    ).status_code == 404
    search = client.post(
        "/api/v1/rag/search",
        headers=attacker_headers,
        json={"query": "owner-only secret", "limit": 5},
    )
    assert search.status_code in (200, 503)
    if search.status_code == 200:
        assert all(item["document_id"] != document_id for item in search.json())


def test_tool_permission_plan_and_confirmation_enforced():
    registry = get_registry()

    write_tool = registry.get("github_write_file")
    assert not write_tool.allows_plan("free")
    assert write_tool.allows_plan("pro")
    assert write_tool.requires_confirmation

    import asyncio
    with patch.object(write_tool, "handler", return_value={"ok": True}):
        try:
            asyncio.run(
                execute_tool(
                    registry,
                    name="github_write_file",
                    arguments={"repository": "org/repo", "path": "a.txt", "content": "x"},
                    plan="pro",
                    confirmed=False,
                )
            )
            raise AssertionError("tool execution should require confirmation")
        except ToolExecutionError as exc:
            assert "confirmation" in str(exc).lower()


def test_terminal_tools_require_confirmation_for_arbitrary_commands():
    registry = get_registry()
    for name in ("terminal_run_tests", "terminal_run_lint", "terminal_run_build", "terminal_install_package"):
        assert registry.get(name).requires_confirmation is True


def test_payment_webhook_rejects_missing_signature_fields():
    response = client.post(
        "/api/v1/payments/notification",
        json={"order_id": "x", "status_code": "200", "gross_amount": "10000"},
    )
    assert response.status_code == 400


def test_payment_webhook_rejects_invalid_signature():
    headers = _register_and_login("security-webhook@example.com")
    db = TestingSessionLocal()
    try:
        user = db.query(User).filter(User.email == "security-webhook@example.com").one()
        payment = Payment(
            user_id=user.id,
            provider="midtrans",
            provider_order_id="security-order",
            amount=10000,
            currency="IDR",
            plan="pro",
            status="pending",
        )
        db.add(payment)
        db.commit()
    finally:
        db.close()

    response = client.post(
        "/api/v1/payments/notification",
        json={
            "order_id": "security-order",
            "status_code": "200",
            "gross_amount": "10000",
            "signature_key": "invalid",
        },
    )
    assert response.status_code == 403
    assert headers


def test_refund_is_admin_only_and_non_settled_is_rejected():
    user_headers = _register_and_login("security-refund-user@example.com")
    db = TestingSessionLocal()
    try:
        user = db.query(User).filter(User.email == "security-refund-user@example.com").one()
        payment = Payment(
            user_id=user.id,
            provider="midtrans",
            provider_order_id="security-refund-order",
            amount=10000,
            currency="IDR",
            plan="pro",
            status="pending",
        )
        db.add(payment)
        db.commit()
        payment_id = payment.id
    finally:
        db.close()

    denied = client.post(
        f"/api/v1/payments/{payment_id}/refund",
        headers=user_headers,
    )
    assert denied.status_code == 403

    _set_role("security-refund-user@example.com", "admin")
    admin_login = client.post(
        "/api/v1/auth/login",
        json={"email": "security-refund-user@example.com", "password": "securepass123"},
    )
    admin_headers = {"Authorization": f"Bearer {admin_login.json()['access_token']}"}
    assert client.post(
        f"/api/v1/payments/{payment_id}/refund",
        headers=admin_headers,
    ).status_code == 409


def test_expired_or_invalid_bearer_token_is_rejected():
    response = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": "Bearer not-a-real-token"},
    )
    assert response.status_code == 401
