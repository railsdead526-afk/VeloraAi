from app.core.config import settings
from tests.conftest import client


def test_health_endpoint():
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.json()["service"] == "VeloraAi"


def test_info_endpoint_uses_configured_environment():
    old_env = settings.app_env
    settings.app_env = "test"
    try:
        response = client.get("/api/v1/info")
        assert response.status_code == 200
        assert response.json()["environment"] == "test"
    finally:
        settings.app_env = old_env
