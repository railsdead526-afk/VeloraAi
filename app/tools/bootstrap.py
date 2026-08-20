from app.tools.base import ToolDefinition
from app.tools.builtin import register_platform_tools
from app.tools.cloudflare_builtin import register_cloudflare_tools
from app.tools.registry import registry
from app.tools.terminal import terminal_exec

_INITIALIZED = False


def get_registry():
    global _INITIALIZED
    if not _INITIALIZED:
        register_platform_tools(registry)
        register_cloudflare_tools(registry)
        try:
            registry.register(
                ToolDefinition(
                    name="terminal_exec",
                    description="Execute a command inside the locked-down VeloraAi terminal sandbox.",
                    handler=terminal_exec,
                    allowed_plans=frozenset({"pro", "max", "admin"}),
                    parameters={
                        "type": "object",
                        "properties": {
                            "command": {"type": "string"},
                            "cwd": {"type": "string"},
                            "timeout": {"type": "integer", "minimum": 1, "maximum": 60},
                        },
                        "required": ["command"],
                        "additionalProperties": False,
                    },
                    requires_confirmation=True,
                    timeout_seconds=65,
                    max_calls_per_request=3,
                )
            )
        except ValueError as exc:
            if not str(exc).startswith("Tool already registered:"):
                raise
        _INITIALIZED = True
    return registry
