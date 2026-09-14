from __future__ import annotations

import asyncio

from app import router_client


class FakeCoordinator:
    def __init__(self) -> None:
        self.calls = 0

    async def enrich(self, payload):
        self.calls += 1
        updated = dict(payload)
        state = dict(updated.get("provider_state") or {})
        state["quota:model:codex_terra"] = {
            "healthy": True,
            "available": True,
            "quota_pressure": 0.91,
            "error_rate": 0.0,
            "latency_ms": 0,
            "predicted_success": None,
        }
        updated["provider_state"] = state
        return updated


class FakeResponse:
    is_success = True

    def raise_for_status(self):
        return None

    def json(self):
        return {"ok": True}


class FakeAsyncClient:
    calls = []

    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def post(self, url, *, json, headers):
        self.__class__.calls.append((url, json, headers))
        return FakeResponse()

    async def get(self, url):
        return FakeResponse()


def test_route_and_staff_receive_quota_preflight_but_reassess_does_not(monkeypatch):
    coordinator = FakeCoordinator()
    FakeAsyncClient.calls = []
    monkeypatch.setattr(router_client, "quota_coordinator", coordinator)
    monkeypatch.setattr(router_client.httpx, "AsyncClient", FakeAsyncClient)
    client = router_client.RouterClient()

    asyncio.run(client.route({"job_id": "j1", "provider_state": {}}))
    asyncio.run(client.staff({"request_id": "p1", "provider_state": {}}))
    asyncio.run(client.reassess({"job_id": "j1", "provider_state": {}}))

    assert coordinator.calls == 2
    route_payload = FakeAsyncClient.calls[0][1]
    staff_payload = FakeAsyncClient.calls[1][1]
    reassess_payload = FakeAsyncClient.calls[2][1]
    assert route_payload["provider_state"]["quota:model:codex_terra"]["quota_pressure"] == 0.91
    assert staff_payload["provider_state"]["quota:model:codex_terra"]["quota_pressure"] == 0.91
    assert "quota:model:codex_terra" not in reassess_payload["provider_state"]
