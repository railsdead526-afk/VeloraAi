from app.services import ai_provider


def test_provider_config_for_gemini(monkeypatch):
    monkeypatch.setattr(ai_provider.settings, "ai_provider", "gemini")
    monkeypatch.setattr(ai_provider.settings, "gemini_api_key", "test-key")
    monkeypatch.setattr(
        ai_provider.settings,
        "gemini_base_url",
        "https://generativelanguage.googleapis.com/v1beta/openai",
    )
    monkeypatch.setattr(ai_provider.settings, "gemini_model", "gemini-1.5-flash")

    config = ai_provider.get_provider_config()

    assert config.name == "gemini"
    assert config.api_key == "test-key"
    assert config.base_url.endswith("/openai")
    assert config.model == "gemini-1.5-flash"
    assert ai_provider.auth_headers(config)["Authorization"] == "Bearer test-key"
    assert "gemini" in ai_provider.SUPPORTED_PROVIDERS