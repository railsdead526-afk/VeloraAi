from app.core.observability import get_request_id, set_request_id


def test_request_id_accepts_safe_client_value():
    assert set_request_id("client-req_123:abc") == "client-req_123:abc"
    assert get_request_id() == "client-req_123:abc"


def test_request_id_replaces_unsafe_values():
    value = set_request_id("x\n" + "A" * 200)
    assert value != "x\n" + "A" * 200
    assert 1 <= len(value) <= 128
    assert all(character.isalnum() for character in value)
