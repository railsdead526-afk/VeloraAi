from app.core.config import settings
from app.services.ai_service import _build_api_messages, generate_ai_reply_from_history


def test_mock_ai_reply_uses_conversation_context():
    old_provider = settings.ai_provider
    settings.ai_provider = "mock"
    try:
        reply = generate_ai_reply_from_history(
            [
                {"role": "user", "content": "Halo"},
                {"role": "assistant", "content": "Hai"},
                {"role": "user", "content": "Pesan pertama saya apa?"},
            ]
        )
        assert reply == "Pesan pertama kamu adalah: Halo"
    finally:
        settings.ai_provider = old_provider


def test_ai_context_is_bounded():
    old_limit = settings.ai_max_history_messages
    settings.ai_max_history_messages = 2
    try:
        messages = _build_api_messages(
            [
                {"role": "user", "content": "one"},
                {"role": "assistant", "content": "two"},
                {"role": "user", "content": "three"},
            ]
        )
        assert [item["content"] for item in messages[1:]] == ["two", "three"]
    finally:
        settings.ai_max_history_messages = old_limit
