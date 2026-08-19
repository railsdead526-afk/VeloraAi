import pytest

from app.core.config import settings
from app.services.ai_service import stream_ai_reply_from_history


@pytest.mark.asyncio
async def test_mock_stream_populates_usage_sink():
    old_provider = settings.ai_provider
    settings.ai_provider = "mock"
    try:
        usage = {}
        chunks = [
            chunk async for chunk in stream_ai_reply_from_history(
                [{"role": "user", "content": "Halo"}],
                usage,
            )
        ]
        assert "".join(chunks)
        assert usage["model"] == "mock"
        assert usage["input_tokens"] is not None
        assert usage["output_tokens"] is not None
        assert usage["input_tokens"] >= 0
        assert usage["output_tokens"] >= 0
    finally:
        settings.ai_provider = old_provider
