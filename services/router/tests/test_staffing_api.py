import os

from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)
HEADERS = {"Authorization": f"Bearer {os.environ['ROUTER_API_TOKEN']}"}


def staffing_payload() -> dict:
    return {
        "request_id": "pm-api-1",
        "project_id": "default",
        "role": "product_manager",
        "profile": "standard",
        "semantic": {
            "reasoning_requirement": 80,
            "context_requirement": 60,
            "ambiguity": 40,
        },
    }


def test_staffing_endpoint_returns_router_selected_pm_agent() -> None:
    response = client.post("/v1/staff", headers=HEADERS, json=staffing_payload())
    assert response.status_code == 200
    data = response.json()
    assert data["request_id"] == "pm-api-1"
    assert data["role"] == "product_manager"
    assert data["choice"]["id"] == "codex_terra"
    assert data["choice"]["reasoning_effort"] == "low"
    assert data["policy_version"] == 19
    assert data["registry_version"] == 9


def test_staffing_endpoint_rejects_unknown_role() -> None:
    payload = staffing_payload()
    payload["role"] = "invented_manager"
    response = client.post("/v1/staff", headers=HEADERS, json=payload)
    assert response.status_code == 422
    assert "Unknown or unconfigured logical role" in response.json()["detail"]


def test_staffing_endpoint_rejects_direct_model_override() -> None:
    payload = staffing_payload()
    payload["model_id"] = "codex_sol"
    response = client.post("/v1/staff", headers=HEADERS, json=payload)
    assert response.status_code == 422
