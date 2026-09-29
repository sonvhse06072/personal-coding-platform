"""PM-001: real Runtime startup/worker and PostgreSQL; external execution is stubbed."""
from __future__ import annotations

import asyncio
import os
import uuid
from unittest.mock import AsyncMock

import psycopg
from psycopg import sql
from psycopg.rows import dict_row
import pytest
from fastapi.testclient import TestClient

from app import main
from app.config import clear_config_cache
from app.engine import RuntimeEngine
from app.plan_orchestrator import PlanOrchestrator, PlanOrchestratorStore
from app.orchestrator_resume import prepare_orchestrated_job_resume, reopen_orchestrated_job
from app.storage import Storage
from app.work_order_checkpoints import launch_identity
from test_work_order_contract import configure, work_order


class Crash(BaseException):
    """Stop at a committed crash boundary without running later launch steps."""


@pytest.fixture
def launch_db(monkeypatch, tmp_path):
    dsn = os.getenv("PCP_CHECKPOINT_TEST_DSN")
    if not dsn:
        pytest.skip("PCP_CHECKPOINT_TEST_DSN is not configured (disposable PostgreSQL only)")
    schema = "launch_test_" + uuid.uuid4().hex
    with psycopg.connect(dsn, autocommit=True) as conn:
        conn.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))

    class TestStorage(Storage):
        def connect(self):
            return psycopg.connect(dsn, row_factory=dict_row, options=f"-csearch_path={schema}")

    configure(monkeypatch, tmp_path)
    monkeypatch.setattr("app.engine_core.cancel_all_antigravity_runs", AsyncMock())
    storage = TestStorage()
    try:
        storage.init()
        store = PlanOrchestratorStore(storage)
        store.ensure()
        with storage.connect() as conn:
            conn.execute("""CREATE TABLE cp_control_actions (
                id TEXT PRIMARY KEY, plan_id TEXT, work_order_id TEXT, status TEXT, updated_at TIMESTAMPTZ
            )""")
        storage.create_execution_plan({
            "id": "plan-1", "project_id": "demo", "status": "ready", "baseline_revision": "v1",
            "baseline_source_commit": "a" * 40, "ticket": {"id": "TICKET-9", "title": "Launch crash test"},
            "plan": {"work_orders": [work_order(id="WO-1", dependencies=[])]},
        })
        store.register_new_plans()
        yield storage
    finally:
        clear_config_cache()
        with psycopg.connect(dsn, autocommit=True) as conn:
            conn.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema)))


def services(storage):
    # Recreate every service and DB connection, not a fake shared job dictionary.
    storage = type(storage)()
    engine = RuntimeEngine(storage)
    store = PlanOrchestratorStore(storage)
    service = PlanOrchestrator(storage, engine, store=store)
    entered = asyncio.Event()
    calls = []

    async def workspace(**kwargs):
        job = storage.get(kwargs["job_id"])
        assert job["status"] == "routing"
        marker = job["checkpoint"].get("orchestrator_launch")
        if marker:
            assert marker["state"] == "launched"
            assert store.work_orders("plan-1")[0]["state"] == "running"
            assert len([cp for cp in store.checkpoints("plan-1") if cp["kind"] == "started"]) == 1
        calls.append(kwargs["job_id"])
        entered.set()
        await asyncio.Event().wait()  # No workspace, provider or live job is created.

    engine.ddev.create_workspace = workspace
    engine.ddev.cancel = AsyncMock()
    return engine, store, service, entered, calls


def fail(*args, **kwargs):
    raise Crash()


def job_id():
    return launch_identity("plan-1", "WO-1")["job_id"]


def payload():
    return {"project_id": "demo", "_job_id": job_id(), "work_order": work_order(id="WO-1", dependencies=[])}


def held_job(storage):
    engine = RuntimeEngine(storage)
    return engine.create_job(payload(), _orchestration=("plan-1", "WO-1"))


def commit_start(storage):
    engine, store, service, _, _ = services(storage)
    service._checkpoint_transition(
        store.work_orders("plan-1")[0], kind="started", state="running",
        job=storage.get(job_id()), job_id=job_id(), detail={"job_id": job_id()},
    )
    return store


def test_crash_before_started_restart_holds_and_retry_reuses_job(launch_db, monkeypatch):
    async def scenario():
        engine, store, service, _, _ = services(launch_db)
        monkeypatch.setattr(service, "_checkpoint_transition", fail)
        with pytest.raises(Crash):
            await service.tick()
        assert launch_db.get(job_id())["checkpoint"]["orchestrator_launch"]["state"] == "held"
        assert store.work_orders("plan-1")[0]["state"] == "pending"
        assert store.checkpoints("plan-1") == []
        engine, store, service, entered, calls = services(launch_db)
        await engine.start()  # Real startup queued-job scan occurs before orchestrator.
        try:
            await asyncio.sleep(0)
            assert engine.queue.empty() and calls == []
            await service.tick()
            await asyncio.wait_for(entered.wait(), 2)
            await service.tick()
            assert calls == [job_id()]
            assert len(launch_db.list()) == len(store.checkpoints("plan-1")) == 1
        finally:
            await engine.stop()
    asyncio.run(scenario())


