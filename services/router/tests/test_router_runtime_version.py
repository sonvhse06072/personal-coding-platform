from fastapi.testclient import TestClient

from app.main import ROUTER_VERSION, app


def test_router_version_is_1_0_28():
    assert ROUTER_VERSION == "1.0.28"
    assert app.version == ROUTER_VERSION


def test_router_health_reports_same_service_version():
    response = TestClient(app).get("/health")

    assert response.status_code == 200
    assert response.json()["version"] == ROUTER_VERSION
    assert response.json()["version"] == app.version
