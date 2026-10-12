"""F2d-04B-03: existing Engine worker separated from legacy side effects.

Source-only: no PostgreSQL, provider, Docker, host Antigravity or real startup.
"""
from __future__ import annotations

import asyncio

import pytest

from app import main as runtime_main
from app.engine_core import RuntimeEngineCore
from app.fullpath_fixture_safety import FullPathCandidateNotReady


def _legacy_env(monkeypatch):
    monkeypatch.setenv("PCP_RUNTIME_STARTUP_MODE", "normal")
    monkeypatch.delenv("PCP_FULLPATH_SOURCE_ONLY", raising=False)
    monkeypatch.setenv("PROJECTS_FILE", "/config/projects.yml")
    monkeypatch.setenv("PROJECT_BASELINES_FILE", "/config/project-baselines.yml")
    monkeypatch.setenv("CODING_PROJECTS_ROOT", "/owner/normal")
    monkeypatch.setenv("CODING_WORKSPACES_ROOT", "/owner/workspaces")
    monkeypatch.setenv("CODEX_HOME", "/home/coder/.codex")
    monkeypatch.setenv("DATABASE_URL", "postgresql://db:pw@db:5432/db")


class ForbiddenStorage:
    def __getattr__(self, name):
        raise AssertionError(f"Worker spawn must not touch storage: {name}")


def test_engineering_worker_spawn_has_no_db_or_legacy_recovery(monkeypatch):
    _legacy_env(monkeypatch)
    engine = RuntimeEngineCore(ForbiddenStorage())
    calls = []

    async def worker():
        calls.append("worker")
        await asyncio.Event().wait()

    monkeypatch.setattr(engine, "_worker_loop", worker)

    async def scenario():
        engine._spawn_engineering_worker()
        task = engine.worker_task
        assert task is not None
        await asyncio.sleep(0)
        assert calls == ["worker"]
        with pytest.raises(RuntimeError, match="already started"):
            engine._spawn_engineering_worker()
        assert engine.worker_task is task
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        engine.worker_task = None

    asyncio.run(scenario())


def test_direct_f2_worker_spawn_stops_before_task_even_if_mode_flipped(monkeypatch):
    _legacy_env(monkeypatch)
    monkeypatch.setenv("PROJECTS_FILE", "/fullpath/config/projects.yml")
    engine = RuntimeEngineCore(ForbiddenStorage())
    calls = []

    async def worker():
        calls.append("worker")

    monkeypatch.setattr(engine, "_worker_loop", worker)

    async def scenario():
        with pytest.raises(FullPathCandidateNotReady, match="source-only"):
            engine._spawn_engineering_worker()
        assert engine.worker_task is None

    asyncio.run(scenario())
    assert calls == []


def test_legacy_main_lifespan_start_stop_order_is_preserved(monkeypatch):
    _legacy_env(monkeypatch)
    calls = []
    monkeypatch.setattr(
        runtime_main, "harden_runtime_process_secret_boundary",
        lambda: calls.append("harden"),
    )

    def stub(component, label):
        async def start():
            calls.append(label + ".start")

        async def stop():
            calls.append(label + ".stop")

        monkeypatch.setattr(component, "start", start)
        monkeypatch.setattr(component, "stop", stop)

    stub(runtime_main.engine, "engine")
    stub(runtime_main.plan_orchestrator, "planner")
    stub(runtime_main.progress_publisher, "progress")
    stub(runtime_main.job_status_publisher, "status")

    async def scenario():
        async with runtime_main.lifespan(runtime_main.app):
            calls.append("serving")

    asyncio.run(scenario())
    assert calls == [
        "harden",
        "engine.start", "planner.start", "progress.start", "status.start",
        "serving",
        "status.stop", "progress.stop", "planner.stop", "engine.stop",
    ]


@pytest.mark.parametrize("call", [
    "_start_legacy_control_plane", "_stop_legacy_control_plane",
])
def test_parked_f2_cannot_call_legacy_control_plane_directly(
    monkeypatch, call,
):
    _legacy_env(monkeypatch)
    monkeypatch.setenv("PCP_RUNTIME_STARTUP_MODE", "normal")
    monkeypatch.setenv("CODEX_HOME", "/home/coder/.codex-fullpath")
    events = []

    async def forbidden():
        events.append("legacy-controller")
        raise AssertionError("No legacy scheduler or publisher may start")

    for component in (
        runtime_main.plan_orchestrator,
        runtime_main.progress_publisher,
        runtime_main.job_status_publisher,
    ):
        monkeypatch.setattr(component, "start", forbidden)
        monkeypatch.setattr(component, "stop", forbidden)

    async def scenario():
        with pytest.raises(FullPathCandidateNotReady, match="source-only"):
            await getattr(runtime_main, call)()

    asyncio.run(scenario())
    assert events == []


def test_parked_f2_lifespan_still_blocks_before_engine_and_controllers(
    monkeypatch,
):
    _legacy_env(monkeypatch)
    monkeypatch.setenv("PCP_RUNTIME_STARTUP_MODE", "normal")
    monkeypatch.setenv("PCP_FULLPATH_SOURCE_ONLY", "true")
    events = []
    monkeypatch.setattr(
        runtime_main, "harden_runtime_process_secret_boundary",
        lambda: events.append("harden"),
    )

    async def forbidden():
        events.append("unsafe-start")
        raise AssertionError("Parked F2 must not start workers or controllers")

    monkeypatch.setattr(runtime_main.engine, "start", forbidden)
    monkeypatch.setattr(runtime_main, "_start_legacy_control_plane", forbidden)

    async def scenario():
        with pytest.raises(FullPathCandidateNotReady, match="source-only"):
            async with runtime_main.lifespan(runtime_main.app):
                pytest.fail("Parked F2 lifespan unexpectedly entered")

    asyncio.run(scenario())
    assert events == ["harden"]
