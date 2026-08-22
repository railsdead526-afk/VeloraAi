from app.core.config import settings
from app.core.crypto import generate_key, reset_secret_box
from app.models.integration import UserIntegration
from tests.conftest import client

STRONG_PASSWORD = "Str0ng!Passw0rd"


def _auth_headers(email: str) -> dict[str, str]:
    client.post("/api/v1/auth/register", json={"email": email, "password": STRONG_PASSWORD})
    token = client.post(
        "/api/v1/auth/login", json={"email": email, "password": STRONG_PASSWORD}
    ).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _with_keys(monkeypatch):
    monkeypatch.setattr(settings, "credential_encryption_keys", generate_key())
    reset_secret_box()


def test_endpoint_requires_authentication():
    assert client.get("/api/v1/integrations").status_code == 401


def test_connect_and_list_never_returns_the_secret(monkeypatch, db):
    _with_keys(monkeypatch)
    headers = _auth_headers("integrations-api@example.com")

    created = client.put(
        "/api/v1/integrations",
        json={
            "provider": "github",
            "secret": "ghp_a_real_looking_token_value",
            "display_name": "Personal account",
        },
        headers=headers,
    )
    assert created.status_code == 201
    body = created.json()
    assert "secret" not in body
    assert body["secret_fingerprint"] == "****alue"
    assert body["status"] == "active"

    listed = client.get("/api/v1/integrations", headers=headers).json()
    assert len(listed) == 1
    assert "secret" not in listed[0]
    assert "ghp_a_real_looking_token_value" not in str(listed)


def test_stored_ciphertext_does_not_contain_the_plaintext(monkeypatch, db):
    _with_keys(monkeypatch)
    headers = _auth_headers("ciphertext-check@example.com")
    client.put(
        "/api/v1/integrations",
        json={"provider": "vercel", "secret": "vercel_plaintext_secret"},
        headers=headers,
    )
    row = db.query(UserIntegration).filter(UserIntegration.provider == "vercel").one()
    assert "vercel_plaintext_secret" not in row.secret_ciphertext


def test_users_only_see_their_own_integrations(monkeypatch):
    _with_keys(monkeypatch)
    alice = _auth_headers("alice-api@example.com")
    bob = _auth_headers("bob-api@example.com")

    client.put(
        "/api/v1/integrations",
        json={"provider": "github", "secret": "alice_secret_token"},
        headers=alice,
    )

    assert client.get("/api/v1/integrations", headers=bob).json() == []
    assert len(client.get("/api/v1/integrations", headers=alice).json()) == 1


def test_one_user_cannot_delete_another_users_integration(monkeypatch):
    _with_keys(monkeypatch)
    alice = _auth_headers("alice-del@example.com")
    bob = _auth_headers("bob-del@example.com")

    client.put(
        "/api/v1/integrations",
        json={"provider": "github", "secret": "alice_secret_token"},
        headers=alice,
    )

    assert client.delete("/api/v1/integrations/github", headers=bob).status_code == 404
    assert len(client.get("/api/v1/integrations", headers=alice).json()) == 1


def test_unknown_provider_is_rejected(monkeypatch):
    _with_keys(monkeypatch)
    headers = _auth_headers("bad-provider-api@example.com")
    response = client.put(
        "/api/v1/integrations",
        json={"provider": "dropbox", "secret": "some_secret_value"},
        headers=headers,
    )
    assert response.status_code == 422


def test_reconnecting_replaces_the_previous_secret(monkeypatch):
    _with_keys(monkeypatch)
    headers = _auth_headers("replace-api@example.com")
    for secret in ("first_secret_aaaa", "second_secret_bbbb"):
        client.put(
            "/api/v1/integrations",
            json={"provider": "github", "secret": secret},
            headers=headers,
        )
    listed = client.get("/api/v1/integrations", headers=headers).json()
    assert len(listed) == 1
    assert listed[0]["secret_fingerprint"] == "****bbbb"


def test_disconnect_removes_the_integration(monkeypatch):
    _with_keys(monkeypatch)
    headers = _auth_headers("disconnect-api@example.com")
    client.put(
        "/api/v1/integrations",
        json={"provider": "cloudflare", "secret": "cf_secret_token"},
        headers=headers,
    )
    assert client.delete("/api/v1/integrations/cloudflare", headers=headers).status_code == 200
    assert client.get("/api/v1/integrations", headers=headers).json() == []


def test_connect_fails_clearly_when_encryption_is_not_configured(monkeypatch):
    headers = _auth_headers("no-keys@example.com")
    monkeypatch.setattr(settings, "credential_encryption_keys", "")
    reset_secret_box()
    response = client.put(
        "/api/v1/integrations",
        json={"provider": "github", "secret": "some_secret_value"},
        headers=headers,
    )
    assert response.status_code == 503
    assert "CREDENTIAL_ENCRYPTION_KEYS" in response.json()["detail"]


def test_supported_providers_are_advertised(monkeypatch):
    _with_keys(monkeypatch)
    headers = _auth_headers("providers-api@example.com")
    providers = client.get("/api/v1/integrations/providers", headers=headers).json()["providers"]
    assert set(providers) == {"github", "vercel", "railway", "cloudflare", "supabase"}
