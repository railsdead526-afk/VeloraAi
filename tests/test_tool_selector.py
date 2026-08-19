from app.tools.base import ToolDefinition
from app.tools.selector import select_tools


async def _noop(arguments):
    return arguments


def _tool(name: str, plans: frozenset[str]) -> ToolDefinition:
    return ToolDefinition(
        name=name,
        description=f"{name} tool",
        handler=_noop,
        allowed_plans=plans,
    )


def test_selector_filters_by_plan_and_context():
    tools = [
        _tool("github_read_file", frozenset({"pro", "max", "admin"})),
        _tool("calculator", frozenset({"free", "pro", "max", "admin"})),
        _tool("terminal", frozenset({"pro", "max", "admin"})),
    ]

    selected = select_tools(tools, "read my github repository file", plan="pro", max_tools=2)
    names = [tool.name for tool in selected]

    assert "github_read_file" in names
    assert len(names) <= 2


def test_selector_never_exposes_paid_tools_to_free():
    tools = [
        _tool("github", frozenset({"pro", "max", "admin"})),
        _tool("calculator", frozenset({"free", "pro", "max", "admin"})),
    ]

    selected = select_tools(tools, "use github to inspect my repo", plan="free")
    assert [tool.name for tool in selected] == ["calculator"]
