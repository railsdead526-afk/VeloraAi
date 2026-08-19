from typing import Any

from app.tools.base import ToolDefinition
from app.tools.registry import registry


_ALLOWED_ALL = frozenset({"free", "pro", "max", "admin"})
_ALLOWED_PAID = frozenset({"pro", "max", "admin"})


def _not_configured(_: dict[str, Any]) -> dict[str, str]:
    raise RuntimeError("Tool integration is not configured")


def register_builtin_tools() -> None:
    definitions = [
        ToolDefinition(
            name="calculator",
            description="Evaluate a safe arithmetic expression.",
            handler=_not_configured,
            allowed_plans=_ALLOWED_ALL,
            parameters={
                "type": "object",
                "properties": {"expression": {"type": "string"}},
                "required": ["expression"],
                "additionalProperties": False,
            },
            timeout_seconds=2,
            max_calls_per_request=5,
        ),
        ToolDefinition(
            name="github",
            description="Read or modify repositories, issues, pull requests, files, branches, and workflow state through a scoped GitHub integration.",
            handler=_not_configured,
            allowed_plans=_ALLOWED_PAID,
            parameters={
                "type": "object",
                "properties": {
                    "operation": {"type": "string", "enum": ["read", "write", "workflow"]},
                    "resource": {"type": "string"},
                    "arguments": {"type": "object"},
                },
                "required": ["operation", "resource"],
                "additionalProperties": False,
            },
            requires_confirmation=True,
            timeout_seconds=20,
            max_calls_per_request=5,
        ),
        ToolDefinition(
            name="terminal",
            description="Execute commands inside a locked-down VeloraAi sandbox. Never execute directly on the application host.",
            handler=_not_configured,
            allowed_plans=_ALLOWED_PAID,
            parameters={
                "type": "object",
                "properties": {"command": {"type": "string"}},
                "required": ["command"],
                "additionalProperties": False,
            },
            requires_confirmation=True,
            timeout_seconds=30,
            max_calls_per_request=3,
        ),
        ToolDefinition(
            name="vercel",
            description="Inspect and manage Vercel projects, deployments, domains, and environment configuration through scoped API credentials.",
            handler=_not_configured,
            allowed_plans=_ALLOWED_PAID,
            parameters={
                "type": "object",
                "properties": {
                    "operation": {"type": "string", "enum": ["read", "deploy", "domain", "env"]},
                    "project": {"type": "string"},
                    "arguments": {"type": "object"},
                },
                "required": ["operation"],
                "additionalProperties": False,
            },
            requires_confirmation=True,
            timeout_seconds=30,
            max_calls_per_request=3,
        ),
        ToolDefinition(
            name="railway",
            description="Inspect and manage Railway projects, services, deployments, variables, and logs through scoped API credentials.",
            handler=_not_configured,
            allowed_plans=_ALLOWED_PAID,
            parameters={
                "type": "object",
                "properties": {
                    "operation": {"type": "string", "enum": ["read", "deploy", "variables", "logs"]},
                    "project": {"type": "string"},
                    "arguments": {"type": "object"},
                },
                "required": ["operation"],
                "additionalProperties": False,
            },
            requires_confirmation=True,
            timeout_seconds=30,
            max_calls_per_request=3,
        ),
        ToolDefinition(
            name="cloudflare",
            description="Inspect and manage Cloudflare zones, DNS, Workers, Pages, and related resources through scoped API credentials.",
            handler=_not_configured,
            allowed_plans=_ALLOWED_PAID,
            parameters={
                "type": "object",
                "properties": {
                    "operation": {"type": "string", "enum": ["read", "dns", "workers", "pages"]},
                    "zone": {"type": "string"},
                    "arguments": {"type": "object"},
                },
                "required": ["operation"],
                "additionalProperties": False,
            },
            requires_confirmation=True,
            timeout_seconds=30,
            max_calls_per_request=3,
        ),
        ToolDefinition(
            name="supabase",
            description="Inspect and manage Supabase projects, database operations, edge functions, storage, and configuration through scoped credentials.",
            handler=_not_configured,
            allowed_plans=_ALLOWED_PAID,
            parameters={
                "type": "object",
                "properties": {
                    "operation": {"type": "string", "enum": ["read", "sql", "function", "storage", "config"]},
                    "project": {"type": "string"},
                    "arguments": {"type": "object"},
                },
                "required": ["operation"],
                "additionalProperties": False,
            },
            requires_confirmation=True,
            timeout_seconds=30,
            max_calls_per_request=3,
        ),
    ]

    for definition in definitions:
        try:
            registry.register(definition)
        except ValueError as exc:
            if not str(exc).startswith("Tool already registered:"):
                raise


register_builtin_tools()
