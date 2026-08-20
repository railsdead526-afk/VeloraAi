import pytest

from app.services.tool_validation import ToolArgumentValidationError, validate_tool_arguments
from app.tools.base import ToolDefinition


def _tool(parameters):
    return ToolDefinition(
        name="example_tool",
        description="Example",
        handler=lambda arguments: arguments,
        allowed_plans=frozenset({"free", "pro", "max", "admin"}),
        parameters=parameters,
    )


def test_validate_accepts_matching_arguments():
    tool = _tool({
        "type": "object",
        "properties": {"limit": {"type": "integer", "minimum": 1}},
        "required": ["limit"],
        "additionalProperties": False,
    })

    assert validate_tool_arguments(tool, {"limit": 10}) == {"limit": 10}


def test_validate_rejects_wrong_type():
    tool = _tool({
        "type": "object",
        "properties": {"limit": {"type": "integer"}},
        "required": ["limit"],
        "additionalProperties": False,
    })

    with pytest.raises(ToolArgumentValidationError, match="limit"):
        validate_tool_arguments(tool, {"limit": "10"})


def test_validate_rejects_unknown_fields():
    tool = _tool({
        "type": "object",
        "properties": {"limit": {"type": "integer"}},
        "additionalProperties": False,
    })

    with pytest.raises(ToolArgumentValidationError, match="Additional properties"):
        validate_tool_arguments(tool, {"limit": 10, "token": "secret"})


def test_validate_rejects_invalid_registered_schema():
    tool = _tool({"type": "not-a-real-schema-type"})

    with pytest.raises(ToolArgumentValidationError, match="schema is invalid"):
        validate_tool_arguments(tool, {})
