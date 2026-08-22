"""Data portability export.

The security property that matters most here: an export file is treated as
public once it leaves the server, so it must never carry material that would
let someone impersonate the user or reach their third-party accounts.
"""

import json

from app.core.config import settings
from app.core.crypto import generate_key, reset_secret_box
from app.models.conversation import Conversation
from app.models.message import Message
from app.models.user import User
from app.services.credential_service import store_credential
from app.services.data_export import build_export
from tests.conftest import client

STRONG_PASSWORD = "Str0ng!Passw0rd"


def _auth_headers(email: str) -> dict[str, str]:
    client.post("/api/v1/auth/register", json={"email": email, "password": STRONG_PASSWORD})
    token = client.post(
        "/api/v1/auth/login", json={"email": email, "password": STRONG_PASSWORD}
    ).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _make_user(db, email: str) -> User:
    user = User(email=email, hashed_password="argon2-hash-placeholder", role="pro")
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def test_export_contains_the_users_own_content(db):
    user = _make_user(db, "exporter@example.com")
    conversation = Conversation(user_id=user.id, title="Planning")
    db.add(conversation)
    db.commit()
    db.refresh(conversation)
    db.add(Message(conversation_id=conversation.id, role="user", content="hello there"))
    db.commit()

    payload = build_export(db, user=user)

    assert payload["account"]["email"] == "exporter@example.com"
    assert payload["export_format_version"] == "1.0"
    assert len(payload["conversations"]) == 1
    assert payload["conversations"][0]["title"] == "Planning"
    assert payload["conversations"][0]["messages"][0]["content"] == "hello there"


def test_export_never_includes_the_password_hash(db):
    user = _make_user(db, "no-hash@example.com")
    serialized = json.dumps(build_export(db, user=user))
    assert "argon2-hash-placeholder" not in serialized
    assert "hashed_password" not in serialized


def test_export_never_includes_third_party_secrets(db, monkeypatch):
    monkeypatch.setattr(settings, "credential_encryption_keys", generate_key())
    reset_secret_box()
    try:
        user = _make_user(db, "no-secrets@example.com")
        store_credential(db, user_id=user.id, provider="github", secret="ghp_do_not_export_me")

        payload = build_export(db, user=user)
        serialized = json.dumps(payload)

        assert "ghp_do_not_export_me" not in serialized
        assert "secret_ciphertext" not in serialized
        # The connection is still disclosed, just not the credential.
        assert payload["integrations"][0]["provider"] == "github"
        assert payload["integrations"][0]["secret_fingerprint"] == "****t_me"
    finally:
        reset_secret_box()


def test_export_is_scoped_to_the_requesting_user(db):
    alice = _make_user(db, "alice-export@example.com")
    bob = _make_user(db, "bob-export@example.com")

    db.add(Conversation(user_id=alice.id, title="Alice private"))
    db.add(Conversation(user_id=bob.id, title="Bob private"))
    db.commit()

    alice_export = json.dumps(build_export(db, user=alice))
    assert "Alice private" in alice_export
    assert "Bob private" not in alice_export


def test_export_endpoint_downloads_a_json_attachment():
    headers = _auth_headers("download-export@example.com")
    response = client.get("/api/v1/auth/me/export", headers=headers)

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/json")
    assert "attachment" in response.headers["content-disposition"]
    assert ".json" in response.headers["content-disposition"]
    assert response.headers["cache-control"] == "no-store"

    payload = response.json()
    assert payload["account"]["email"] == "download-export@example.com"
    assert "notice" in payload


def test_export_requires_authentication():
    assert client.get("/api/v1/auth/me/export").status_code == 401


def test_export_records_an_audit_event(db):
    from app.models.audit_log import AuditLog

    headers = _auth_headers("audited-export@example.com")
    client.get("/api/v1/auth/me/export", headers=headers)

    events = [row.event for row in db.query(AuditLog).all()]
    assert "account.data_exported" in events


def test_export_includes_billing_records_for_reconciliation(db):
    from app.services.billing_service import apply_payment_notification, create_payment_intent

    user = _make_user(db, "billing-export@example.com")
    payment = create_payment_intent(db, user_id=user.id, plan="pro", amount=99_000)
    apply_payment_notification(
        db,
        provider="midtrans",
        provider_order_id=payment.provider_order_id,
        provider_transaction_id="txn-export",
        transaction_status="settlement",
    )

    payload = build_export(db, user=user)
    assert payload["payments"][0]["amount"] == 99_000
    assert payload["payments"][0]["invoice_number"] is not None
    assert payload["subscriptions"][0]["plan"] == "pro"
