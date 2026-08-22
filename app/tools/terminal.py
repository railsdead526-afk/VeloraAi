from typing import Any

from app.services.sandbox_client import SandboxClient
from app.tools.providers import ToolProviderError


def terminal_exec(arguments: dict[str, Any]) -> dict[str, Any]:
    command = str(arguments.get("command", "")).strip()
    if not command:
        raise ToolProviderError("Terminal command is required")

    try:
        client = SandboxClient()
        requested_workspace = arguments.get("workspace_id")
        workspace_id = (
            requested_workspace.strip()
            if isinstance(requested_workspace, str) and requested_workspace.strip()
            else None
        )
        owns_workspace = workspace_id is None
        workspace_id = workspace_id or client.create_workspace()
        try:
            return client.execute(
                workspace_id=workspace_id,
                command=command,
                cwd=arguments.get("cwd"),
                timeout=min(int(arguments.get("timeout", 30)), 60),
            )
        finally:
            if owns_workspace:
                client.delete_workspace(workspace_id)
    except ToolProviderError:
        raise
    except (TypeError, ValueError) as exc:
        raise ToolProviderError("Invalid terminal execution parameters") from exc
