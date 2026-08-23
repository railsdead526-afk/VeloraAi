from typing import Any
from urllib.parse import quote

from app.tools.credentials import resolve_credential
from app.tools.identifiers import validate_identifier
from app.tools.providers import ToolProviderError, _request


def _token() -> str:
    return resolve_credential("cloudflare")


def _zone(arguments: dict[str, Any]) -> str:
    return validate_identifier(str(arguments.get("zone_id", "")), field="zone_id")


def cloudflare_list_dns_records(arguments: dict[str, Any]) -> dict[str, Any]:
    token = _token()
    zone = _zone(arguments)
    query = str(arguments.get("name", "")).strip()
    url = f"https://api.cloudflare.com/client/v4/zones/{zone}/dns_records?per_page=100"
    if query:
        url += f"&name={quote(query, safe='')}"
    return _request("GET", url, token=token)


def cloudflare_create_dns_record(arguments: dict[str, Any]) -> dict[str, Any]:
    token = _token()
    zone = _zone(arguments)
    record_type = str(arguments.get("type", "")).upper()
    name = str(arguments.get("name", "")).strip()
    content = str(arguments.get("content", "")).strip()
    if record_type not in {"A", "AAAA", "CNAME", "TXT", "MX", "NS"}:
        raise ToolProviderError("unsupported DNS record type")
    if not name or not content:
        raise ToolProviderError("name and content are required")
    payload = {
        "type": record_type,
        "name": name,
        "content": content,
        "ttl": int(arguments.get("ttl", 1)),
        "proxied": bool(arguments.get("proxied", False)),
    }
    if record_type == "MX":
        payload["priority"] = int(arguments.get("priority", 10))
    return _request(
        "POST",
        f"https://api.cloudflare.com/client/v4/zones/{zone}/dns_records",
        token=token,
        json=payload,
    )


def cloudflare_update_dns_record(arguments: dict[str, Any]) -> dict[str, Any]:
    token = _token()
    zone = _zone(arguments)
    record = validate_identifier(str(arguments.get("record_id", "")), field="record_id")
    payload: dict[str, Any] = {
        key: arguments[key]
        for key in ("type", "name", "content", "ttl", "proxied")
        if key in arguments
    }
    if "type" in payload:
        payload["type"] = str(payload["type"]).upper()
    if not payload:
        raise ToolProviderError("at least one DNS field is required")
    return _request(
        "PATCH",
        f"https://api.cloudflare.com/client/v4/zones/{zone}/dns_records/{record}",
        token=token,
        json=payload,
    )


def cloudflare_delete_dns_record(arguments: dict[str, Any]) -> dict[str, Any]:
    token = _token()
    zone = _zone(arguments)
    record = validate_identifier(str(arguments.get("record_id", "")), field="record_id")
    return _request(
        "DELETE",
        f"https://api.cloudflare.com/client/v4/zones/{zone}/dns_records/{record}",
        token=token,
    )
