import asyncio
from pathlib import Path

import httpx

from app.adapters.antigravity import AntigravityAdapter


class _Response:
    def raise_for_status(self):
        return None

    def json(self):
        return {
            "returncode": 0,
            "stderr": "",
            "stdout": '{"status":"SUCCESS","response":"done","usage":{}}',
            "payload": {"status": "SUCCESS", "response": "done", "usage": {}},
        }


def test_flash_medium_omits_legacy_router_reasoning_effort(monkeypatch, tmp_path: Path):
    captured = {}

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def post(self, url, *args, **kwargs):
            captured.update(kwargs["json"])
            return _Response()

    monkeypatch.setenv("ANTIGRAVITY_BRIDGE_TOKEN", "secret")
    monkeypatch.setattr(httpx, "AsyncClient", FakeClient)

    run = asyncio.run(
        AntigravityAdapter("gemini-3.8-flash-medium", "low").run(
            workspace=tmp_path,
            prompt="bounded prompt",
            mode="evaluate",
            timeout=30,
        )
    )

    assert run.returncode == 0
    assert captured["model"] == "gemini-3.8-flash-medium"
    assert "effort" not in captured


def test_antigravity_omits_effort_when_router_leaves_it_unset(monkeypatch, tmp_path: Path):
    captured = {}

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def post(self, url, *args, **kwargs):
            captured.update(kwargs["json"])
            return _Response()

    monkeypatch.setenv("ANTIGRAVITY_BRIDGE_TOKEN", "secret")
    monkeypatch.setattr(httpx, "AsyncClient", FakeClient)

    asyncio.run(
        AntigravityAdapter("gemini-3.1-pro-high", None).run(
            workspace=tmp_path,
            prompt="bounded prompt",
            mode="plan",
            timeout=30,
        )
    )

    assert "effort" not in captured


def test_flash_high_keeps_supported_router_reasoning_effort(monkeypatch, tmp_path: Path):
    captured = {}

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def post(self, url, *args, **kwargs):
            captured.update(kwargs["json"])
            return _Response()

    monkeypatch.setenv("ANTIGRAVITY_BRIDGE_TOKEN", "secret")
    monkeypatch.setattr(httpx, "AsyncClient", FakeClient)

    run = asyncio.run(
        AntigravityAdapter("gemini-3.8-flash-high", "medium").run(
            workspace=tmp_path,
            prompt="bounded prompt",
            mode="evaluate",
            timeout=30,
        )
    )

    assert run.returncode == 0
    assert captured["model"] == "gemini-3.8-flash-high"
    assert captured["effort"] == "medium"
