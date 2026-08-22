from app.core.config import settings
from tests.conftest import client


def test_health_is_cheap_and_reports_version():
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert "version" in body


def test_readiness_reports_every_dependency():
    response = client.get("/api/v1/ready")
    body = response.json()
    assert set(body["checks"]) == {
        "database",
        "rate_limit_storage",
        "ai_provider",
        "credential_encryption",
        "sandbox",
    }
    assert body["checks"]["database"]["status"] == "ok"


def test_readiness_returns_503_when_a_dependency_is_down(monkeypatch):
    monkeypatch.setattr(
        "app.api.v1.system._check_ai_provider",
        lambda: {"status": "error", "detail": "ConnectError"},
    )
    response = client.get("/api/v1/ready")
    assert response.status_code == 503
    assert response.json()["status"] == "not_ready"
    assert "ai_provider" in response.json()["failed"]


def test_metrics_requires_a_token_when_one_is_configured(monkeypatch):
    monkeypatch.setattr(settings, "metrics_token", "scrape-secret")
    assert client.get("/api/v1/metrics").status_code == 401
    assert (
        client.get("/api/v1/metrics", headers={"Authorization": "Bearer wrong"}).status_code == 401
    )
    ok = client.get("/api/v1/metrics", headers={"Authorization": "Bearer scrape-secret"})
    assert ok.status_code == 200
    assert b"velora_http_requests_total" in ok.content


def test_metrics_can_be_disabled(monkeypatch):
    monkeypatch.setattr(settings, "metrics_enabled", False)
    assert client.get("/api/v1/metrics").status_code == 404


def test_security_headers_are_present():
    response = client.get("/api/v1/health")
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert "Content-Security-Policy" in response.headers
    assert response.headers["Cross-Origin-Opener-Policy"] == "same-origin"
    assert "X-Request-ID" in response.headers


def test_path_normalisation_keeps_metric_cardinality_bounded():
    from app.core.metrics import normalize_path

    assert (
        normalize_path("/api/v1/conversations/42/messages") == "/api/v1/conversations/{id}/messages"
    )
    assert normalize_path("/api/v1/health") == "/api/v1/health"


def test_log_redaction_strips_credentials():
    from app.core.observability import redact

    assert "ghp_" not in redact("token=ghp_abcdefghijklmnopqrstuvwxyz")
    assert "REDACTED" in redact('{"api_key": "sk-abcdefghijklmnop"}')
    assert "REDACTED" in redact("Authorization: Bearer abcdefghijklmnopqrst")