@pytest.mark.parametrize("boundary", ["before_release", "after_release"])
def test_crash_after_started_restart_launches_once(launch_db, monkeypatch, boundary):
    async def scenario():
        engine, store, service, _, _ = services(launch_db)
        monkeypatch.setattr(store if boundary == "before_release" else engine,
                            "release_launch" if boundary == "before_release" else "enqueue", fail)
        with pytest.raises(Crash):
            await service.tick()
        assert store.work_orders("plan-1")[0]["state"] == "running"
        history = store.checkpoints("plan-1")
        assert len(history) == 1 and history[0]["kind"] == "started"
        engine, store, service, entered, calls = services(launch_db)
        await engine.start()
        try:
            # Startup and reconciliation can both observe ready/queued. Dedup
            # before yielding to the worker, and again after execution starts.
            await service.tick()
            await service.tick()
            await asyncio.wait_for(entered.wait(), 2)
            await service.tick()
            assert calls == [job_id()]
            assert store.checkpoints("plan-1") == history
            assert len(launch_db.list()) == 1
        finally:
            await engine.stop()
    asyncio.run(scenario())


def test_normal_launch_has_checkpoint_before_real_worker_side_effect(launch_db):
    async def scenario():
        engine, store, service, entered, calls = services(launch_db)
        await engine.start()
        try:
            await service.tick()
            await asyncio.wait_for(entered.wait(), 2)
            assert calls == [job_id()]
            assert len(store.checkpoints("plan-1")) == 1
        finally:
            await engine.stop()
    asyncio.run(scenario())


def test_restart_in_flight_never_auto_resumes_and_explicit_resume_still_works(launch_db):
    async def scenario():
        held_job(launch_db)
        store = commit_start(launch_db)
        store.release_launch("plan-1", "WO-1", job_id())
        # Persist the real execution-entry claim, then discard the process.
        launch_db.claim_orchestrated_launch(job_id())
        engine, store, service, entered, calls = services(launch_db)
        await engine.start()
        try:
            assert launch_db.get(job_id())["status"] == "interrupted"
            engine.ddev.cancel.assert_awaited_once_with(job_id=job_id())
            await service.tick()
            await asyncio.sleep(0)
            assert calls == [] and engine.queue.empty()
            assert launch_db.get(job_id())["status"] == "interrupted"
            context = prepare_orchestrated_job_resume(store, job_id())
            await engine.resume(job_id())
            reopen_orchestrated_job(store, context, job_id())
            await asyncio.wait_for(entered.wait(), 2)
            assert calls == [job_id()]
        finally:
            await engine.stop()
    asyncio.run(scenario())


def test_standalone_queued_startup_is_unchanged(launch_db):
    async def scenario():
        engine, _, _, entered, calls = services(launch_db)
        standalone = engine.create_job({"project_id": "demo", "task": {"title": "manual", "description": "test"}})
        # Standalone execution has no new claim; observe the original queued path.
        async def workspace(**kwargs):
            assert launch_db.get(standalone)["status"] == "queued"
            calls.append(kwargs["job_id"])
            entered.set()
            await asyncio.Event().wait()
        engine.ddev.create_workspace = workspace
        await engine.start()
        try:
            await asyncio.wait_for(entered.wait(), 2)
            assert calls == [standalone]
            assert "orchestrator_launch" not in launch_db.get(standalone)["checkpoint"]
        finally:
            await engine.stop()
    asyncio.run(scenario())


def test_restart_after_actual_worker_entry_keeps_interruption(launch_db):
    async def scenario():
        engine, store, service, entered, calls = services(launch_db)
        await engine.start()
        try:
            await service.tick()
            await asyncio.wait_for(entered.wait(), 2)
            assert calls == [job_id()]
            assert launch_db.get(job_id())["status"] == "routing"
        finally:
            await engine.stop()
        assert launch_db.get(job_id())["status"] == "interrupted"
        engine, store, service, _, calls = services(launch_db)
        await engine.start()
        try:
            await service.tick()
            await asyncio.sleep(0)
            assert calls == [] and engine.queue.empty()
            assert launch_db.get(job_id())["status"] == "interrupted"
        finally:
            await engine.stop()
    asyncio.run(scenario())


