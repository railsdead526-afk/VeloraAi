"""Production configuration gates.

`Settings.validate()` is the last line of defence against a deployment that is
technically running but commercially or legally unsafe. Each gate here maps to
a real failure mode.
"""

import pytest

from app.core.config import Settings
from app.core.crypto import generate_key


def _production_settings() -> Settings:
    config = Settings()
    config.app_env = "production"
    config.app_debug = False
    config.secret_key = "s" * 64
    config.database_url = "postgresql://user:pass@localhost/velora"
    config.database_schema = "velora"
    config.rate_limit_storage_uri = "redis://localhost:6379/0"
    config.cors_origins = ["https://app.velora.example.com"]
    config.trusted_hosts = ["api.velora.example.com"]
    config.midtrans_server_key = "server-key"
    config.midtrans_client_key = "client-key"
    config.pro_price_idr = 99_000
    config.max_price_idr = 199_000
    config.ai_provider = "openai"
    config.openai_api_key = "sk-test"
    config.credential_encryption_keys = generate_key()
    config.allow_env_tool_credentials = False
    config.require_email_verification = True
    config.frontend_base_url = "https://app.velora.example.com"
    config.metrics_enabled = True
    config.metrics_token = "scrape-token"
    config.smtp_host = "smtp.example.com"
    config.smtp_from = "VeloraAi <no-reply@velora.example.com>"
    return config


def test_a_fully_configured_production_settings_object_validates():
    _production_settings().validate()


def test_missing_credential_encryption_keys_is_refused():
    config = _production_settings()
    config.credential_encryption_keys = ""
    with pytest.raises(RuntimeError, match="CREDENTIAL_ENCRYPTION_KEYS"):
        config.validate()


def test_shared_env_tool_credentials_are_refused():
    """The tenant-isolation escape hatch must never be reachable in production."""
    config = _production_settings()
    config.allow_env_tool_credentials = True
    with pytest.raises(RuntimeError, match="ALLOW_ENV_TOOL_CREDENTIALS"):
        config.validate()


def test_unverified_signups_are_refused():
    config = _production_settings()
    config.require_email_verification = False
    with pytest.raises(RuntimeError, match="REQUIRE_EMAIL_VERIFICATION"):
        config.validate()


def test_plaintext_cors_origin_is_refused():
    config = _production_settings()
    config.cors_origins = ["http://app.velora.example.com"]
    with pytest.raises(RuntimeError, match="https"):
        config.validate()


def test_missing_trusted_hosts_is_refused():
    config = _production_settings()
    config.trusted_hosts = []
    with pytest.raises(RuntimeError, match="TRUSTED_HOSTS"):
        config.validate()


def test_wildcard_trusted_host_is_refused():
    config = _production_settings()
    config.trusted_hosts = ["*"]
    with pytest.raises(RuntimeError, match="TRUSTED_HOSTS"):
        config.validate()


def test_plaintext_frontend_url_is_refused():
    config = _production_settings()
    config.frontend_base_url = "http://app.velora.example.com"
    with pytest.raises(RuntimeError, match="FRONTEND_BASE_URL"):
        config.validate()


def test_production_without_an_email_transport_is_refused():
    """Verification and reset links are undeliverable without SMTP."""
    config = _production_settings()
    config.smtp_host = ""
    with pytest.raises(RuntimeError, match="SMTP_HOST"):
        config.validate()


def test_production_without_a_from_address_is_refused():
    config = _production_settings()
    config.smtp_from = ""
    config.smtp_username = ""
    with pytest.raises(RuntimeError, match="SMTP_FROM"):
        config.validate()


def test_conflicting_tls_modes_are_refused():
    config = _production_settings()
    config.smtp_use_ssl = True
    config.smtp_use_starttls = True
    with pytest.raises(RuntimeError, match="mutually exclusive"):
        config.validate()


def test_unprotected_metrics_endpoint_is_refused():
    config = _production_settings()
    config.metrics_token = ""
    with pytest.raises(RuntimeError, match="METRICS_TOKEN"):
        config.validate()


def test_public_schema_is_refused():
    config = _production_settings()
    config.database_schema = "public"
    with pytest.raises(RuntimeError, match="DATABASE_SCHEMA"):
        config.validate()


def test_invalid_encryption_key_is_refused_outside_production():
    config = Settings()
    config.app_env = "development"
    config.credential_encryption_keys = "not-a-valid-key"
    with pytest.raises(RuntimeError):
        config.validate()


