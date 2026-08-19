from tests.conftest import client


def register_and_login(email: str):
    client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "12345678"},
    )
    response = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "12345678"},
    )
    return response.json()["access_token"]


def test_user_cannot_access_another_users_conversation():
    owner_token = register_and_login("owner@example.com")
    attacker_token = register_and_login("attacker@example.com")

    created = client.post(
        "/api/v1/conversations",
        json={"title": "Private"},
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    conversation_id = created.json()["id"]

    headers = {"Authorization": f"Bearer {attacker_token}"}

    assert client.get(
        f"/api/v1/conversations/{conversation_id}/messages",
        headers=headers,
    ).status_code == 404

    assert client.patch(
        f"/api/v1/conversations/{conversation_id}",
        json={"title": "Hijacked"},
        headers=headers,
    ).status_code == 404

    assert client.delete(
        f"/api/v1/conversations/{conversation_id}",
        headers=headers,
    ).status_code == 404

    assert client.post(
        f"/api/v1/conversations/{conversation_id}/messages",
        json={"content": "steal this"},
        headers=headers,
    ).status_code == 404
