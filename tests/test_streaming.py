import pytest

from app.core.config import settings
from app.services.ai_service import stream_ai_reply_from_history


@pytest.mark.asyncio
async def test_mock_streaming_returns_complete_reply():
    old_provider = settings.ai_provider
    settings.ai_provider = "mock"
    try:
        chunks = [
            chunk
            async for chunk in stream_ai_reply_from_history(
                [{"role": "user", "content": "halo"}]
            )
        ]
        assert "halo" in "".join(chunks).lower()
        assert len(chunks) > 1
    finally:
        settings.ai_provider = old_provider


@pytest.mark.asyncio
async def test_streaming_rejects_unknown_provider():
    old_provider = settings.ai_provider
    settings.ai_provider = "unknown"
    try:
        with pytest.raises(RuntimeError, match="not configured"):
            async for _ in stream_ai_reply_from_history(
                [{"role": "user", "content": "halo"}]
            ):
                pass
    finally:
        settings.ai_provider = old_provider
