import asyncio

import httpx
import pytest

from app.services import ai_tool_loop


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

    result = ai_tool_loop._post_completion_sync(Client(), "https://example.test/chat/completions", headers={}, payload={})
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
            await ai_tool_loop._post_completion_async(Client(), "https://example.test/chat/completions", headers={}, payload={})

    asyncio.run(run())
    assert attempts["count"] == 1
