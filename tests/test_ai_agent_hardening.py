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


def test_sync_provider_retry_uses_configured_budget(monkeypatch):
    attempts = {"count": 0}
    monkeypatch.setattr(ai_tool_loop.settings, "ai_max_retries", 2)

    class Client:
        def post(self, *args, **kwargs):
            attempts["count"] += 1
            if attempts["count"] < 3:
                raise httpx.ConnectError("temporary")
            return FakeResponse()

    result = ai_tool_loop._post_completion_sync(
        Client(), "https://example.test/chat/completions", headers={}, payload={}
    )
    assert result["choices"][0]["message"]["content"] == "ok"
    assert attempts["count"] == 3


def test_async_provider_retry_does_not_retry_non_retryable_4xx(monkeypatch):
    attempts = {"count": 0}
    monkeypatch.setattr(ai_tool_loop.settings, "ai_max_retries", 3)

    class Client:
        async def post(self, *args, **kwargs):
            attempts["count"] += 1
            return FakeResponse(status_code=400)

    async def run():
        with pytest.raises(httpx.HTTPStatusError):
            await ai_tool_loop._post_completion_async(
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
            await ai_tool_loop._post_completion_async(
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
