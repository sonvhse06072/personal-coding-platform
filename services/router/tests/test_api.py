import os

from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)
HEADERS = {"Authorization": f"Bearer {os.getenv('ROUTER_API_TOKEN', 'change-me')}"}


def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_route_endpoint():
    payload = {
        "job_id": "api-1",
        "project_id": "default",
        "repository": "example",
        "source_commit": "abcd1234",
        "task": {"title": "Change a label"},
        "repo": {"estimated_files": 1, "affected_components": 1, "existing_pattern": True},
    }
    response = client.post("/v1/route", headers=HEADERS, json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["job_id"] == "api-1"
    assert "strategy" in data
