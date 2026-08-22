import asyncio
import inspect
from typing import Any

from app.services.tool_validation import ToolArgumentValidationError, validate_tool_arguments
from app.tools.policy import policy
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
    call_counts: dict[str, int] | None = None,
) -> Any:
    tool = registry.get(name)

    if not policy.allows(tool, plan=plan):
        raise ToolExecutionError("Tool is not available for this plan")

    try:
        arguments = validate_tool_arguments(tool, arguments)
    except ToolArgumentValidationError as exc:
        raise ToolExecutionError(str(exc)) from exc

    if policy.requires_approval(tool) and not confirmed:
        raise ToolExecutionError("Tool execution requires user confirmation")

    counts = call_counts if call_counts is not None else {}
    used = counts.get(name, 0)
    if used >= tool.max_calls_per_request:
        raise ToolExecutionError("Tool call limit exceeded for this request")
    counts[name] = used + 1

    try:
        if inspect.iscoroutinefunction(tool.handler):
            result = await asyncio.wait_for(
                tool.handler(arguments),
                timeout=tool.timeout_seconds,
            )
        else:
            result = await asyncio.wait_for(
                asyncio.to_thread(tool.handler, arguments),
                timeout=tool.timeout_seconds,
            )
        return result
    except TimeoutError as exc:
        raise ToolExecutionError("Tool execution timed out") from exc
    except ToolExecutionError:
        raise
    except Exception as exc:
        raise ToolExecutionError("Tool execution failed") from exc
