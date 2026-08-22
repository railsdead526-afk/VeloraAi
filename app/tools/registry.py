from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from app.tools.base import ToolDefinition

# `ToolRegistry.list` shadows the builtin inside the class body, so annotations
# written as `list[...]` there would resolve to the method rather than the type.
# Aliasing keeps the public method name while letting the annotations be correct.
_List = list


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, ToolDefinition] = {}

    def register(self, tool: ToolDefinition) -> None:
        if tool.name in self._tools:
            raise ValueError(f"Tool already registered: {tool.name}")
        if tool.timeout_seconds <= 0:
            raise ValueError("Tool timeout must be greater than zero")
        if tool.max_calls_per_request < 1:
            raise ValueError("Tool max_calls_per_request must be at least one")
        self._tools[tool.name] = tool

    def replace(self, tool: ToolDefinition) -> None:
        if tool.name not in self._tools:
            raise KeyError(f"Unknown tool: {tool.name}")
        if tool.timeout_seconds <= 0:
            raise ValueError("Tool timeout must be greater than zero")
        if tool.max_calls_per_request < 1:
            raise ValueError("Tool max_calls_per_request must be at least one")
        self._tools[tool.name] = tool

    def get(self, name: str) -> ToolDefinition:
        try:
            return self._tools[name]
        except KeyError as exc:
            raise KeyError(f"Unknown tool: {name}") from exc

    def list(self) -> _List[ToolDefinition]:
        return _List(self._tools.values())

    @staticmethod
    def schemas_for(tools: Iterable[ToolDefinition]) -> _List[dict[str, Any]]:
        return [
            {
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.parameters,
                },
            }
            for tool in tools
        ]

    def schemas(self) -> _List[dict[str, Any]]:
        return self.schemas_for(self._tools.values())


registry = ToolRegistry()
