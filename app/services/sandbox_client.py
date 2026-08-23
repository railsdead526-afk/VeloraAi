from __future__ import annotations

import os
from typing import Any

import httpx

from app.tools.providers import ToolProviderError
from app.tools.terminal_safety import TerminalSafetyError, validate_workspace_id


class SandboxClient:
    """Versioned client for the isolated sandbox control service."""

    def __init__(self, *, base_url: str | None = None, token: str | None = None) -> None:
        resolved_url: str = base_url or os.getenv("TERMINAL_SANDBOX_URL") or ""
        self.base_url = resolved_url.rstrip("/")
        self.token: str = token or os.getenv("TERMINAL_SANDBOX_TOKEN") or ""
        if not self.base_url or not self.token:
            raise ToolProviderError("Terminal sandbox is not configured")

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"}

    @staticmethod
    def _safe_workspace_id(workspace_id: str) -> str:
        """Last line of defence before the id becomes part of a URL path."""
        try:
            return validate_workspace_id(str(workspace_id))
        except TerminalSafetyError as exc:
            raise ToolProviderError("Invalid sandbox workspace id") from exc

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
            return self._safe_workspace_id(workspace_id)
        except (httpx.HTTPError, ValueError) as exc:
            raise ToolProviderError("Sandbox workspace creation failed") from exc

    def delete_workspace(self, workspace_id: str) -> None:
        workspace_id = self._safe_workspace_id(workspace_id)
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
        workspace_id = self._safe_workspace_id(workspace_id)
        # A non-positive timeout would otherwise be handed straight to httpx.
        timeout = max(1, min(int(timeout), 60))
        try:
            response = httpx.post(
                f"{self.base_url}/v1/workspaces/{workspace_id}/execute",
                headers=self._headers(),
                json={"command": command, "cwd": cwd, "timeout": timeout},
                timeout=timeout + 5,
            )
            response.raise_for_status()
            payload = response.json()
            if not isinstance(payload, dict):
                raise ToolProviderError("Sandbox returned an invalid execution response")
            return payload
        except (httpx.HTTPError, ValueError) as exc:
            raise ToolProviderError("Sandbox execution failed") from exc
