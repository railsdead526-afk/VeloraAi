import os
from typing import Any

import httpx

from app.tools.providers import ToolProviderError


def terminal_exec(arguments: dict[str, Any]) -> dict[str, Any]:
    sandbox_url = os.getenv("TERMINAL_SANDBOX_URL", "").rstrip("/")
    token = os.getenv("TERMINAL_SANDBOX_TOKEN", "")
    command = str(arguments.get("command", "")).strip()
    if not sandbox_url or not token:
        raise ToolProviderError("Terminal sandbox is not configured")
    if not command:
        raise ToolProviderError("Terminal command is required")
    try:
        response = httpx.post(
            f"{sandbox_url}/execute",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json={"command": command, "cwd": arguments.get("cwd"), "timeout": min(int(arguments.get("timeout", 30)), 60)},
            timeout=65,
        )
        response.raise_for_status()
        data = response.json()
        return data if isinstance(data, dict) else {"data": data}
    except (httpx.HTTPError, ValueError) as exc:
        raise ToolProviderError("Terminal sandbox request failed") from exc
