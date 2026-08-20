from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable


ToolHandler = Callable[[dict[str, Any]], Any | Awaitable[Any]]


@dataclass(frozen=True)
class ToolDefinition:
    name: str
    description: str
    handler: ToolHandler
    allowed_plans: frozenset[str]
    parameters: dict[str, Any] = field(
        default_factory=lambda: {
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        }
    )
    requires_confirmation: bool = False
    timeout_seconds: float = 10.0
    max_calls_per_request: int = 1

    def allows_plan(self, plan: str) -> bool:
        return plan.lower() in self.allowed_plans
