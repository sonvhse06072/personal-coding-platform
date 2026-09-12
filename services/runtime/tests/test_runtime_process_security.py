from __future__ import annotations

import asyncio

import pytest

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
