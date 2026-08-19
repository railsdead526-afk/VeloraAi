from typing import Any

from app.tools.base import ToolDefinition


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

    def get(self, name: str) -> ToolDefinition:
        try:
            return self._tools[name]
        except KeyError as exc:
            raise KeyError(f"Unknown tool: {name}") from exc

    def list(self) -> list[ToolDefinition]:
        return list(self._tools.values())

    def schemas(self) -> list[dict[str, Any]]:
        return [
            {
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.parameters,
                },
                "x-velora": {
                    "requires_confirmation": tool.requires_confirmation,
                    "timeout_seconds": tool.timeout_seconds,
                    "max_calls_per_request": tool.max_calls_per_request,
                    "allowed_plans": sorted(tool.allowed_plans),
                },
            }
            for tool in self._tools.values()
        ]


registry = ToolRegistry()
