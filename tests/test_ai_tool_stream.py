import pytest

from app.services.ai_tool_stream import stream_ai_reply_with_tools
from app.tools.bootstrap import get_registry


@pytest.mark.asyncio
async def test_native_stream_emits_tokens_and_done_for_mock_provider(monkeypatch):
    monkeypatch.setattr("app.services.ai_tool_stream.settings.ai_provider", "mock")

    events = [
        event
        async for event in stream_ai_reply_with_tools(
            [{"role": "user", "content": "halo"}],
            plan="free",
            confirmed=False,
            registry=get_registry(),
        )
    ]

    assert any(event.type == "token" for event in events)
    assert events[-1].type == "done"
    assert events[-1].model == "mock"
