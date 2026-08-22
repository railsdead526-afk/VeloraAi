import pytest

from app.tools.base import ToolDefinition, ToolRisk
from app.tools.executor import ToolExecutionError, execute_tool
from app.tools.registry import ToolRegistry
from app.tools.policy import policy


def _tool(risk: ToolRisk, *, confirmation: bool = False) -> ToolDefinition:
    return ToolDefinition(
        name=f"tool_{risk.value}",
        description="test",
        handler=lambda _: {"ok": True},
        allowed_plans=frozenset({"max", "admin"}),
        requires_confirmation=confirmation,
        risk_level=risk,
    )


def test_risk_policy_requires_approval_for_high_impact_tools() -> None:
    assert not policy.requires_approval(_tool(ToolRisk.LOW))
    assert policy.requires_approval(_tool(ToolRisk.WRITE))
    assert policy.requires_approval(_tool(ToolRisk.DESTRUCTIVE))
    assert policy.requires_approval(_tool(ToolRisk.PRIVILEGED))
    assert policy.requires_approval(_tool(ToolRisk.LOW, confirmation=True))


@pytest.mark.asyncio
async def test_executor_blocks_risky_tool_without_confirmation() -> None:
    registry = ToolRegistry()
    tool = _tool(ToolRisk.WRITE)
    registry.register(tool)

    with pytest.raises(ToolExecutionError, match="requires user confirmation"):
        await execute_tool(
            registry,
            name=tool.name,
            arguments={},
            plan="max",
            confirmed=False,
        )


@pytest.mark.asyncio
async def test_executor_allows_risky_tool_after_confirmation() -> None:
    registry = ToolRegistry()
    tool = _tool(ToolRisk.WRITE)
    registry.register(tool)

    result = await execute_tool(
        registry,
        name=tool.name,
        arguments={},
        plan="max",
        confirmed=True,
    )

    assert result == {"ok": True}
