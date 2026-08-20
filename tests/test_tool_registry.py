from app.tools.bootstrap import get_registry


def test_registry_contains_only_configured_tools():
    names = {tool.name for tool in get_registry().list()}

    assert "github" not in names
    assert "terminal" not in names
    assert "vercel" not in names
    assert "railway" not in names
    assert "cloudflare" not in names
    assert "supabase" not in names
    assert "calculator" not in names

    assert "github_list_repositories" in names
    assert "github_write_file" in names
    assert "vercel_list_projects" in names
    assert "railway_list_services" in names
    assert "cloudflare_list_dns_records" in names
    assert "supabase_execute_sql" in names
    assert "terminal_read_file" in names
