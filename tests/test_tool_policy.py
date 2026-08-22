from app.tools.base import ToolDefinition, ToolRisk
from app.tools.policy import policy


def _tool(name: str, plans: frozenset[str], risk: ToolRisk = ToolRisk.LOW) -> ToolDefinition:
    return ToolDefinition(
        name=name,
        description=name,
        handler=lambda _: None,
        allowed_plans=plans,
        risk_level=risk,
    )


def test_policy_preserves_existing_plan_access() -> None:
    free_tool = _tool("free_tool", frozenset({"free", "pro", "max", "admin"}))
    max_tool = _tool("max_tool", frozenset({"max", "admin"}), ToolRisk.WRITE)

    visible = policy.visible_tools([free_tool, max_tool], plan="pro")

    assert [tool.name for tool in visible] == ["free_tool"]


def test_risk_metadata_is_explicit_and_non_behavioral() -> None:
    tool = _tool("deploy", frozenset({"max", "admin"}), ToolRisk.PRIVILEGED)

    assert tool.risk_level is ToolRisk.PRIVILEGED
    assert policy.allows(tool, plan="max")
