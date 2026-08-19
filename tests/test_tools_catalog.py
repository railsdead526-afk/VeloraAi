from app.tools.catalog import register_builtin_tools
from app.tools.registry import registry


def test_builtin_tool_catalog_exposes_platform_tools():
    register_builtin_tools()
    names = {tool.name for tool in registry.list()}
    assert {"calculator", "github", "terminal", "vercel", "railway", "cloudflare", "supabase"}.issubset(names)


def test_platform_tools_require_confirmation():
    register_builtin_tools()
    for name in {"github", "terminal", "vercel", "railway", "cloudflare", "supabase"}:
        assert registry.get(name).requires_confirmation is True


def test_tool_schemas_are_function_calling_compatible():
    register_builtin_tools()
    schemas = registry.schemas()
    assert all(item["type"] == "function" for item in schemas)
    assert all("parameters" in item["function"] for item in schemas)
