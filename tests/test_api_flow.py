from tests.conftest import client


def test_register_login_and_me_flow():
    email = "flow@example.com"
    password = "securepass123"

    register = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": password},
    )
    assert register.status_code == 201
    assert register.json()["email"] == email

    duplicate = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": password},
    )
    assert duplicate.status_code == 400

    login = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
    )
    assert login.status_code == 200
    token = login.json()["access_token"]

    me = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert me.status_code == 200
    assert me.json()["email"] == email


def test_conversation_requires_authentication():
    response = client.get("/api/v1/conversations")
    assert response.status_code in (401, 403)


def test_create_and_list_conversation():
    email = "conversation-flow@example.com"
    password = "securepass123"

    client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": password},
    )
    login = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
    )
    token = login.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    created = client.post(
        "/api/v1/conversations",
        headers=headers,
        json={"title": "  My first chat  "},
    )
    assert created.status_code == 201
    assert created.json()["title"] == "My first chat"

    listed = client.get("/api/v1/conversations", headers=headers)
    assert listed.status_code == 200
    assert any(item["title"] == "My first chat" for item in listed.json())
