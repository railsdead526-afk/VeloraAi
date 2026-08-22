import httpx
import pytest

from app.tools.providers import ToolProviderError, _request


def test_provider_error_does_not_echo_secret(monkeypatch):
    secret = "super-secret-token-123456"

    def fail_request(*args, **kwargs):
        request = httpx.Request("GET", "https://example.test")
        response = httpx.Response(401, request=request, text=f"invalid token {secret}")
        raise httpx.HTTPStatusError("provider rejected request", request=request, response=response)

    monkeypatch.setattr(httpx, "request", fail_request)

    with pytest.raises(ToolProviderError) as exc_info:
        _request("GET", "https://example.test", token=secret)

    assert str(exc_info.value) == "External provider request failed"
    assert secret not in str(exc_info.value)


def test_provider_token_is_not_returned_in_success_payload(monkeypatch):
    secret = "super-secret-token-abcdef"

    def fake_request(method, url, headers, json, timeout):
        assert headers["Authorization"] == f"Bearer {secret}"
        return httpx.Response(200, request=httpx.Request(method, url), json={"ok": True})

    monkeypatch.setattr(httpx, "request", fake_request)

    result = _request("GET", "https://example.test", token=secret)

    assert result == {"ok": True}
    assert secret not in repr(result)
