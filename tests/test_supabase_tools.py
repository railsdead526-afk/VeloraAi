from app.tools.providers import ToolProviderError
from app.tools.supabase_tools import supabase_execute_sql


def test_supabase_sql_requires_project_id(monkeypatch):
    monkeypatch.setenv("SUPABASE_ACCESS_TOKEN", "test-token")
    try:
        supabase_execute_sql({"query": "select 1"})
    except ToolProviderError as exc:
        assert "project_id" in str(exc)
    else:
        raise AssertionError("expected project_id validation error")


def test_supabase_sql_requires_query(monkeypatch):
    monkeypatch.setenv("SUPABASE_ACCESS_TOKEN", "test-token")
    try:
        supabase_execute_sql({"project_id": "project-ref"})
    except ToolProviderError as exc:
        assert "query" in str(exc)
    else:
        raise AssertionError("expected query validation error")
