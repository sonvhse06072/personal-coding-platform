from __future__ import annotations

import asyncio

from app.engine_telemetry import TelemetryRouterProxy


class Delegate:
    def __init__(self) -> None:
        self.payload = None

    async def route(self, payload):
        self.payload = payload
        return {"ok": True, "payload": payload}

    async def health(self):
        return True

    async def staff(self, payload):
        return payload

    async def reassess(self, payload):
        return payload


class Storage:
    def __init__(self, *, fail: bool = False, sufficient: bool = True) -> None:
        self.fail = fail
        self.sufficient = sufficient

    def get(self, job_id):
        return {
            "id": job_id,
            "checkpoint": {"work_order": {"requested_role": "backend_developer"}},
        }

    def calibration_hint(self, **kwargs):
        if self.fail:
            raise RuntimeError("telemetry unavailable")
        return {
            "sample_size": 7 if self.sufficient else 2,
            "minimum_sample_size": 5,
            "sufficient_sample": self.sufficient,
            "resource_multipliers": {"max_model_calls": 1.2} if self.sufficient else {},
            "model_success": {
                "codex_terra": {"sample_size": 7, "success_rate": 0.91}
            } if self.sufficient else {},
        }


def payload() -> dict:
    return {
        "job_id": "job-1",
        "project_id": "project-a",
        "source_commit": "abcd1234",
        "task": {"title": "Task", "task_type": "bugfix"},
        "repo": {},
        "provider_state": {
            "provider:openai": {"healthy": True, "available": True},
        },
    }


def test_proxy_passes_observed_resource_and_model_success_evidence() -> None:
    delegate = Delegate()
    proxy = TelemetryRouterProxy(delegate, Storage())

    asyncio.run(proxy.route(payload()))

    sent = delegate.payload
    assert sent is not None
    assert sent["calibration"]["sample_size"] == 7
    assert sent["calibration"]["resource_multipliers"]["max_model_calls"] == 1.2
    assert sent["provider_state"]["codex_terra"]["predicted_success"] == 0.91
    assert sent["provider_state"]["provider:openai"]["available"] is True


def test_proxy_does_not_inject_model_success_from_sparse_samples() -> None:
    delegate = Delegate()
    proxy = TelemetryRouterProxy(delegate, Storage(sufficient=False))

    asyncio.run(proxy.route(payload()))

    sent = delegate.payload
    assert sent is not None
    assert sent["calibration"]["sample_size"] == 2
    assert "codex_terra" not in sent["provider_state"]


def test_telemetry_read_failure_falls_back_to_policy_defaults_instead_of_failing_routing() -> None:
    delegate = Delegate()
    proxy = TelemetryRouterProxy(delegate, Storage(fail=True))

    result = asyncio.run(proxy.route(payload()))

    assert result["ok"] is True
    sent = delegate.payload
    assert sent is not None
    assert sent["calibration"]["sample_size"] == 0
    assert sent["calibration"]["resource_multipliers"] == {}
