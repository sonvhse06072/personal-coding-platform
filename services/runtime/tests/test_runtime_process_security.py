from __future__ import annotations

import asyncio

import pytest
from fastapi.testclient import TestClient

from app import main, security


def test_linux_runtime_process_is_marked_non_dumpable(monkeypatch) -> None:
    calls: list[tuple[int, int, int, int, int]] = []

    class FakeLibc:
        def prctl(self, *args):
            calls.append(args)
            return 0

    monkeypatch.setattr(security.sys, "platform", "linux")
    monkeypatch.setattr(security.ctypes, "CDLL", lambda *args, **kwargs: FakeLibc())

    security.harden_runtime_process_secret_boundary()

    assert calls == [(security.PR_SET_DUMPABLE, 0, 0, 0, 0)]


def test_runtime_process_hardening_fails_closed_on_linux(monkeypatch) -> None:
    class FakeLibc:
        def prctl(self, *args):
            return -1

    monkeypatch.setattr(security.sys, "platform", "linux")
    monkeypatch.setattr(security.ctypes, "CDLL", lambda *args, **kwargs: FakeLibc())
    monkeypatch.setattr(security.ctypes, "get_errno", lambda: 1)

    with pytest.raises(RuntimeError, match="Unable to harden Runtime process secret boundary"):
        security.harden_runtime_process_secret_boundary()


def test_runtime_process_hardening_is_noop_off_linux(monkeypatch) -> None:
    monkeypatch.setattr(security.sys, "platform", "darwin")

    def fail_if_called(*args, **kwargs):
        raise AssertionError("CDLL must not be called off Linux")

    monkeypatch.setattr(security.ctypes, "CDLL", fail_if_called)
    security.harden_runtime_process_secret_boundary()


def test_lifespan_hardens_process_before_starting_engine_and_orchestrator(monkeypatch) -> None:
    monkeypatch.delenv("PCP_RUNTIME_STARTUP_MODE", raising=False)
    events: list[str] = []

    def fake_harden() -> None:
        events.append("harden")

    async def fake_engine_start() -> None:
        events.append("engine_start")

    async def fake_engine_stop() -> None:
        events.append("engine_stop")

    async def fake_orchestrator_start() -> None:
        events.append("orchestrator_start")

    async def fake_orchestrator_stop() -> None:
        events.append("orchestrator_stop")

    monkeypatch.setattr(main, "harden_runtime_process_secret_boundary", fake_harden)
    monkeypatch.setattr(main.engine, "start", fake_engine_start)
    monkeypatch.setattr(main.engine, "stop", fake_engine_stop)
    monkeypatch.setattr(main.plan_orchestrator, "start", fake_orchestrator_start)
    monkeypatch.setattr(main.plan_orchestrator, "stop", fake_orchestrator_stop)

    async def exercise() -> None:
        async with main.lifespan(main.app):
            events.append("running")

    asyncio.run(exercise())

    assert events == [
        "harden",
        "engine_start",
        "orchestrator_start",
        "running",
        "orchestrator_stop",
        "engine_stop",
    ]


@pytest.mark.parametrize("value", ["", "INSPECT", "disabled", " inspect ", "true"])
def test_invalid_inspection_startup_mode_refuses_to_start(monkeypatch, value) -> None:
    monkeypatch.setenv("PCP_RUNTIME_STARTUP_MODE", value)
    calls = []
    monkeypatch.setattr(main, "harden_runtime_process_secret_boundary", lambda: calls.append("harden"))

    async def forbidden_start():
        raise AssertionError("No engine, plan or publisher startup is allowed")

    for service in (
        main.engine,
        main.plan_orchestrator,
        main.progress_publisher,
        main.job_status_publisher,
    ):
        monkeypatch.setattr(service, "start", forbidden_start)

    async def exercise():
        async with main.lifespan(main.app):
            pytest.fail("Invalid startup mode must not yield an app")

    with pytest.raises(RuntimeError, match="Invalid PCP_RUNTIME_STARTUP_MODE"):
        asyncio.run(exercise())
    assert calls == ["harden"]


def test_inspection_startup_skips_all_services_and_blocks_all_nonhealth_routes(monkeypatch) -> None:
    monkeypatch.setenv("PCP_RUNTIME_STARTUP_MODE", "inspect")
    events = []
    monkeypatch.setattr(main, "harden_runtime_process_secret_boundary", lambda: events.append("harden"))

    async def forbidden_lifecycle():
        raise AssertionError("Inspection must not start or stop durable Runtime services")

    for service in (
        main.engine,
        main.plan_orchestrator,
        main.progress_publisher,
        main.job_status_publisher,
    ):
        monkeypatch.setattr(service, "start", forbidden_lifecycle)
        monkeypatch.setattr(service, "stop", forbidden_lifecycle)

    async def offline_health():
        return False

    monkeypatch.setattr(main.engine.router, "health", offline_health)
    monkeypatch.setattr(main.engine.ddev, "health", offline_health)

    with TestClient(main.app) as client:
        health = client.get("/health")
        assert health.status_code == 200
        assert health.json()["status"] == "degraded"

        async def online_health():
            return True

        monkeypatch.setattr(main.engine.router, "health", online_health)
        monkeypatch.setattr(main.engine.ddev, "health", online_health)
        assert client.get("/health").json()["status"] == "degraded"

        for method, endpoint in (
            ("GET", "/v1/jobs"),
            ("GET", "/v1/plans/example/orchestration"),
            ("GET", "/v1/dashboard"),
            ("GET", "/openapi.json"),
            ("POST", "/v1/jobs"),
            ("POST", "/v1/pm-bridge/poll"),
            ("POST", "/v1/orchestrator/tick"),
            ("POST", "/v1/dashboard/preview/start"),
        ):
            result = client.request(method, endpoint)
            assert result.status_code == 503, (method, endpoint, result.text)
            assert "inspection mode" in result.json()["detail"]

    assert events == ["harden"]


def test_default_runtime_startup_mode_is_normal(monkeypatch) -> None:
    monkeypatch.delenv("PCP_RUNTIME_STARTUP_MODE", raising=False)
    assert main.runtime_startup_mode() == "normal"
    monkeypatch.setenv("PCP_RUNTIME_STARTUP_MODE", "normal")
    assert main.runtime_startup_mode() == "normal"
