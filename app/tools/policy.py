from __future__ import annotations

from enum import StrEnum
from typing import Iterable

from app.tools.base import ToolDefinition


class ToolRisk(StrEnum):
    LOW = "low"
    WRITE = "write"
    DESTRUCTIVE = "destructive"
    PRIVILEGED = "privileged"


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