@pytest.mark.parametrize(
    ("attribute", "value"),
    [
        ("subscription_period_days", 0),
        ("subscription_grace_days", -1),
        ("vat_percent", 101.0),
        ("refresh_token_expire_days", 0),
        ("max_active_sessions", 0),
        ("login_max_failed_attempts", 0),
        ("password_reset_ttl_minutes", 0),
        ("email_verification_ttl_hours", 0),
        ("database_pool_size", 0),
        ("smtp_port", 0),
        ("smtp_port", 70000),
        ("smtp_timeout_seconds", 0.0),
    ],
)
def test_nonsensical_values_are_refused_everywhere(attribute, value):
    config = Settings()
    config.app_env = "development"
    setattr(config, attribute, value)
    with pytest.raises(RuntimeError):
        config.validate()


# --------------------------------------------------------------------------- #
# Pre-flight
#
# Settings.validate() stops at the first problem, which on a hosted platform
# means a slow deploy-fail-fix loop. The pre-flight script reports everything
# at once, from outside the app.
# --------------------------------------------------------------------------- #


def _valid_production_env() -> dict[str, str]:
    from app.core.crypto import generate_key

    return {
        "APP_ENV": "production",
        "SECRET_KEY": "s" * 64,
        "CREDENTIAL_ENCRYPTION_KEYS": generate_key(),
        "DATABASE_URL": "postgresql://u:p@aws-0-ap.pooler.supabase.com:5432/postgres",
        "DATABASE_SCHEMA": "velora",
        "RATE_LIMIT_STORAGE_URI": "redis://localhost:6379/0",
        "CORS_ORIGINS": "https://app.example.com",
        "TRUSTED_HOSTS": "api.example.com",
        "FRONTEND_BASE_URL": "https://app.example.com",
        "REQUIRE_EMAIL_VERIFICATION": "true",
        "METRICS_TOKEN": "scrape",
        "SMTP_HOST": "smtp.example.com",
        "SMTP_FROM": "no-reply@example.com",
        "AI_PROVIDER": "openai",
        "OPENAI_API_KEY": "sk-test",
        "PAYMENT_PROVIDER": "disabled",
    }


def _preflight(env: dict[str, str]) -> list[tuple[str, str, str]]:
    from scripts.preflight import _problems

    return _problems(env)


def _failed_keys(env: dict[str, str]) -> set[str]:
    from scripts.preflight import FAIL

    return {key for level, key, _ in _preflight(env) if level == FAIL}


def test_preflight_passes_a_valid_production_env():
    assert _failed_keys(_valid_production_env()) == set()


def test_preflight_catches_the_supabase_ipv6_endpoint():
    """The direct endpoint is unreachable from Railway and fails opaquely."""
    env = _valid_production_env()
    env["DATABASE_URL"] = "postgresql://u:p@db.abcdef.supabase.co:5432/postgres"
    assert "DATABASE_URL" in _failed_keys(env)


def test_preflight_catches_a_trailing_slash_in_cors():
    """Origins are compared exactly, so a trailing slash silently blocks the UI."""
    env = _valid_production_env()
    env["CORS_ORIGINS"] = "https://app.example.com/"
    assert "CORS_ORIGINS" in _failed_keys(env)


def test_preflight_catches_a_url_in_trusted_hosts():
    env = _valid_production_env()
    env["TRUSTED_HOSTS"] = "https://api.example.com"
    assert "TRUSTED_HOSTS" in _failed_keys(env)


def test_preflight_reports_every_problem_at_once():
    """The whole point: one pass instead of one redeploy per mistake."""
    env = _valid_production_env()
    env["SECRET_KEY"] = "short"
    env["DATABASE_SCHEMA"] = "public"
    env["RATE_LIMIT_STORAGE_URI"] = "memory://"
    env["AI_PROVIDER"] = "mock"
    assert {
        "SECRET_KEY",
        "DATABASE_SCHEMA",
        "RATE_LIMIT_STORAGE_URI",
        "AI_PROVIDER",
    } <= _failed_keys(env)


def test_preflight_skips_gates_outside_production():
    env = {"APP_ENV": "development"}
    assert _failed_keys(env) == set()


def test_preflight_requires_payment_config_only_when_selling():
    env = _valid_production_env()
    env["PAYMENT_PROVIDER"] = "midtrans"
    failures = _failed_keys(env)
    assert "MIDTRANS_SERVER_KEY" in failures
    assert "PRO_PRICE_IDR" in failures


def test_preflight_agrees_with_the_runtime_validator():
    """The two must not drift: a config the script passes should boot."""
    import os
    from unittest.mock import patch

    from app.core.config import Settings

    env = _valid_production_env()
    with patch.dict(os.environ, env, clear=True):
        Settings().validate()
