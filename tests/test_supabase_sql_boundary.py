import pytest

from app.services.supabase_sql_policy import validate_read_only_sql
from app.tools.bootstrap import get_registry


@pytest.mark.parametrize(
    "query",
    [
        "SELECT id FROM users",
        "SELECT id FROM users;",
        "EXPLAIN SELECT id FROM users",
        "SHOW search_path",
        "DESCRIBE users",
    ],
)
def test_read_only_sql_allows_safe_statements(query):
    assert validate_read_only_sql(query)


@pytest.mark.parametrize(
    "query",
    [
        "INSERT INTO users(id) VALUES (1)",
        "UPDATE users SET email='x'",
        "DELETE FROM users",
        "DROP TABLE users",
        "CREATE TABLE users_backup(id int)",
        "TRUNCATE users",
        "WITH deleted AS (DELETE FROM users RETURNING id) SELECT * FROM deleted",
        "SELECT 1; SELECT 2",
        "SELECT 1; DROP TABLE users",
    ],
)
def test_read_only_sql_rejects_mutating_or_multiple_statements(query):
    with pytest.raises(ValueError):
        validate_read_only_sql(query)


def test_supabase_sql_tools_use_separate_plan_boundaries():
    registry = get_registry()
    write_tool = registry.get("supabase_execute_sql")
    read_tool = registry.get("supabase_query_sql")

    assert write_tool.allowed_plans == frozenset({"max", "admin"})
    assert read_tool.allowed_plans == frozenset({"pro", "max", "admin"})
    assert write_tool.requires_confirmation is True
    assert read_tool.requires_confirmation is True
