import os


def test_platform_token_names_are_defined(monkeypatch):
    monkeypatch.setenv("VERCEL_TOKEN", "test-vercel")
    monkeypatch.setenv("RAILWAY_TOKEN", "test-railway")
    assert os.getenv("VERCEL_TOKEN")
    assert os.getenv("RAILWAY_TOKEN")


def test_platform_tool_parameters_are_valid():
    from app.tools.bootstrap import get_registry

    tools = {tool.name: tool for tool in get_registry().list()}
    expected = {
        "vercel_get_project",
        "vercel_list_deployments",
        "vercel_get_deployment",
        "vercel_list_domains",
        "vercel_create_deployment",
        "vercel_cancel_deployment",
        "railway_list_services",
        "railway_get_deployments",
        "railway_get_deployment",
        "railway_redeploy",
        "railway_restart_service",
    }
    assert expected <= tools.keys()
    assert all(tool.parameters["type"] == "object" for tool in (tools[name] for name in expected))


def test_mutating_platform_tools_require_confirmation():
    from app.tools.bootstrap import get_registry

    tools = {tool.name: tool for tool in get_registry().list()}
    mutating = {
        "vercel_create_deployment",
        "vercel_cancel_deployment",
        "railway_redeploy",
        "railway_restart_service",
    }
    assert all(tools[name].requires_confirmation for name in mutating)
