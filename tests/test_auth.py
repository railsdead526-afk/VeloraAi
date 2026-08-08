from tests.conftest import client


def test_register():
    response = client.post(
        "/api/v1/auth/register",
        json={"email": "testuser@example.com", "password": "12345678"},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["email"] == "testuser@example.com"
    assert data["is_active"] is True
    assert "id" in data


def test_login():
    client.post(
        "/api/v1/auth/register",
        json={"email": "loginuser@example.com", "password": "12345678"},
    )

    response = client.post(
        "/api/v1/auth/login",
        json={"email": "loginuser@example.com", "password": "12345678"},
    )
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"


def test_auth_me():
    client.post(
        "/api/v1/auth/register",
        json={"email": "meuser@example.com", "password": "12345678"},
    )

    login_response = client.post(
        "/api/v1/auth/login",
        json={"email": "meuser@example.com", "password": "12345678"},
    )
    token = login_response.json()["access_token"]

    response = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["email"] == "meuser@example.com"


def test_auth_me_unauthorized():
    response = client.get("/api/v1/auth/me")
    assert response.status_code == 401

