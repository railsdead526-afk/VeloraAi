from __future__ import annotations

from typing import Iterable

from app.tools.base import ToolDefinition


class ToolPolicy:
    """Central capability policy for tool exposure."""

    def allows(self, tool: ToolDefinition, *, plan: str) -> bool:
        return tool.allows_plan(plan)

    def visible_tools(
        self,
        tools: Iterable[ToolDefinition],
        *,
        plan: str,
    ) -> list[ToolDefinition]:
        return [tool for tool in tools if self.allows(tool, plan=plan)]


policy = ToolPolicy()
