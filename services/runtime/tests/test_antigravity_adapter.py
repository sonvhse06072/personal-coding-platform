import asyncio
from pathlib import Path

import httpx

from app.adapters.antigravity import AntigravityAdapter


def test_antigravity_parses_json_usage(monkeypatch, tmp_path: Path):
    class FakeResponse:
        def raise_for_status(self):
            return None
        def json(self):
            return {
                "returncode": 0,
                "stderr": "",
                "stdout": '{"status":"SUCCESS","response":"done","usage":{"input_tokens":123,"output_tokens":45,"thinking_tokens":9}}',
                "payload": {
                    "status": "SUCCESS",
                    "response": "done",
                    "usage": {"input_tokens": 123, "output_tokens": 45, "thinking_tokens": 9},
                },
            }

    class FakeClient:
        def __init__(self, *args, **kwargs): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *args): return None
        async def post(self, *args, **kwargs): return FakeResponse()

    monkeypatch.setenv("ANTIGRAVITY_BRIDGE_TOKEN", "secret")
    monkeypatch.setattr(httpx, "AsyncClient", FakeClient)
    run = asyncio.run(
        AntigravityAdapter("auto").run(workspace=tmp_path, prompt="do it", mode="execute", timeout=30)
    )
    assert run.returncode == 0
    assert run.output == "done"
    assert run.usage["input_tokens"] == 123
    assert run.usage["output_tokens"] == 45


def test_antigravity_soft_permission_denial_is_not_success(monkeypatch, tmp_path: Path):
    notice = (
        'jetski: no output produced — a tool required the "unsandboxed" permission '
        "that headless mode cannot prompt for, so it was auto-denied."
    )

    class FakeResponse:
        def raise_for_status(self):
            return None
        def json(self):
            return {
                "returncode": 0,
                "stderr": notice,
                "stdout": '{"status":"SUCCESS","response":"","usage":{"input_tokens":10,"output_tokens":2}}',
                "payload": {
                    "status": "SUCCESS",
                    "response": "",
                    "usage": {"input_tokens": 10, "output_tokens": 2},
                },
            }

    class FakeClient:
        def __init__(self, *args, **kwargs): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *args): return None
        async def post(self, *args, **kwargs): return FakeResponse()

    monkeypatch.setenv("ANTIGRAVITY_BRIDGE_TOKEN", "secret")
    monkeypatch.setattr(httpx, "AsyncClient", FakeClient)
    run = asyncio.run(
        AntigravityAdapter("auto").run(workspace=tmp_path, prompt="do it", mode="execute", timeout=30)
    )
    assert run.returncode == 77
    assert run.failure_kind == "permission_denied"
    assert not run.provider_failed
    assert "auto-denied" in (run.failure_message or "")


def test_antigravity_bridge_unavailable_is_provider_failure(monkeypatch, tmp_path: Path):
    class FakeClient:
        def __init__(self, *args, **kwargs): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *args): return None
        async def post(self, *args, **kwargs):
            raise httpx.ConnectError("no bridge")

    monkeypatch.setenv("ANTIGRAVITY_BRIDGE_TOKEN", "secret")
    monkeypatch.setattr(httpx, "AsyncClient", FakeClient)
    run = asyncio.run(
        AntigravityAdapter("auto").run(workspace=tmp_path, prompt="do it", mode="execute", timeout=30)
    )
    assert run.provider_failed
    assert run.failure_kind == "provider_unavailable"


def test_antigravity_cancel_calls_host_bridge_cancel(monkeypatch, tmp_path: Path):
    cancelled_run_ids: list[str] = []

    class FakeResponse:
        def raise_for_status(self):
            return None
        def json(self):
            return {"cancelled": True}

    class FakeClient:
        def __init__(self, *args, **kwargs): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *args): return None
        async def post(self, url, *args, **kwargs):
            if url.endswith("/cancel"):
                cancelled_run_ids.append(kwargs["json"]["run_id"])
                return FakeResponse()
            await asyncio.Event().wait()
            raise AssertionError("unreachable")

    monkeypatch.setenv("ANTIGRAVITY_BRIDGE_TOKEN", "secret")
    monkeypatch.setattr(httpx, "AsyncClient", FakeClient)

    async def scenario():
        task = asyncio.create_task(
            AntigravityAdapter("auto").run(
                workspace=tmp_path, prompt="do it", mode="execute", timeout=30
            )
        )
        await asyncio.sleep(0)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    asyncio.run(scenario())
    assert len(cancelled_run_ids) == 1
    assert cancelled_run_ids[0]
