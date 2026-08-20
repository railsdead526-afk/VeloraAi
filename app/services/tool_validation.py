from __future__ import annotations

from typing import Any

from jsonschema import Draft202012Validator, SchemaError

from app.tools.base import ToolDefinition


class ToolArgumentValidationError(ValueError):
    """Raised when tool arguments do not satisfy the registered schema."""


def validate_tool_arguments(
    tool: ToolDefinition,
    arguments: dict[str, Any],
) -> dict[str, Any]:
    schema = tool.parameters
    try:
        validator = Draft202012Validator(schema)
    except SchemaError as exc:
        raise ToolArgumentValidationError("Tool parameter schema is invalid") from exc

    errors = sorted(validator.iter_errors(arguments), key=lambda error: list(error.path))
    if errors:
        first = errors[0]
        path = ".".join(str(part) for part in first.path)
        location = f" at {path}" if path else ""
        raise ToolArgumentValidationError(
            f"Invalid arguments for tool '{tool.name}'{location}: {first.message}"
        )

    return arguments