def test_held_job_rejects_enqueue_direct_run_and_unproven_release(launch_db):
    held_job(launch_db)
    engine, store, service, _, calls = services(launch_db)
    with pytest.raises(RuntimeError, match="held"):
        asyncio.run(engine.enqueue(job_id()))
    with pytest.raises(RuntimeError, match="held"):
        asyncio.run(engine.run_job(job_id()))
    store.update_work_order("plan-1", "WO-1", state="running", job_id=job_id())
    with pytest.raises(RuntimeError, match="started checkpoint"):
        store.release_launch("plan-1", "WO-1", job_id())
    assert launch_db.get(job_id())["checkpoint"]["orchestrator_launch"]["state"] == "held"
    assert engine.queue.empty() and calls == []


def test_release_write_failure_rolls_back_and_retry_recovers(launch_db, monkeypatch):
    held_job(launch_db)
    store = commit_start(launch_db)
    connect = store.storage.connect
    class Connection:
        def __enter__(self):
            self.conn = connect()
            return self
        def __exit__(self, *args):
            return self.conn.__exit__(*args)
        def execute(self, query, args=None):
            result = self.conn.execute(query, args)
            if "UPDATE cp_jobs" in query:
                raise RuntimeError("release persistence failure")
            return result
        def commit(self):
            self.conn.commit()
    with monkeypatch.context() as patch:
        patch.setattr(store.storage, "connect", Connection)
        with pytest.raises(RuntimeError, match="release persistence failure"):
            store.release_launch("plan-1", "WO-1", job_id())
    assert launch_db.get(job_id())["checkpoint"]["orchestrator_launch"]["state"] == "held"
    assert len(store.checkpoints("plan-1")) == 1
    assert store.release_launch("plan-1", "WO-1", job_id())
    before = launch_db.get(job_id())
    assert store.release_launch("plan-1", "WO-1", job_id())
    assert launch_db.get(job_id()) == before


def test_execution_claim_failure_never_reaches_workspace(launch_db, monkeypatch):
    held_job(launch_db)
    store = commit_start(launch_db)
    store.release_launch("plan-1", "WO-1", job_id())
    engine, _, _, _, calls = services(launch_db)
    def broken(job_id):
        raise RuntimeError("execution claim persistence failure")
    monkeypatch.setattr(engine.storage, "claim_orchestrated_launch", broken)
    with pytest.raises(RuntimeError, match="claim persistence failure"):
        asyncio.run(engine.run_job(job_id()))
    row = launch_db.get(job_id())
    assert row["status"] == "queued"
    assert row["checkpoint"]["orchestrator_launch"]["state"] == "ready"
    assert calls == []


@pytest.mark.parametrize("committed", [False, True])
def test_hold_creation_failure_never_makes_unheld_job(launch_db, monkeypatch, committed):
    create = launch_db.create
    def broken(row):
        if committed:
            create(row)
        raise RuntimeError("hold persistence failure")
    with monkeypatch.context() as patch:
        patch.setattr(launch_db, "create", broken)
        with pytest.raises(RuntimeError, match="hold persistence failure"):
            held_job(launch_db)
    row = launch_db.get(job_id())
    assert row is None or row["checkpoint"]["orchestrator_launch"]["state"] == "held"
    assert held_job(launch_db) == job_id()
    assert len(launch_db.list()) == 1


def test_public_job_payload_cannot_select_launch_reservation(launch_db, monkeypatch):
    monkeypatch.setattr(main, "engine", RuntimeEngine(launch_db))
    monkeypatch.setattr(main, "storage", launch_db)
    monkeypatch.setenv("RUNTIME_API_TOKEN", "launch-test-token")
    response = TestClient(main.app).post("/v1/jobs", headers={"Authorization": "Bearer launch-test-token"}, json={
        **payload(), "auto_run": False, "_orchestration": ["plan-1", "WO-1"],
        "checkpoint": {"orchestrator_launch": {**launch_identity("plan-1", "WO-1"), "state": "ready"}},
    })
    assert response.status_code == 200
    standalone = response.json()["id"]
    assert standalone != job_id()
    assert "orchestrator_launch" not in launch_db.get(standalone)["checkpoint"]


def test_deterministic_collision_cannot_adopt_unreserved_job(launch_db):
    RuntimeEngine(launch_db).create_job(payload())
    with pytest.raises(RuntimeError, match="reservation"):
        held_job(launch_db)
    assert len(launch_db.list()) == 1


@pytest.mark.parametrize("field,value", [("job_id", "wrong"), ("plan_id", "other"), ("state", "unknown")])
def test_corrupt_reservation_fails_closed_at_startup(launch_db, field, value):
    held_job(launch_db)
    checkpoint = launch_db.get(job_id())["checkpoint"]
    checkpoint["orchestrator_launch"][field] = value
    launch_db.update(job_id(), checkpoint=checkpoint)
    engine, _, _, _, calls = services(launch_db)
    with pytest.raises(RuntimeError, match="reservation"):
        asyncio.run(engine.start())
    assert calls == [] and engine.queue.empty()
