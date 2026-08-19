import asyncio

import pytest

from app.core.config import settings
from app.services.ai_service import stream_ai_reply_from_history


def test_mock_streaming_returns_complete_reply():
    async def collect():
        return [
            chunk
            async for chunk in stream_ai_reply_from_history(
                [{"role": "user", "content": "halo"}]
            )
        ]

    old_provider = settings.ai_provider
    settings.ai_provider = "mock"
    try:
        chunks = asyncio.run(collect())
        assert "halo" in "".join(chunks).lower()
        assert len(chunks) > 1
    finally:
        settings.ai_provider = old_provider


def test_streaming_rejects_unknown_provider():
    async def consume():
        async for _ in stream_ai_reply_from_history(
            [{"role": "user", "content": "halo"}]
        ):
            pass

    old_provider = settings.ai_provider
    settings.ai_provider = "unknown"
    try:
        with pytest.raises(RuntimeError, match="not configured"):
            asyncio.run(consume())
    finally:
        settings.ai_provider = old_provider
