from typing import Any

from app.services.sandbox_client import SandboxClient
from app.tools.providers import ToolProviderError
from app.tools.terminal_safety import TerminalSafetyError, validate_workspace_id


def terminal_exec(arguments: dict[str, Any]) -> dict[str, Any]:
    command = str(arguments.get("command", "")).strip()
    if not command:
        raise ToolProviderError("Terminal command is required")

    try:
        client = SandboxClient()
        requested_workspace = arguments.get("workspace_id")
        workspace_id = None
        if isinstance(requested_workspace, str) and requested_workspace.strip():
            # No tool exposes workspace_id today, but the plumbing accepts one, so
            # reject a hostile value here rather than relying on that staying true.
            try:
                workspace_id = validate_workspace_id(requested_workspace)
            except TerminalSafetyError as exc:
                raise ToolProviderError("Invalid sandbox workspace id") from exc
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
