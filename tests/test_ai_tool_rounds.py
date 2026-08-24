"""Regression tests for the multi-round tool loop.

Each test here pins down a bug that used to cost either money or correctness:

* the loop gave up with a 500 after the round budget ran out, discarding every
  token already paid for;
* a retried streaming round concatenated its partial tool-call arguments onto the
  ones collected by the aborted attempt, producing invalid JSON;
* a retried streaming round billed the usage reported by the failed attempt.
"""

from __future__ import annotations

import asyncio
import json

import httpx
import pytest

from app.services import ai_tool_loop, ai_tool_stream
from app.tools.base import ToolDefinition
from app.tools.registry import ToolRegistry


@pytest.fixture
def echo_registry() -> ToolRegistry:
    registry = ToolRegistry()
    registry.register(
        ToolDefinition(
            name="echo",
            description="Echo",
            handler=lambda arguments: {"ok": True},
            allowed_plans=frozenset({"pro"}),
            parameters={"type": "object", "additionalProperties": True},
            timeout_seconds=5,
            max_calls_per_request=10,
        )
    )
    return registry


@pytest.fixture(autouse=True)
def openai_provider(monkeypatch):
    monkeypatch.setattr(ai_tool_loop.settings, "ai_provider", "openai")
    monkeypatch.setattr(ai_tool_loop.settings, "openai_api_key", "test-key")
    monkeypatch.setattr(ai_tool_loop.settings, "openai_base_url", "https://example.test/v1")


class _AsyncClientContext:
    def __init__(self, client):
        self.client = client

    async def __aenter__(self):
        return self.client

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _Response:
    def __init__(self, payload):
        self._payload = payload
        self.status_code = 200

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


def _tool_call_payload() -> dict:
    return {
        "choices": [
            {
                "message": {
                    "content": None,
                    "tool_calls": [
                        {"id": "call-1", "function": {"name": "echo", "arguments": "{}"}}
                    ],
                }
            }
        ],
        "usage": {"prompt_tokens": 1, "completion_tokens": 1},
    }


def test_final_round_drops_tools_and_returns_an_answer(monkeypatch, echo_registry):
    """A model stuck in a tool loop must still produce a reply, not a 500."""
    payloads: list[dict] = []

    class Client:
        async def post(self, url, headers=None, json=None):
            payloads.append(json)
            if len(payloads) < ai_tool_loop.MAX_TOOL_ROUNDS:
                return _Response(_tool_call_payload())
            return _Response(
                {
                    "choices": [{"message": {"content": "jawaban akhir"}}],
                    "usage": {"prompt_tokens": 5, "completion_tokens": 7},
                }
            )

    monkeypatch.setattr(httpx, "AsyncClient", lambda *a, **k: _AsyncClientContext(Client()))

    result = asyncio.run(
        ai_tool_loop.generate_ai_reply_with_tools_async(
            [{"role": "user", "content": "use echo"}], plan="pro", registry=echo_registry
        )
    )

    assert result.content == "jawaban akhir"
    assert len(payloads) == ai_tool_loop.MAX_TOOL_ROUNDS
    # Every round but the last offers tools; the last withholds them entirely.
    assert all("tools" in payload for payload in payloads[:-1])
    assert "tools" not in payloads[-1]
    assert "tool_choice" not in payloads[-1]
    # Usage from every round is billed, not just the last one.
    assert result.input_tokens == 1 * (ai_tool_loop.MAX_TOOL_ROUNDS - 1) + 5


def test_sync_wrapper_refuses_to_run_inside_an_event_loop(echo_registry):
    async def run():
        with pytest.raises(RuntimeError, match="cannot be called from an event loop"):
            ai_tool_loop.generate_ai_reply_with_tools(
                [{"role": "user", "content": "hi"}], plan="pro", registry=echo_registry
            )

    asyncio.run(run())


