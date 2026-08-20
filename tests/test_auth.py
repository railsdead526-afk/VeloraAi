from tests.conftest import TestingSessionLocal, client


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


def test_register_duplicate_email_is_rejected():
    payload = {"email": "duplicate@example.com", "password": "12345678"}
    assert client.post("/api/v1/auth/register", json=payload).status_code == 201
    assert client.post("/api/v1/auth/register", json=payload).status_code == 400


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


def test_login_wrong_password_is_rejected():
    client.post(
        "/api/v1/auth/register",
        json={"email": "wrongpass@example.com", "password": "12345678"},
    )
    response = client.post(
        "/api/v1/auth/login",
        json={"email": "wrongpass@example.com", "password": "bad-password"},
    )
    assert response.status_code == 401


def test_inactive_user_cannot_login_or_use_existing_token():
    client.post(
        "/api/v1/auth/register",
        json={"email": "inactive@example.com", "password": "12345678"},
    )
    active_login = client.post(
        "/api/v1/auth/login",
        json={"email": "inactive@example.com", "password": "12345678"},
    )
    assert active_login.status_code == 200
    token = active_login.json()["access_token"]

    db = TestingSessionLocal()
    try:
        from app.crud.user import get_user_by_email
        user = get_user_by_email(db, "inactive@example.com")
        user.is_active = False
        db.commit()
    finally:
        db.close()

    assert client.post(
        "/api/v1/auth/login",
        json={"email": "inactive@example.com", "password": "12345678"},
    ).status_code == 401
    assert client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    ).status_code == 401


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


def test_premium_only_allows_pro_and_denies_free():
    client.post(
        "/api/v1/auth/register",
        json={"email": "free-premium@example.com", "password": "12345678"},
    )
    free_login = client.post(
        "/api/v1/auth/login",
        json={"email": "free-premium@example.com", "password": "12345678"},
    )
    free_token = free_login.json()["access_token"]
    assert client.get(
        "/api/v1/auth/premium-only",
        headers={"Authorization": f"Bearer {free_token}"},
    ).status_code == 403

    db = TestingSessionLocal()
    try:
        from app.crud.user import get_user_by_email
        user = get_user_by_email(db, "free-premium@example.com")
        user.role = "pro"
        db.commit()
    finally:
        db.close()

    pro_login = client.post(
        "/api/v1/auth/login",
        json={"email": "free-premium@example.com", "password": "12345678"},
    )
    pro_token = pro_login.json()["access_token"]
    response = client.get(
        "/api/v1/auth/premium-only",
        headers={"Authorization": f"Bearer {pro_token}"},
    )
    assert response.status_code == 200
    assert response.json()["role"] == "pro"
