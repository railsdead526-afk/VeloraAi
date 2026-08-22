from __future__ import annotations

from typing import Iterable

from app.tools.base import ToolDefinition, ToolRisk


class ToolPolicy:
    """Central capability policy for tool exposure and execution safety."""

    def allows(self, tool: ToolDefinition, *, plan: str) -> bool:
        return tool.allows_plan(plan)

    def visible_tools(
        self,
        tools: Iterable[ToolDefinition],
        *,
        plan: str,
    ) -> list[ToolDefinition]:
        return [tool for tool in tools if self.allows(tool, plan=plan)]

    def requires_approval(self, tool: ToolDefinition) -> bool:
        """All explicitly high-impact tools require explicit approval."""
        return tool.requires_confirmation or tool.risk_level in {
            ToolRisk.WRITE,
            ToolRisk.DESTRUCTIVE,
            ToolRisk.PRIVILEGED,
        }


policy = ToolPolicy()
