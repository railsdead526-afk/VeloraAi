from __future__ import annotations

from typing import Iterable

from app.tools.base import ToolDefinition, ToolRisk


class ToolPolicy:
    """Central capability and risk policy for tool exposure/execution."""

    def allows(self, tool: ToolDefinition, *, plan: str) -> bool:
        return tool.allows_plan(plan)

    def requires_approval(self, tool: ToolDefinition) -> bool:
        return tool.requires_confirmation or tool.risk_level is not ToolRisk.LOW

    def visible_tools(
        self,
        tools: Iterable[ToolDefinition],
        *,
        plan: str,
    ) -> list[ToolDefinition]:
        return [tool for tool in tools if self.allows(tool, plan=plan)]


policy = ToolPolicy()
