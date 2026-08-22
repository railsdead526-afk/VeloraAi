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
    ],
)
def test_nonsensical_values_are_refused_everywhere(attribute, value):
    config = Settings()
    config.app_env = "development"
    setattr(config, attribute, value)
    with pytest.raises(RuntimeError):
        config.validate()
