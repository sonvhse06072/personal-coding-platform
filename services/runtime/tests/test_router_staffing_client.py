from __future__ import annotations

import asyncio

from app import router_client as router_client_module
from app.router_client import RouterClient


class FakeResponse:
    def __init__(self, payload: dict) -> None:
        self.payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self.payload


class FakeAsyncClient:
    def __init__(self, capture: dict, *, timeout: int) -> None:
        self.capture = capture
        self.capture["timeout"] = timeout

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def post(self, url: str, *, json: dict, headers: dict) -> FakeResponse:
        self.capture.update({"url": url, "json": json, "headers": headers})
        return FakeResponse({
            "request_id": json["request_id"],
            "project_id": json["project_id"],
            "role": json["role"],
            "profile": json["profile"],
            "choice": {"id": "codex_plus"},
        })


def test_router_client_staff_posts_only_to_staffing_endpoint(monkeypatch) -> None:
    capture: dict = {}
    monkeypatch.setenv("ROUTER_URL", "http://router.test:8090/")
    monkeypatch.setenv("ROUTER_API_TOKEN", "router-secret")
    monkeypatch.setattr(
        router_client_module.httpx,
        "AsyncClient",
        lambda *, timeout: FakeAsyncClient(capture, timeout=timeout),
    )

    payload = {
        "request_id": "pm-plan-1",
        "project_id": "demo",
        "role": "product_manager",
        "profile": "standard",
        "provider_state": {},
    }
    result = asyncio.run(RouterClient().staff(payload))

    assert capture["url"] == "http://router.test:8090/v1/staff"
    assert capture["json"] == payload
    assert capture["headers"] == {"Authorization": "Bearer router-secret"}
    assert capture["timeout"] == 30
    assert result["choice"]["id"] == "codex_plus"
