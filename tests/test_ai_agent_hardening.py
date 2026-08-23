import asyncio
import json

import httpx
import pytest

from app.services import ai_tool_loop
from app.tools.base import ToolDefinition
from app.tools.registry import ToolRegistry


class FakeResponse:
    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self._payload = payload or {"choices": [{"message": {"content": "ok"}}]}

    def raise_for_status(self):
        if self.status_code >= 400:
            request = httpx.Request("POST", "https://example.test/chat/completions")
            response = httpx.Response(self.status_code, request=request)
            raise httpx.HTTPStatusError("http error", request=request, response=response)

    def json(self):
        return self._payload


def _no_sleep(monkeypatch):
    async def fake_sleep(_seconds):
        return None

    monkeypatch.setattr(ai_tool_loop.asyncio, "sleep", fake_sleep)


def test_provider_retry_uses_configured_budget(monkeypatch):
    attempts = {"count": 0}
    monkeypatch.setattr(ai_tool_loop.settings, "ai_max_retries", 2)
    _no_sleep(monkeypatch)

    class Client:
        async def post(self, *args, **kwargs):
            attempts["count"] += 1
            if attempts["count"] < 3:
                raise httpx.ConnectError("temporary")
            return FakeResponse()

    async def run():
        return await ai_tool_loop._post_completion(
            Client(), "https://example.test/chat/completions", headers={}, payload={}
        )

    result = asyncio.run(run())
    assert result["choices"][0]["message"]["content"] == "ok"
    assert attempts["count"] == 3


def test_provider_retry_waits_between_attempts(monkeypatch):
    """The synchronous path used to retry with no delay at all, hammering a 429."""
    delays: list[float] = []
    monkeypatch.setattr(ai_tool_loop.settings, "ai_max_retries", 2)

    async def fake_sleep(seconds):
        delays.append(seconds)

    monkeypatch.setattr(ai_tool_loop.asyncio, "sleep", fake_sleep)

    class Client:
        def __init__(self):
            self.calls = 0

        async def post(self, *args, **kwargs):
            self.calls += 1
            if self.calls < 3:
                raise httpx.ConnectError("temporary")
            return FakeResponse()

    async def run():
        return await ai_tool_loop._post_completion(
            Client(), "https://example.test/chat/completions", headers={}, payload={}
        )

    asyncio.run(run())
    assert delays == [1.0, 2.0]


def test_provider_retry_honours_retry_after_header(monkeypatch):
    monkeypatch.setattr(ai_tool_loop.settings, "ai_max_retries", 1)
    request = httpx.Request("POST", "https://example.test/chat/completions")
    response = httpx.Response(429, request=request, headers={"Retry-After": "3"})
    exc = httpx.HTTPStatusError("rate limited", request=request, response=response)
    assert ai_tool_loop._retry_delay(0, exc) == 3.0


def test_provider_retry_ignores_absurd_retry_after(monkeypatch):
    request = httpx.Request("POST", "https://example.test/chat/completions")
    response = httpx.Response(429, request=request, headers={"Retry-After": "600"})
    exc = httpx.HTTPStatusError("rate limited", request=request, response=response)
    assert ai_tool_loop._retry_delay(0, exc) == 1.0


def test_async_provider_retry_does_not_retry_non_retryable_4xx(monkeypatch):
    attempts = {"count": 0}
    monkeypatch.setattr(ai_tool_loop.settings, "ai_max_retries", 3)

    class Client:
        async def post(self, *args, **kwargs):
            attempts["count"] += 1
            return FakeResponse(status_code=400)

    async def run():
        with pytest.raises(httpx.HTTPStatusError):
            await ai_tool_loop._post_completion(
                Client(), "https://example.test/chat/completions", headers={}, payload={}
            )

    asyncio.run(run())
    assert attempts["count"] == 1


def test_async_provider_cancellation_is_not_swallowed():
    class Client:
        async def post(self, *args, **kwargs):
            raise asyncio.CancelledError()

    async def run():
        with pytest.raises(asyncio.CancelledError):
            await ai_tool_loop._post_completion(
                Client(), "https://example.test/chat/completions", headers={}, payload={}
            )

    asyncio.run(run())


def test_async_tool_loop_exhausts_round_budget(monkeypatch):
    monkeypatch.setattr(ai_tool_loop.settings, "ai_provider", "openai")
    monkeypatch.setattr(ai_tool_loop.settings, "openai_api_key", "test-key")
    monkeypatch.setattr(ai_tool_loop.settings, "openai_base_url", "https://example.test/v1")

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

    payload = {
        "choices": [
            {
                "message": {
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "call-1",
                            "function": {"name": "echo", "arguments": json.dumps({})},
                        }
                    ],
                }
            }
        ],
        "usage": {"prompt_tokens": 1, "completion_tokens": 1},
    }

    class Client:
        async def post(self, *args, **kwargs):
            return FakeResponse(payload=payload)

    monkeypatch.setattr(httpx, "AsyncClient", lambda *args, **kwargs: _AsyncClientContext(Client()))

    async def run():
        with pytest.raises(RuntimeError, match="maximum number of rounds"):
            await ai_tool_loop.generate_ai_reply_with_tools_async(
                [{"role": "user", "content": "use echo"}],
                plan="pro",
                registry=registry,
            )

    asyncio.run(run())


class _AsyncClientContext:
    def __init__(self, client):
        self.client = client

    async def __aenter__(self):
        return self.client

    async def __aexit__(self, exc_type, exc, tb):
        return False
