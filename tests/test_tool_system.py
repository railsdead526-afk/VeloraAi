import asyncio

import pytest

from app.tools.base import ToolDefinition
from app.tools.executor import ToolExecutionError, execute_tool
from app.tools.registry import ToolRegistry


@pytest.mark.asyncio
async def test_tool_registry_and_executor():
    registry = ToolRegistry()

    async def calculator(arguments):
        return arguments["a"] + arguments["b"]

    registry.register(
        ToolDefinition(
            name="calculator",
            description="Safe arithmetic",
            handler=calculator,
            allowed_plans=frozenset({"free", "pro", "max", "admin"}),
        )
    )

    result = await execute_tool(
        registry,
        name="calculator",
        arguments={"a": 2, "b": 3},
        plan="free",
    )
    assert result == 5


@pytest.mark.asyncio
async def test_tool_plan_restriction():
    registry = ToolRegistry()
    registry.register(
        ToolDefinition(
            name="advanced",
            description="Advanced tool",
            handler=lambda _: "ok",
            allowed_plans=frozenset({"pro", "max"}),
        )
    )

    with pytest.raises(ToolExecutionError, match="not available"):
        await execute_tool(registry, name="advanced", arguments={}, plan="free")


@pytest.mark.asyncio
async def test_tool_confirmation_and_timeout():
    registry = ToolRegistry()

    async def slow(_):
        await asyncio.sleep(0.05)
        return "done"

    registry.register(
        ToolDefinition(
            name="dangerous",
            description="Requires confirmation",
            handler=slow,
            allowed_plans=frozenset({"max"}),
            requires_confirmation=True,
            timeout_seconds=0.01,
        )
    )

    with pytest.raises(ToolExecutionError, match="confirmation"):
        await execute_tool(registry, name="dangerous", arguments={}, plan="max")

    with pytest.raises(ToolExecutionError, match="timed out"):
        await execute_tool(
            registry,
            name="dangerous",
            arguments={},
            plan="max",
            confirmed=True,
        )


def test_registry_rejects_duplicate_tools():
    registry = ToolRegistry()
    tool = ToolDefinition(
        name="same",
        description="duplicate",
        handler=lambda _: None,
        allowed_plans=frozenset({"free"}),
    )
    registry.register(tool)
    with pytest.raises(ValueError, match="already registered"):
        registry.register(tool)
