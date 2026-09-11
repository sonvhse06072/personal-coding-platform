import asyncio

import httpx

from app.adapters.antigravity import cancel_all_antigravity_runs


def test_cancel_all_antigravity_runs_on_recovery(monkeypatch):
    calls = []

    class FakeResponse:
        def raise_for_status(self):
            return None
        def json(self):
            return {"cancelled": 2}

    class FakeClient:
        def __init__(self, *args, **kwargs): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *args): return None
        async def post(self, url, *args, **kwargs):
            calls.append(url)
            return FakeResponse()

    monkeypatch.setenv("ANTIGRAVITY_BRIDGE_TOKEN", "secret")
    monkeypatch.setattr(httpx, "AsyncClient", FakeClient)
    assert asyncio.run(cancel_all_antigravity_runs()) == 2
    assert calls == ["http://host.docker.internal:8792/cancel-all"]
