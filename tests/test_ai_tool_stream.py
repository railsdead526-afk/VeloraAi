import json

import pytest

from app.services.ai_tool_stream import stream_ai_reply_with_tools
from app.services.tool_confirmation import create_confirmation_token
from app.tools.base import ToolDefinition
from app.tools.registry import ToolRegistry


def _sse(payload):
    return "data: " + json.dumps(payload)


@pytest.mark.asyncio
async def test_native_stream_emits_tokens_and_done_for_mock_provider(monkeypatch):
    monkeypatch.setattr("app.services.ai_tool_stream.settings.ai_provider", "mock")

    events = [
        event
        async for event in stream_ai_reply_with_tools(
            [{"role": "user", "content": "halo"}],
            plan="free",
            confirmed=False,
            registry=ToolRegistry(),
        )
    ]

    assert any(event.type == "token" for event in events)
    assert events[-1].type == "done"
    assert events[-1].model == "mock"


class _FakeResponse:
    status_code = 200

    def __init__(self, lines):
        self._lines = lines

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def aread(self):
        return b""

    def raise_for_status(self):
        return None

    async def aiter_lines(self):
        for line in self._lines:
            yield line


class _FakeClient:
    def __init__(self, responses):
        self.responses = responses
        self.index = 0

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    def stream(self, *args, **kwargs):
        response = _FakeResponse(self.responses[self.index])
        self.index += 1
        return response


@pytest.mark.asyncio
async def test_native_stream_handles_multi_round_tool_call(monkeypatch):
    monkeypatch.setattr("app.services.ai_tool_stream.settings.ai_provider", "llama")
    monkeypatch.setattr("app.services.ai_tool_stream.settings.llama_api_key", "test-key")
    monkeypatch.setattr("app.services.ai_tool_stream.settings.llama_base_url", "https://llama.test")
    monkeypatch.setattr("app.services.ai_tool_stream.settings.llama_model", "test-model")
    monkeypatch.setattr("app.services.ai_tool_stream.select_tools", lambda tools, *_args, **_kwargs: list(tools))

    registry = ToolRegistry()
    calls = []

    def handler(arguments):
        calls.append(arguments)
        return {"repositories": ["VeloraAi"]}

    registry.register(
        ToolDefinition(
            name="github_list_repositories",
            description="List GitHub repositories",
            handler=handler,
            allowed_plans=frozenset({"free", "pro", "max", "admin"}),
            parameters={
                "type": "object",
                "properties": {"limit": {"type": "integer"}},
                "additionalProperties": False,
            },
        )
    )

    first_delta = {
        "choices": [{"delta": {"tool_calls": [{
            "index": 0,
            "id": "call-1",
            "function": {"name": "github_list_repositories", "arguments": '{"lim'},
        }]}}]
    }
    second_delta = {
        "choices": [{"delta": {"tool_calls": [{
            "index": 0,
            "function": {"arguments": 'it": 1}'},
        }]}}]
    }
    first_round = [_sse(first_delta), _sse(second_delta), "data: [DONE]"]
    second_round = [
        _sse({"choices": [{"delta": {"content": "Found VeloraAi."}}]}),
        _sse({"usage": {"prompt_tokens": 10, "completion_tokens": 4}}),
        "data: [DONE]",
    ]

    fake_client = _FakeClient([first_round, second_round])
    monkeypatch.setattr("app.services.ai_tool_stream.httpx.AsyncClient", lambda *args, **kwargs: fake_client)

    events = [
        event
        async for event in stream_ai_reply_with_tools(
            [{"role": "user", "content": "list my github repositories"}],
            plan="free",
            confirmed=False,
            registry=registry,
        )
    ]

    assert calls == [{"limit": 1}]
    assert [event.type for event in events] == ["tool_start", "tool_end", "token", "done"]
    assert events[-1].input_tokens == 10
    assert events[-1].output_tokens == 4


