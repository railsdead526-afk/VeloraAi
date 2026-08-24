from starlette.requests import Request

from app.core.rate_limit import get_client_address


def make_request(*, client_host: str, forwarded_for: str | None = None) -> Request:
    headers = []
    if forwarded_for is not None:
        headers.append((b"x-forwarded-for", forwarded_for.encode()))
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/api/v1/health",
            "query_string": b"",
            "headers": headers,
            "client": (client_host, 1234),
            "server": ("api", 8000),
            "scheme": "http",
        }
    )


def test_untrusted_client_cannot_spoof_forwarded_for(monkeypatch):
    monkeypatch.setattr("app.core.rate_limit.settings.trusted_proxy_ips", ["10.0.0.0/8"])
    request = make_request(client_host="192.0.2.10", forwarded_for="198.51.100.10")
    assert get_client_address(request) == "192.0.2.10"


def test_trusted_proxy_chain_returns_first_untrusted_hop(monkeypatch):
    monkeypatch.setattr("app.core.rate_limit.settings.trusted_proxy_ips", ["10.0.0.0/8"])
    request = make_request(
        client_host="10.0.0.2",
        forwarded_for="198.51.100.10, 10.0.0.3",
    )
    assert get_client_address(request) == "198.51.100.10"
