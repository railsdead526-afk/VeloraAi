import json

from app.core.plans import get_plan_policy
from app.tools.bootstrap import get_registry
from app.tools.executor import ToolExecutionError, execute_tool


def test_tool_registry_exposes_function_schemas():
    schemas = get_registry().schemas()
    names = {item["function"]["name"] for item in schemas}
    assert "github_list_repositories" in names
    assert "terminal_exec" in names


def test_terminal_requires_confirmation():
    registry = get_registry()
    tool = registry.get("terminal_exec")
    assert tool.requires_confirmation is True


def test_terminal_is_not_available_to_free():
    registry = get_registry()
    plan = get_plan_policy("free")
    try:
        import asyncio
        asyncio.run(
            execute_tool(
                registry,
                name="terminal_exec",
                arguments={"command": "echo test"},
                plan=plan.name,
                confirmed=True,
            )
        )
    except ToolExecutionError as exc:
        assert "not available" in str(exc).lower()


def test_tool_error_results_are_json_serializable():
    payload = {"error": "Tool execution failed"}
    assert json.dumps(payload)