@pytest.mark.asyncio
async def test_native_stream_emits_confirmation_required_without_execution(monkeypatch):
    monkeypatch.setattr("app.services.ai_tool_stream.settings.ai_provider", "llama")
    monkeypatch.setattr("app.services.ai_tool_stream.settings.llama_api_key", "test-key")
    monkeypatch.setattr("app.services.ai_tool_stream.settings.llama_base_url", "https://llama.test")
    monkeypatch.setattr("app.services.ai_tool_stream.settings.llama_model", "test-model")
    monkeypatch.setattr("app.services.ai_tool_stream.select_tools", lambda tools, *_args, **_kwargs: list(tools))

    registry = ToolRegistry()
    executed = []

    registry.register(
        ToolDefinition(
            name="dangerous_write",
            description="Write something important",
            handler=lambda arguments: executed.append(arguments),
            allowed_plans=frozenset({"pro", "max", "admin"}),
            requires_confirmation=True,
        )
    )

    tool_request = {
        "choices": [{"delta": {"tool_calls": [{
            "index": 0,
            "id": "call-2",
            "function": {"name": "dangerous_write", "arguments": "{}"},
        }]}}]
    }
    response_lines = [_sse(tool_request), "data: [DONE]"]
    fake_client = _FakeClient([response_lines])
    monkeypatch.setattr("app.services.ai_tool_stream.httpx.AsyncClient", lambda *args, **kwargs: fake_client)

    events = [
        event
        async for event in stream_ai_reply_with_tools(
            [{"role": "user", "content": "write something"}],
            plan="pro",
            confirmed=False,
            registry=registry,
            user_id=42,
            conversation_id=7,
        )
    ]

    assert executed == []
    confirmation = next(event for event in events if event.type == "tool_confirmation_required")
    assert confirmation.confirmation_token
    assert events[-1].type == "tool_end"


@pytest.mark.asyncio
async def test_native_stream_accepts_only_matching_confirmation_token(monkeypatch):
    monkeypatch.setattr("app.services.ai_tool_stream.settings.ai_provider", "llama")
    monkeypatch.setattr("app.services.ai_tool_stream.settings.llama_api_key", "test-key")
    monkeypatch.setattr("app.services.ai_tool_stream.settings.llama_base_url", "https://llama.test")
    monkeypatch.setattr("app.services.ai_tool_stream.settings.llama_model", "test-model")
    monkeypatch.setattr("app.services.ai_tool_stream.select_tools", lambda tools, *_args, **_kwargs: list(tools))

    registry = ToolRegistry()
    executed = []
    registry.register(
        ToolDefinition(
            name="dangerous_write",
            description="Write something important",
            handler=lambda arguments: executed.append(arguments) or {"ok": True},
            allowed_plans=frozenset({"pro", "max", "admin"}),
            requires_confirmation=True,
        )
    )

    tool_request = {
        "choices": [{"delta": {"tool_calls": [{
            "index": 0,
            "id": "call-3",
            "function": {"name": "dangerous_write", "arguments": '{"value":"approved"}'},
        }]}}]
    }
    final_round = [
        _sse({"choices": [{"delta": {"content": "Done."}}]}),
        _sse({"usage": {"prompt_tokens": 8, "completion_tokens": 2}}),
        "data: [DONE]",
    ]
    first_client = _FakeClient([[ _sse(tool_request), "data: [DONE]" ]])
    monkeypatch.setattr("app.services.ai_tool_stream.httpx.AsyncClient", lambda *args, **kwargs: first_client)

    events = [
        event
        async for event in stream_ai_reply_with_tools(
            [{"role": "user", "content": "write approved"}],
            plan="pro",
            confirmed=False,
            registry=registry,
            user_id=42,
            conversation_id=7,
        )
    ]
    token = next(event.confirmation_token for event in events if event.type == "tool_confirmation_required")

    second_client = _FakeClient([final_round])
    monkeypatch.setattr("app.services.ai_tool_stream.httpx.AsyncClient", lambda *args, **kwargs: second_client)
    resumed = [
        event
        async for event in stream_ai_reply_with_tools(
            [{"role": "user", "content": "write approved"}],
            plan="pro",
            confirmed=False,
            registry=registry,
            user_id=42,
            conversation_id=7,
            approved_confirmation_token=token,
        )
    ]

    assert executed == [{"value": "approved"}]
    assert resumed[-1].type == "done"

    mismatched_client = _FakeClient([[ _sse(tool_request), "data: [DONE]" ]])
    monkeypatch.setattr("app.services.ai_tool_stream.httpx.AsyncClient", lambda *args, **kwargs: mismatched_client)
    mismatched = [
        event
        async for event in stream_ai_reply_with_tools(
            [{"role": "user", "content": "write approved"}],
            plan="pro",
            confirmed=False,
            registry=registry,
            user_id=42,
            conversation_id=8,
            approved_confirmation_token=token,
        )
    ]
    assert len(executed) == 1
    assert any(event.type == "tool_confirmation_required" for event in mismatched)
