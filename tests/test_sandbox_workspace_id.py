"""The sandbox workspace id ends up inside a URL path, so it must be constrained.

httpx normalises dot segments when it builds a URL, which means an id such as
``../../v1/admin`` addresses a completely different sandbox endpoint while still
carrying the operator's bearer token. ``?`` and ``#`` truncate the path in the
same way. No tool exposes ``workspace_id`` in its JSON schema today, so this is
not reachable from a model right now, but the plumbing accepts one and these
tests keep it safe if it is ever surfaced.
"""

from __future__ import annotations

import httpx
import pytest

from app.services.sandbox_client import SandboxClient
from app.tools.providers import ToolProviderError
from app.tools.terminal_safety import TerminalSafetyError, validate_workspace_id

TRAVERSAL_IDS = [
    "../../v1/admin",
    "abc/../../secret",
    "abc?x=1",
    "abc#frag",
    "..%2f..%2fadmin",
    "a" * 65,
    "",
    "   ",
    "has space",
    "semi;colon",
]


@pytest.fixture
def client(monkeypatch) -> SandboxClient:
    return SandboxClient(base_url="http://sandbox.test", token="token")


@pytest.mark.parametrize("workspace_id", TRAVERSAL_IDS)
def test_validate_workspace_id_rejects_hostile_values(workspace_id):
    with pytest.raises(TerminalSafetyError):
        validate_workspace_id(workspace_id)


@pytest.mark.parametrize("workspace_id", ["abc", "ws-123", "A_b-9", "a" * 64])
def test_validate_workspace_id_accepts_plain_identifiers(workspace_id):
    assert validate_workspace_id(workspace_id) == workspace_id


def test_traversal_id_would_have_escaped_the_workspace_namespace():
    """Documents the concrete failure mode the validation prevents."""
    url = httpx.URL("http://sandbox.test/v1/workspaces/../../v1/admin/execute")
    assert url.path == "/v1/admin/execute"


@pytest.mark.parametrize("workspace_id", TRAVERSAL_IDS)
def test_execute_refuses_a_hostile_workspace_id(client, workspace_id, monkeypatch):
    def fail(*args, **kwargs):
        raise AssertionError("no request may be sent for a rejected workspace id")

    monkeypatch.setattr(httpx, "post", fail)
    with pytest.raises(ToolProviderError, match="Invalid sandbox workspace id"):
        client.execute(workspace_id=workspace_id, command="echo hi")


@pytest.mark.parametrize("workspace_id", TRAVERSAL_IDS)
def test_delete_refuses_a_hostile_workspace_id(client, workspace_id, monkeypatch):
    def fail(*args, **kwargs):
        raise AssertionError("no request may be sent for a rejected workspace id")

    monkeypatch.setattr(httpx, "delete", fail)
    with pytest.raises(ToolProviderError, match="Invalid sandbox workspace id"):
        client.delete_workspace(workspace_id)


def test_create_workspace_rejects_a_hostile_id_from_the_sandbox(client, monkeypatch):
    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {"workspace_id": "../../v1/admin"}

    monkeypatch.setattr(httpx, "post", lambda *a, **k: Response())
    with pytest.raises(ToolProviderError, match="Invalid sandbox workspace id"):
        client.create_workspace()


def test_execute_clamps_the_timeout(client, monkeypatch):
    captured: dict = {}

    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {"exit_code": 0}

    def capture(url, headers=None, json=None, timeout=None):
        captured["body"] = json
        captured["timeout"] = timeout
        return Response()

    monkeypatch.setattr(httpx, "post", capture)

    client.execute(workspace_id="ws-1", command="echo hi", timeout=-5)
    assert captured["body"]["timeout"] == 1
    assert captured["timeout"] == 6

    client.execute(workspace_id="ws-1", command="echo hi", timeout=9000)
    assert captured["body"]["timeout"] == 60
    assert captured["timeout"] == 65
