import os

os.environ["SANDBOX_SERVICE_TOKEN"] = "test-token"

from fastapi.testclient import TestClient

from app import app, create_workspace

client = TestClient(app)


def auth() -> dict[str, str]:
    return {"Authorization": "Bearer test-token"}


def test_health_is_public() -> None:
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_workspace_requires_authentication() -> None:
    response = client.post("/v1/workspaces")
    assert response.status_code == 401


def test_command_rejects_shell_operators() -> None:
    workspace = create_workspace().workspace_id
    response = client.post(
        f"/v1/workspaces/{workspace}/execute",
        headers=auth(),
        json={"command": "python -c 'print(1)' && whoami"},
    )
    assert response.status_code == 400
    assert "shell operators" in response.json()["detail"]


def test_cwd_cannot_escape_workspace() -> None:
    workspace = create_workspace().workspace_id
    response = client.post(
        f"/v1/workspaces/{workspace}/execute",
        headers=auth(),
        json={"command": "python --version", "cwd": "../"},
    )
    assert response.status_code == 400
    assert "cwd must stay inside workspace" in response.json()["detail"]


def test_unknown_workspace_is_rejected() -> None:
    response = client.post(
        "/v1/workspaces/00000000000000000000000000000000/execute",
        headers=auth(),
        json={"command": "python --version"},
    )
    assert response.status_code == 404
