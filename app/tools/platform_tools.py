from typing import Any

from app.tools.credentials import resolve_credential
from app.tools.providers import ToolProviderError, _request

#: Legacy environment-variable names kept as the public argument so the
#: existing call sites stay readable; resolution is per-user.
_PROVIDER_BY_ENV = {
    "GITHUB_TOKEN": "github",
    "VERCEL_TOKEN": "vercel",
    "RAILWAY_TOKEN": "railway",
    "CLOUDFLARE_API_TOKEN": "cloudflare",
    "SUPABASE_ACCESS_TOKEN": "supabase",
}


def _token(name: str) -> str:
    provider = _PROVIDER_BY_ENV.get(name)
    if provider is None:
        raise ToolProviderError(f"Unknown credential {name}")
    return resolve_credential(provider)


def vercel_get_project(arguments: dict[str, Any]) -> dict[str, Any]:
    token = _token("VERCEL_TOKEN")
    project = str(arguments.get("project", "")).strip()
    if not project:
        raise ToolProviderError("project is required")
    return _request("GET", f"https://api.vercel.com/v9/projects/{project}", token=token)


def vercel_list_deployments(arguments: dict[str, Any]) -> dict[str, Any]:
    token = _token("VERCEL_TOKEN")
    project = str(arguments.get("project", "")).strip()
    limit = min(max(int(arguments.get("limit", 20)), 1), 100)
    query = f"?limit={limit}" + (f"&projectId={project}" if project else "")
    return _request("GET", f"https://api.vercel.com/v6/deployments{query}", token=token)


def vercel_get_deployment(arguments: dict[str, Any]) -> dict[str, Any]:
    token = _token("VERCEL_TOKEN")
    deployment = str(arguments.get("deployment", "")).strip()
    if not deployment:
        raise ToolProviderError("deployment is required")
    return _request("GET", f"https://api.vercel.com/v13/deployments/{deployment}", token=token)


def vercel_list_domains(arguments: dict[str, Any]) -> dict[str, Any]:
    token = _token("VERCEL_TOKEN")
    return _request("GET", "https://api.vercel.com/v5/domains", token=token)


def vercel_create_deployment(arguments: dict[str, Any]) -> dict[str, Any]:
    token = _token("VERCEL_TOKEN")
    project = str(arguments.get("project", "")).strip()
    if not project:
        raise ToolProviderError("project is required")
    payload = {
        "name": project,
        "project": project,
        "target": arguments.get("target"),
        "gitSource": arguments.get("git_source"),
    }
    payload = {key: value for key, value in payload.items() if value is not None}
    return _request("POST", "https://api.vercel.com/v13/deployments", token=token, json=payload)


def vercel_cancel_deployment(arguments: dict[str, Any]) -> dict[str, Any]:
    token = _token("VERCEL_TOKEN")
    deployment = str(arguments.get("deployment", "")).strip()
    if not deployment:
        raise ToolProviderError("deployment is required")
    return _request(
        "PATCH", f"https://api.vercel.com/v12/deployments/{deployment}/cancel", token=token, json={}
    )


def railway_list_services(arguments: dict[str, Any]) -> dict[str, Any]:
    token = _token("RAILWAY_TOKEN")
    project_id = str(arguments.get("project_id", "")).strip()
    if not project_id:
        raise ToolProviderError("project_id is required")
    query = "query($projectId: String!) { project(id: $projectId) { services { edges { node { id name } } } } }"
    return _request(
        "POST",
        "https://backboard.railway.com/graphql/v2",
        token=token,
        json={"query": query, "variables": {"projectId": project_id}},
    )


def railway_get_deployments(arguments: dict[str, Any]) -> dict[str, Any]:
    token = _token("RAILWAY_TOKEN")
    service_id = str(arguments.get("service_id", "")).strip()
    if not service_id:
        raise ToolProviderError("service_id is required")
    query = "query($serviceId: String!) { deployments(first: 20, input: { serviceId: $serviceId }) { edges { node { id status createdAt } } } }"
    return _request(
        "POST",
        "https://backboard.railway.com/graphql/v2",
        token=token,
        json={"query": query, "variables": {"serviceId": service_id}},
    )


def railway_get_deployment(arguments: dict[str, Any]) -> dict[str, Any]:
    token = _token("RAILWAY_TOKEN")
    deployment_id = str(arguments.get("deployment_id", "")).strip()
    if not deployment_id:
        raise ToolProviderError("deployment_id is required")
    query = (
        "query($deploymentId: String!) { deployment(id: $deploymentId) { id status createdAt } }"
    )
    return _request(
        "POST",
        "https://backboard.railway.com/graphql/v2",
        token=token,
        json={"query": query, "variables": {"deploymentId": deployment_id}},
    )


def railway_redeploy(arguments: dict[str, Any]) -> dict[str, Any]:
    token = _token("RAILWAY_TOKEN")
    deployment_id = str(arguments.get("deployment_id", "")).strip()
    if not deployment_id:
        raise ToolProviderError("deployment_id is required")
    mutation = (
        "mutation($deploymentId: String!) { deploymentRedeploy(id: $deploymentId) { id status } }"
    )
    return _request(
        "POST",
        "https://backboard.railway.com/graphql/v2",
        token=token,
        json={"query": mutation, "variables": {"deploymentId": deployment_id}},
    )


def railway_restart_service(arguments: dict[str, Any]) -> dict[str, Any]:
    token = _token("RAILWAY_TOKEN")
    service_id = str(arguments.get("service_id", "")).strip()
    if not service_id:
        raise ToolProviderError("service_id is required")
    mutation = (
        "mutation($serviceId: String!) { serviceInstanceRedeploy(serviceId: $serviceId) { id } }"
    )
    return _request(
        "POST",
        "https://backboard.railway.com/graphql/v2",
        token=token,
        json={"query": mutation, "variables": {"serviceId": service_id}},
    )
