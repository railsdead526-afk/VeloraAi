from __future__ import annotations

import httpx
import pytest

from app.services.sandbox_client import SandboxClient
from app.tools.providers import ToolProviderError


class FakeResponse:
    def __init__(self, payload: object, status_code: int = 200) -> None:
        self._payload = payload
        self.status_code = status_code

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("error", request=httpx.Request("POST", "http://sandbox"), response=httpx.Response(self.status_code))

    def json(self) -> object:
        return self._payload


def test_client_requires_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TERMINAL_SANDBOX_URL", raising=False)
    monkeypatch.delenv("TERMINAL_SANDBOX_TOKEN", raising=False)
    with pytest.raises(ToolProviderError, match="not configured"):
        SandboxClient()


def test_create_workspace_uses_v1_endpoint_and_bearer(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    def fake_post(url: str, **kwargs: object) -> FakeResponse:
        captured.update(url=url, **kwargs)
        return FakeResponse({"workspace_id": "a" * 32})

    monkeypatch.setattr(httpx, "post", fake_post)
    client = SandboxClient(base_url="http://sandbox/", token="secret")

    assert client.create_workspace() == "a" * 32
    assert captured["url"] == "http://sandbox/v1/workspaces"
    assert captured["headers"] == {
        "Authorization": "Bearer secret",
        "Content-Type": "application/json",
    }


def test_execute_caps_timeout_and_uses_workspace_route(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    def fake_post(url: str, **kwargs: object) -> FakeResponse:
        captured.update(url=url, **kwargs)
        return FakeResponse({"exit_code": 0, "stdout": "ok", "stderr": ""})

    monkeypatch.setattr(httpx, "post", fake_post)
    client = SandboxClient(base_url="http://sandbox", token="secret")

    result = client.execute(workspace_id="b" * 32, command="python --version", cwd="src", timeout=999)

    assert result["exit_code"] == 0
    assert captured["url"] == f"http://sandbox/v1/workspaces/{'b' * 32}/execute"
    assert captured["json"] == {"command": "python --version", "cwd": "src", "timeout": 60}
    assert captured["timeout"] == 65


def test_malformed_workspace_response_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(httpx, "post", lambda *args, **kwargs: FakeResponse({"workspace_id": 123}))
    client = SandboxClient(base_url="http://sandbox", token="secret")

    with pytest.raises(ToolProviderError, match="invalid workspace"):
        client.create_workspace()
