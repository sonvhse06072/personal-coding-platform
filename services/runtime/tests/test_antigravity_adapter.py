import asyncio
import json
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


def test_antigravity_trusted_local_payload_is_execute_repair_only(monkeypatch, tmp_path: Path):
    payloads: list[dict] = []

    class FakeResponse:
        def raise_for_status(self):
            return None
        def json(self):
            return {
                "returncode": 0,
                "stderr": "",
                "stdout": '{"status":"SUCCESS","response":"done","usage":{}}',
                "payload": {"status": "SUCCESS", "response": "done", "usage": {}},
            }

    class FakeClient:
        def __init__(self, *args, **kwargs): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *args): return None
        async def post(self, *args, **kwargs):
            payloads.append(dict(kwargs["json"]))
            return FakeResponse()

    monkeypatch.setenv("ANTIGRAVITY_BRIDGE_TOKEN", "secret")
    monkeypatch.setattr(httpx, "AsyncClient", FakeClient)
    monkeypatch.setattr(
        "app.adapters.antigravity.trusted_local_developer_enabled",
        lambda workspace, mode, adapter=None: mode in {"execute", "repair"} and adapter == "antigravity_host",
    )

    asyncio.run(
        AntigravityAdapter("auto").run(
            workspace=tmp_path, prompt="implement", mode="execute", timeout=30
        )
    )
    asyncio.run(
        AntigravityAdapter("auto").run(
            workspace=tmp_path, prompt="inspect", mode="evaluate", timeout=30
        )
    )

    assert payloads[0]["trusted_local_developer"] is True
    assert payloads[1]["trusted_local_developer"] is False


def test_flash_medium_omits_stale_reasoning_effort(monkeypatch, tmp_path: Path):
    payloads: list[dict] = []

    class FakeResponse:
        def raise_for_status(self):
            return None
        def json(self):
            return {
                "returncode": 0,
                "stderr": "",
                "stdout": '{"status":"SUCCESS","response":"done","usage":{}}',
                "payload": {"status": "SUCCESS", "response": "done", "usage": {}},
            }

    class FakeClient:
        def __init__(self, *args, **kwargs): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *args): return None
        async def post(self, *args, **kwargs):
            payloads.append(dict(kwargs["json"]))
            return FakeResponse()

    monkeypatch.setenv("ANTIGRAVITY_BRIDGE_TOKEN", "secret")
    monkeypatch.setattr(httpx, "AsyncClient", FakeClient)

    run = asyncio.run(
        AntigravityAdapter("gemini-3.8-flash-medium", "low").run(
            workspace=tmp_path,
            prompt="evaluate",
            mode="evaluate",
            timeout=30,
        )
    )

    assert run.returncode == 0
    assert payloads
    assert payloads[0]["model"] == "gemini-3.8-flash-medium"
    assert "effort" not in payloads[0]


def test_antigravity_stream_persists_only_completed_response(monkeypatch, tmp_path: Path):
    events: list[dict] = []

    class FakeStreamResponse:
        status_code = 200

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        def raise_for_status(self):
            return None

        async def aiter_lines(self):
            rows = [
                {"event": "init", "model": "claude-sonnet-4-6"},
                {
                    "event": "step_update",
                    "step_update": {
                        "step_type": "agent_response",
                        "state": "ACTIVE",
                        "text_delta": "huma",
                    },
                },
                {
                    "event": "step_update",
                    "step_update": {
                        "step_type": "agent_response",
                        "state": "ACTIVE",
                        "text_delta": "n_decision",
                    },
                },
                {
                    "event": "result",
                    "result": {
                        "status": "SUCCESS",
                        "response": "human_decision",
                        "usage": {"input_tokens": 10, "output_tokens": 2},
                    },
                },
                {
                    "bridge_event": "result",
                    "returncode": 0,
                    "stderr": "",
                    "timed_out": False,
                },
            ]
            for row in rows:
                yield json.dumps(row)

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        def stream(self, *args, **kwargs):
            return FakeStreamResponse()

    monkeypatch.setenv("ANTIGRAVITY_BRIDGE_TOKEN", "secret")
    monkeypatch.setattr(httpx, "AsyncClient", FakeClient)
    monkeypatch.setattr("app.adapters.antigravity.emit_developer_event", events.append)

    run = asyncio.run(
        AntigravityAdapter("claude-sonnet-4-6").run(
            workspace=tmp_path,
            prompt="evaluate",
            mode="evaluate",
            timeout=30,
        )
    )

    assert run.returncode == 0
    assert run.output == "human_decision"
    messages = [event for event in events if event and event.get("event_type") == "developer_message"]
    assert len(messages) == 1
    assert messages[0]["data"]["text"] == "human_decision"
    assert "huma" not in [event.get("data", {}).get("text") for event in events]
    assert "n_decision" not in [event.get("data", {}).get("text") for event in events]
