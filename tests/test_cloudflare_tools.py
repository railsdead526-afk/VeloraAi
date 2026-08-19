from app.tools.bootstrap import get_registry


def test_cloudflare_dns_tools_registered():
    names = {tool.name for tool in get_registry().list()}
    assert {
        "cloudflare_list_dns_records",
        "cloudflare_create_dns_record",
        "cloudflare_update_dns_record",
        "cloudflare_delete_dns_record",
    } <= names


def test_cloudflare_dns_mutations_require_confirmation():
    registry = get_registry()
    for name in {
        "cloudflare_create_dns_record",
        "cloudflare_update_dns_record",
        "cloudflare_delete_dns_record",
    }:
        assert registry.get(name).requires_confirmation is True
