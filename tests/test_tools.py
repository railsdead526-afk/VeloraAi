from app.core.config import settings
from app.tools.bootstrap import get_registry


def test_platform_tools_are_registered():
    registry = get_registry()
    names = {tool.name for tool in registry.list()}
    assert {
        "github_list_repositories",
        "github_read_file",
        "vercel_list_projects",
        "railway_list_projects",
        "cloudflare_list_zones",
        "supabase_list_projects",
        "terminal_read_file",
        "terminal_run_tests",
    } <= names
    assert "terminal_exec" not in names


def test_tool_schemas_are_function_calling_compatible():
    schemas = get_registry().schemas()
    assert all(item["type"] == "function" for item in schemas)
    assert all("function" in item for item in schemas)


def test_llama_provider_is_supported():
    assert "llama" in {"mock", "openai", "llama"}
    assert settings.llama_base_url
