from __future__ import annotations

import os
from typing import Any

import httpx

from app.tools.providers import ToolProviderError


class SandboxClient:
    """Versioned client for the isolated sandbox control service."""

    def __init__(self, *, base_url: str | None = None, token: str | None = None) -> None:
        self.base_url = (base_url or os.getenv("TERMINAL_SANDBOX_URL", "")).rstrip("/")
        self.token = token or os.getenv("TERMINAL_SANDBOX_TOKEN", "")
        if not self.base_url or not self.token:
            raise ToolProviderError("Terminal sandbox is not configured")

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"}

    def create_workspace(self) -> str:
        try:
            response = httpx.post(
                f"{self.base_url}/v1/workspaces", headers=self._headers(), timeout=10
            )
            response.raise_for_status()
            payload = response.json()
            workspace_id = payload.get("workspace_id")
            if not isinstance(workspace_id, str) or not workspace_id:
                raise ToolProviderError("Sandbox returned an invalid workspace")
            return workspace_id
        except (httpx.HTTPError, ValueError) as exc:
            raise ToolProviderError("Sandbox workspace creation failed") from exc

    def delete_workspace(self, workspace_id: str) -> None:
        try:
            response = httpx.delete(
                f"{self.base_url}/v1/workspaces/{workspace_id}",
                headers=self._headers(),
                timeout=10,
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise ToolProviderError("Sandbox workspace deletion failed") from exc

    def execute(
        self,
        *,
        workspace_id: str,
        command: str,
        cwd: str | None = None,
        timeout: int = 30,
    ) -> dict[str, Any]:
        try:
            response = httpx.post(
                f"{self.base_url}/v1/workspaces/{workspace_id}/execute",
                headers=self._headers(),
                json={"command": command, "cwd": cwd, "timeout": min(timeout, 60)},
                timeout=min(timeout, 60) + 5,
            )
            response.raise_for_status()
            payload = response.json()
            if not isinstance(payload, dict):
                raise ToolProviderError("Sandbox returned an invalid execution response")
            return payload
        except (httpx.HTTPError, ValueError) as exc:
            raise ToolProviderError("Sandbox execution failed") from exc
