import os

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.main import app, require_auth


client = TestClient(app)
HEADERS = {"Authorization": f"Bearer {os.environ['ROUTER_API_TOKEN']}"}


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


def test_models_endpoint_exposes_per_model_reasoning_capabilities():
    response = client.get("/v1/models", headers=HEADERS)

    assert response.status_code == 200
    data = response.json()
    assert data["version"] == 10
    assert data["models"]["codex_terra"]["reasoning_efforts"] == [
        "low",
        "medium",
        "high",
        "xhigh",
        "max",
    ]
    assert data["models"]["antigravity_free"]["reasoning_efforts"] == [
        "low",
        "medium",
        "high",
    ]
    assert data["models"]["antigravity_claude_sonnet"]["reasoning_efforts"] == []


@pytest.mark.parametrize("configured", [None, "", "   ", "CHANGE_ME", "change-me"])
def test_router_auth_fails_closed_when_token_is_not_configured(monkeypatch, configured):
    if configured is None:
        monkeypatch.delenv("ROUTER_API_TOKEN", raising=False)
    else:
        monkeypatch.setenv("ROUTER_API_TOKEN", configured)

    with pytest.raises(HTTPException) as exc_info:
        require_auth("Bearer anything")

    assert exc_info.value.status_code == 503
    assert exc_info.value.detail == "ROUTER_API_TOKEN is not configured"


def test_router_auth_rejects_missing_or_invalid_bearer(monkeypatch):
    monkeypatch.setenv("ROUTER_API_TOKEN", "real-router-token")

    with pytest.raises(HTTPException) as missing:
        require_auth(None)
    assert missing.value.status_code == 401

    with pytest.raises(HTTPException) as invalid:
        require_auth("Bearer wrong-token")
    assert invalid.value.status_code == 401


def test_router_auth_accepts_configured_token(monkeypatch):
    monkeypatch.setenv("ROUTER_API_TOKEN", "real-router-token")
    require_auth("Bearer real-router-token")