def test_sync_wrapper_shares_the_async_implementation(monkeypatch, echo_registry):
    class Client:
        async def post(self, url, headers=None, json=None):
            return _Response(
                {
                    "choices": [{"message": {"content": "halo"}}],
                    "usage": {"prompt_tokens": 2, "completion_tokens": 3},
                }
            )

    monkeypatch.setattr(httpx, "AsyncClient", lambda *a, **k: _AsyncClientContext(Client()))

    result = ai_tool_loop.generate_ai_reply_with_tools(
        [{"role": "user", "content": "hi"}], plan="pro", registry=echo_registry
    )
    assert result.content == "halo"
    assert (result.input_tokens, result.output_tokens) == (2, 3)


class _StreamContext:
    def __init__(self, lines, status_code=200, fail_after=None):
        self._lines = lines
        self.status_code = status_code
        self._fail_after = fail_after

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    def raise_for_status(self):
        return None

    async def aread(self):
        return b""

    async def aiter_lines(self):
        for index, line in enumerate(self._lines):
            if self._fail_after is not None and index == self._fail_after:
                raise httpx.RemoteProtocolError("connection dropped")
            yield line


def _delta_line(**delta) -> str:
    return "data: " + json.dumps({"choices": [{"delta": delta}]})


def _tool_delta(index, *, call_id=None, name=None, arguments=None) -> str:
    function: dict = {}
    if name is not None:
        function["name"] = name
    if arguments is not None:
        function["arguments"] = arguments
    call: dict = {"index": index, "function": function}
    if call_id is not None:
        call["id"] = call_id
    return _delta_line(tool_calls=[call])


def test_streaming_retry_does_not_corrupt_tool_arguments(monkeypatch, echo_registry):
    """A dropped stream must not glue two partial argument strings together."""
    monkeypatch.setattr(ai_tool_stream.settings, "ai_provider", "openai")
    monkeypatch.setattr(ai_tool_stream.settings, "openai_api_key", "test-key")
    monkeypatch.setattr(ai_tool_stream.settings, "openai_base_url", "https://example.test/v1")
    monkeypatch.setattr(ai_tool_stream.settings, "ai_max_retries", 1)

    async def no_sleep(_attempt):
        return None

    monkeypatch.setattr(ai_tool_stream, "_backoff", no_sleep)

    executed: list[dict] = []

    async def fake_execute_tool(registry, *, name, arguments, plan, confirmed, call_counts):
        executed.append(arguments)
        return {"ok": True}

    monkeypatch.setattr(ai_tool_stream, "execute_tool", fake_execute_tool)

    first_attempt = [
        _tool_delta(0, call_id="call-1", name="echo"),
        _tool_delta(0, arguments='{"value":'),
        "data: never reached",
    ]
    second_attempt = [
        _tool_delta(0, call_id="call-1", name="echo"),
        _tool_delta(0, arguments='{"value":'),
        _tool_delta(0, arguments=' "halo"}'),
        'data: {"usage": {"prompt_tokens": 4, "completion_tokens": 6}}',
        "data: [DONE]",
    ]
    final_round = [
        _delta_line(content="selesai"),
        'data: {"usage": {"prompt_tokens": 1, "completion_tokens": 1}}',
        "data: [DONE]",
    ]
    streams = [
        _StreamContext(first_attempt, fail_after=2),
        _StreamContext(second_attempt),
        _StreamContext(final_round),
    ]

    class Client:
        def stream(self, method, url, headers=None, json=None):
            return streams.pop(0)

    monkeypatch.setattr(httpx, "AsyncClient", lambda *a, **k: _AsyncClientContext(Client()))

    async def run():
        return [
            event
            async for event in ai_tool_stream.stream_ai_reply_with_tools(
                [{"role": "user", "content": "use echo"}],
                plan="pro",
                confirmed=True,
                registry=echo_registry,
            )
        ]

    events = asyncio.run(run())

    # The retried attempt parsed cleanly instead of producing '{"value":{"value": "halo"}'.
    assert executed == [{"value": "halo"}]
    done = [event for event in events if event.type == "done"]
    assert len(done) == 1
    # Tokens reported by the aborted attempt are not billed twice.
    assert done[0].input_tokens == 5
    assert done[0].output_tokens == 7
