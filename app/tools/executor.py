import asyncio
import inspect
from typing import Any

from app.tools.registry import ToolRegistry


class ToolExecutionError(Exception):
    """Raised when a tool cannot be executed safely."""


async def execute_tool(
    registry: ToolRegistry,
    *,
    name: str,
    arguments: dict[str, Any],
    plan: str,
    confirmed: bool = False,
) -> Any:
    tool = registry.get(name)

    if not tool.allows_plan(plan):
        raise ToolExecutionError("Tool is not available for this plan")
    if tool.requires_confirmation and not confirmed:
        raise ToolExecutionError("Tool execution requires user confirmation")

    try:
        result = tool.handler(arguments)
        if inspect.isawaitable(result):
            return await asyncio.wait_for(result, timeout=tool.timeout_seconds)
        return result
    except asyncio.TimeoutError as exc:
        raise ToolExecutionError("Tool execution timed out") from exc
    except ToolExecutionError:
        raise
    except Exception as exc:
        raise ToolExecutionError("Tool execution failed") from exc
