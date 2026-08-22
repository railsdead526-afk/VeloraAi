from app.services import ai_provider


def test_provider_config_for_openai(monkeypatch):
    monkeypatch.setattr(ai_provider.settings, "ai_provider", "openai")
    monkeypatch.setattr(ai_provider.settings, "openai_api_key", "test-key")
    monkeypatch.setattr(ai_provider.settings, "openai_base_url", "https://api.openai.com/v1")
    monkeypatch.setattr(ai_provider.settings, "openai_model", "gpt-test")

    config = ai_provider.get_provider_config()

    assert config.name == "openai"
    assert config.api_key == "test-key"
    assert config.base_url.endswith("/v1")
    assert config.model == "gpt-test"
    assert ai_provider.auth_headers(config)["Authorization"] == "Bearer test-key"


def test_provider_config_for_ollama_compatible_llama(monkeypatch):
    monkeypatch.setattr(ai_provider.settings, "ai_provider", "llama")
    monkeypatch.setattr(ai_provider.settings, "llama_api_key", "")
    monkeypatch.setattr(ai_provider.settings, "llama_base_url", "http://localhost:11434/v1")
    monkeypatch.setattr(ai_provider.settings, "llama_model", "Llama-test")

    config = ai_provider.get_provider_config()

    assert config.name == "llama"
    assert config.api_key == ""
    assert config.base_url.endswith("/v1")
    assert config.model == "Llama-test"
    assert "Authorization" not in ai_provider.auth_headers(config)


def test_provider_config_for_mock(monkeypatch):
    monkeypatch.setattr(ai_provider.settings, "ai_provider", "mock")

    config = ai_provider.get_provider_config()

    assert config.name == "mock"
    assert config.model == "mock"
    assert ai_provider.auth_headers(config) == {"Content-Type": "application/json"}


def test_unknown_provider_fails_closed(monkeypatch):
    monkeypatch.setattr(ai_provider.settings, "ai_provider", "unknown")

    try:
        ai_provider.get_provider_config()
    except RuntimeError as exc:
        assert str(exc) == "AI provider is not configured"
    else:
        raise AssertionError("Unknown providers must fail closed")
