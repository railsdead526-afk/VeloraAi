import ipaddress

from fastapi import Request
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.core.config import settings


def _trusted_networks():
    return [ipaddress.ip_network(value, strict=False) for value in settings.trusted_proxy_ips]


def _is_trusted(address: str, networks) -> bool:
    try:
        ip = ipaddress.ip_address(address)
    except ValueError:
        return False
    return any(ip in network for network in networks)


def get_client_address(request: Request) -> str:
    peer_address = get_remote_address(request)
    networks = _trusted_networks()
    if not networks or not _is_trusted(peer_address, networks):
        return peer_address

    forwarded_for = request.headers.get("x-forwarded-for", "")
    addresses = [value.strip() for value in forwarded_for.split(",") if value.strip()]
    for address in reversed(addresses):
        if not _is_trusted(address, networks):
            return address
    return peer_address


limiter = Limiter(
    key_func=get_client_address,
    default_limits=[settings.rate_limit_default],
    storage_uri=settings.rate_limit_storage_uri,
)
