from app.tools.base import ToolDefinition, ToolRisk
from app.tools.supabase_tools import supabase_execute_sql, supabase_query_sql

READ_SQL_PLANS = frozenset({"pro", "max", "admin"})
WRITE_SQL_PLANS = frozenset({"max", "admin"})
SQL_PARAMETERS = {
    "type": "object",
    "properties": {
        "project_id": {"type": "string"},
        "query": {"type": "string"},
    },
    "required": ["project_id", "query"],
    "additionalProperties": False,
}


def harden_supabase_sql_registry(registry) -> None:
    registry.replace(
        ToolDefinition(
            name="supabase_execute_sql",
            description="Execute SQL against Supabase Postgres with write capability.",
            handler=supabase_execute_sql,
            allowed_plans=WRITE_SQL_PLANS,
            parameters=SQL_PARAMETERS,
            requires_confirmation=True,
            # Arbitrary SQL with write capability: the most dangerous tool here.
            risk_level=ToolRisk.DESTRUCTIVE,
            timeout_seconds=30,
            max_calls_per_request=2,
        )
    )
    registry.register(
        ToolDefinition(
            name="supabase_query_sql",
            description="Run a single read-only SQL statement against Supabase Postgres.",
            handler=supabase_query_sql,
            allowed_plans=READ_SQL_PLANS,
            parameters=SQL_PARAMETERS,
            requires_confirmation=True,
            # Read-only by policy, but still arbitrary SQL against the user's
            # database, so it is gated rather than treated as a plain read.
            risk_level=ToolRisk.WRITE,
            timeout_seconds=30,
            max_calls_per_request=3,
        )
    )
