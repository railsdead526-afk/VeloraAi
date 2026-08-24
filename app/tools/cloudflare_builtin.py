from app.tools.base import ToolDefinition, ToolRisk
from app.tools.cloudflare_tools import (
    cloudflare_create_dns_record,
    cloudflare_delete_dns_record,
    cloudflare_list_dns_records,
    cloudflare_update_dns_record,
)

READ_PLANS = frozenset({"free", "pro", "max", "admin"})
WRITE_PLANS = frozenset({"pro", "max", "admin"})


def register_cloudflare_tools(registry) -> None:
    definitions = [
        ToolDefinition(
            name="cloudflare_list_dns_records",
            description="List DNS records for a Cloudflare zone.",
            handler=cloudflare_list_dns_records,
            allowed_plans=READ_PLANS,
            parameters={
                "type": "object",
                "properties": {
                    "zone_id": {"type": "string"},
                    "name": {"type": "string"},
                },
                "required": ["zone_id"],
                "additionalProperties": False,
            },
            timeout_seconds=15,
            max_calls_per_request=5,
        ),
        ToolDefinition(
            name="cloudflare_create_dns_record",
            description="Create a DNS record in a Cloudflare zone.",
            handler=cloudflare_create_dns_record,
            allowed_plans=WRITE_PLANS,
            parameters={
                "type": "object",
                "properties": {
                    "zone_id": {"type": "string"},
                    "type": {"type": "string"},
                    "name": {"type": "string"},
                    "content": {"type": "string"},
                    "ttl": {"type": "integer", "minimum": 1},
                    "proxied": {"type": "boolean"},
                    "priority": {"type": "integer", "minimum": 0},
                },
                "required": ["zone_id", "type", "name", "content"],
                "additionalProperties": False,
            },
            requires_confirmation=True,
            risk_level=ToolRisk.WRITE,
            timeout_seconds=15,
            max_calls_per_request=3,
        ),
        ToolDefinition(
            name="cloudflare_update_dns_record",
            description="Update a DNS record in a Cloudflare zone.",
            handler=cloudflare_update_dns_record,
            allowed_plans=WRITE_PLANS,
            parameters={
                "type": "object",
                "properties": {
                    "zone_id": {"type": "string"},
                    "record_id": {"type": "string"},
                    "type": {"type": "string"},
                    "name": {"type": "string"},
                    "content": {"type": "string"},
                    "ttl": {"type": "integer", "minimum": 1},
                    "proxied": {"type": "boolean"},
                },
                "required": ["zone_id", "record_id"],
                "additionalProperties": False,
            },
            requires_confirmation=True,
            risk_level=ToolRisk.WRITE,
            timeout_seconds=15,
            max_calls_per_request=3,
        ),
        ToolDefinition(
            name="cloudflare_delete_dns_record",
            description="Delete a DNS record from a Cloudflare zone.",
            handler=cloudflare_delete_dns_record,
            allowed_plans=WRITE_PLANS,
            parameters={
                "type": "object",
                "properties": {
                    "zone_id": {"type": "string"},
                    "record_id": {"type": "string"},
                },
                "required": ["zone_id", "record_id"],
                "additionalProperties": False,
            },
            requires_confirmation=True,
            risk_level=ToolRisk.DESTRUCTIVE,
            timeout_seconds=15,
            max_calls_per_request=3,
        ),
    ]
    for definition in definitions:
        try:
            registry.register(definition)
        except ValueError as exc:
            if not str(exc).startswith("Tool already registered:"):
                raise
