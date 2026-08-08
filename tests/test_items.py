from tests.conftest import client


def create_user_and_get_token(email: str, password: str = "12345678"):
    client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": password},
    )
    response = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
    )
    return response.json()["access_token"]


def test_create_item():
    token = create_user_and_get_token("itemuser@example.com")

    response = client.post(
        "/api/v1/items",
        json={"name": "Item Test", "description": "Testing item"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "Item Test"
    assert data["description"] == "Testing item"
    assert "id" in data


def test_list_items_only_owner_items():
    token1 = create_user_and_get_token("owner1@example.com")
    token2 = create_user_and_get_token("owner2@example.com")

    client.post(
        "/api/v1/items",
        json={"name": "Owner1 Item", "description": "Milik owner1"},
        headers={"Authorization": f"Bearer {token1}"},
    )

    response = client.get(
        "/api/v1/items",
        headers={"Authorization": f"Bearer {token2}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 0
    assert data["items"] == []


def test_get_item_only_owner_can_access():
    token1 = create_user_and_get_token("getowner1@example.com")
    token2 = create_user_and_get_token("getowner2@example.com")

    create_response = client.post(
        "/api/v1/items",
        json={"name": "Secret Item", "description": "Owner1 only"},
        headers={"Authorization": f"Bearer {token1}"},
    )
    item_id = create_response.json()["id"]

    response = client.get(
        f"/api/v1/items/{item_id}",
        headers={"Authorization": f"Bearer {token2}"},
    )
    assert response.status_code == 404


def test_delete_item_only_owner_can_delete():
    token1 = create_user_and_get_token("deleteowner1@example.com")
    token2 = create_user_and_get_token("deleteowner2@example.com")

    create_response = client.post(
        "/api/v1/items",
        json={"name": "Delete Test", "description": "Owner1 only"},
        headers={"Authorization": f"Bearer {token1}"},
    )
    item_id = create_response.json()["id"]

    response = client.delete(
        f"/api/v1/items/{item_id}",
        headers={"Authorization": f"Bearer {token2}"},
    )
    assert response.status_code == 404

    owner_check = client.get(
        f"/api/v1/items/{item_id}",
        headers={"Authorization": f"Bearer {token1}"},
    )
    assert owner_check.status_code == 200


def test_items_requires_auth():
    response = client.get("/api/v1/items")
    assert response.status_code == 401

def test_update_item_only_owner_can_update():
    token1 = create_user_and_get_token("updateowner1@example.com")
    token2 = create_user_and_get_token("updateowner2@example.com")

    create_response = client.post(
        "/api/v1/items",
        json={"name": "Original", "description": "Owner1 item"},
        headers={"Authorization": f"Bearer {token1}"},
    )

    assert create_response.status_code == 201
    item_id = create_response.json()["id"]

    response = client.put(
        f"/api/v1/items/{item_id}",
        json={"name": "Hacked", "description": "Not yours"},
        headers={"Authorization": f"Bearer {token2}"},
    )

    assert response.status_code == 404

    owner_check = client.get(
        f"/api/v1/items/{item_id}",
        headers={"Authorization": f"Bearer {token1}"},
    )

    assert owner_check.status_code == 200
    data = owner_check.json()
    assert data["name"] == "Original"
    assert data["description"] == "Owner1 item"

