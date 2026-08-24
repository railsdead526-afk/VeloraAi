from unittest.mock import patch

import pytest

from app.core.config import Settings
from app.services.ai_provider import AIProviderConfig, get_provider_config
from app.services.ai_service import generate_ai_reply_from_history


def _production_settings() -> Settings:
    config = Settings()
    config.app_env = "production"
    config.app_debug = False
    config.secret_key = "s" * 64
    config.database_url = "postgresql://user:pass@localhost/velora"
    config.database_schema = "velora"
    config.rate_limit_storage_uri = "redis://localhost:6379/0"
    config.cors_origins = ["https://velora.example.com"]
    config.midtrans_server_key = "server-key"
    config.midtrans_client_key = "client-key"
    config.midtrans_is_production = True
    config.midtrans_base_url = "https://api.midtrans.com"
    config.midtrans_snap_base_url = "https://app.midtrans.com"
    config.pro_price_idr = 99000
    config.max_price_idr = 199000
    return config


def test_production_rejects_mock_provider():
    config = _production_settings()
    config.ai_provider = "mock"
    with pytest.raises(RuntimeError, match="AI_PROVIDER=mock"):
        config.validate()


def test_production_openai_provider_requires_key():
    config = _production_settings()
    config.ai_provider = "openai"
    config.openai_api_key = ""
    with pytest.raises(RuntimeError, match="OPENAI_API_KEY"):
        config.validate()


def test_provider_config_exposes_configured_openai_provider():
    with patch.object(__import__("app.services.ai_provider", fromlist=["settings"]).settings, "ai_provider", "openai"), patch.object(
        __import__("app.services.ai_provider", fromlist=["settings"]).settings,
        "openai_api_key",
        "test-key",
    ), patch.object(
        __import__("app.services.ai_provider", fromlist=["settings"]).settings,
        "openai_base_url",
        "https://api.example.test/v1",
    ), patch.object(
        __import__("app.services.ai_provider", fromlist=["settings"]).settings,
        "openai_model",
        "test-model",
    ):
        config = get_provider_config()

    assert config == AIProviderConfig(
        name="openai",
        api_key="test-key",
        base_url="https://api.example.test/v1",
        model="test-model",
    )


def test_openai_request_uses_configured_endpoint_and_model():
    fake_response = type(
        "FakeResponse",
        (),
        {
            "status_code": 200,
            "raise_for_status": lambda self: None,
            "json": lambda self: {
                "choices": [{"message": {"content": "real-provider"}}],
                "usage": {"prompt_tokens": 5, "completion_tokens": 3},
            },
        },
    )()

    class FakeClient:
        def __init__(self, *args, **kwargs):
            self.request = None

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def post(self, url, headers, json):
            self.request = (url, headers, json)
            FakeClient.last_request = self.request
            return fake_response

    service_settings = __import__("app.services.ai_service", fromlist=["settings"]).settings
    with patch.object(service_settings, "ai_provider", "openai"), patch.object(service_settings, "openai_api_key", "test-key"), patch.object(
        service_settings, "openai_base_url", "https://api.example.test/v1"
    ), patch.object(service_settings, "openai_model", "test-model"), patch.object(service_settings, "ai_max_retries", 0), patch(
        "app.services.ai_service.httpx.Client", FakeClient
    ):
        result = generate_ai_reply_from_history([{"role": "user", "content": "hello"}])

    assert result == "real-provider"
    url, headers, payload = FakeClient.last_request
    assert url == "https://api.example.test/v1/chat/completions"
    assert headers["Authorization"] == "Bearer test-key"
    assert payload["model"] == "test-model"


def test_production_requires_midtrans_production_mode_and_endpoints():
    config = _production_settings()
    config.ai_provider = "openai"
    config.openai_api_key = "test-key"

    config.midtrans_is_production = False
    with pytest.raises(RuntimeError, match="MIDTRANS_IS_PRODUCTION"):
        config.validate()

    config.midtrans_is_production = True
    config.midtrans_base_url = "https://api.sandbox.midtrans.com"
    with pytest.raises(RuntimeError, match="MIDTRANS_BASE_URL"):
        config.validate()

    config.midtrans_base_url = "https://api.midtrans.com"
    config.midtrans_snap_base_url = "https://app.sandbox.midtrans.com"
    with pytest.raises(RuntimeError, match="MIDTRANS_SNAP_BASE_URL"):
        config.validate()
