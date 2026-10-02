from __future__ import annotations

import asyncio
from contextlib import contextmanager
from copy import deepcopy
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app import main as runtime_main
from app.engine import RuntimeEngine
from app.orchestrator_resume import prepare_orchestrated_job_resume, reopen_orchestrated_job
from app.schemas import JobRunRequest, JobSourceAdvanceRequest


class Result:
    def __init__(self, row):
        self.row = row

    def fetchone(self):
        return deepcopy(self.row) if self.row is not None else None


class Connection:
    def __init__(self, storage):
        self.storage = storage

    def execute(self, query, params=None):
        assert "FROM cp_plan_work_orders WHERE job_id=%s" in query
        job_id = (params or [None])[0]
        row = next(
            (item for item in self.storage.tracked if item.get("job_id") == job_id),
            None,
        )
        return Result(row)


class Storage:
    def __init__(self, tracked):
        self.tracked = tracked

    @contextmanager
    def connect(self):
        yield Connection(self)


class Store:
    def __init__(self, tracked, plan_status="blocked"):
        self.storage = Storage([deepcopy(item) for item in tracked])
        self.plan_status = plan_status
        self.work_order_updates = []
        self.plan_updates = []

    def ensure(self):
        return None

    def orchestration(self, plan_id):
        return {"plan_id": plan_id, "status": self.plan_status}

    def update_work_order(self, plan_id, work_order_id, **fields):
        self.work_order_updates.append((plan_id, work_order_id, deepcopy(fields)))
        row = next(
            item for item in self.storage.tracked
            if item["plan_id"] == plan_id and item["work_order_id"] == work_order_id
        )
        row.update(deepcopy(fields))

    def update_plan(self, plan_id, *, status):
        self.plan_updates.append((plan_id, status))
        self.plan_status = status


class RuntimeStorage:
    def __init__(self, row):
        self.rows = {row["id"]: deepcopy(row)}

    def get(self, job_id):
        row = self.rows.get(job_id)
        return deepcopy(row) if row else None

    def update(self, job_id, **fields):
        self.rows[job_id].update(deepcopy(fields))


def tracked(*, mode="agent", state="blocked"):
    return {
        "plan_id": "pm-gh-1",
        "work_order_id": "WO-1",
        "execution_mode": mode,
        "state": state,
        "job_id": "job-1",
        "detail": {"reason": "old block", "job_id": "job-1"},
    }


def failed_job_row():
    return {
        "id": "job-1",
        "project_id": "demo",
        "status": "failed",
        "source_commit": "a" * 40,
        "workspace": "/workspaces/job-1",
        "task": {"title": "Recover orchestrated job"},
        "repo_analysis": {"estimated_files": 2},
        "progress": {"model_calls": 3, "input_tokens": 100},
        "checkpoint": {"provider_state": {}, "route_history": []},
    }


def test_blocked_agent_job_reopens_exact_work_order_and_plan() -> None:
    store = Store([tracked()])

    context = prepare_orchestrated_job_resume(store, "job-1")
    assert context == {
        "plan_id": "pm-gh-1",
        "work_order_id": "WO-1",
        "reopen": True,
        "detail": {"reason": "old block", "job_id": "job-1"},
    }

    reopen_orchestrated_job(store, context, "job-1")

    assert store.storage.tracked[0]["state"] == "running"
    assert store.storage.tracked[0]["detail"]["reason"] == "old block"
    assert store.storage.tracked[0]["detail"]["resume_state"] == "explicit_job_resume"
    assert store.plan_status == "executing"


def test_running_agent_job_needs_no_orchestration_reopen() -> None:
    store = Store([tracked(state="running")], plan_status="executing")

    context = prepare_orchestrated_job_resume(store, "job-1")
    assert context is not None
    assert context["reopen"] is False

    reopen_orchestrated_job(store, context, "job-1")
    assert store.work_order_updates == []
    assert store.plan_updates == []


def test_operator_work_order_fails_closed() -> None:
    store = Store([tracked(mode="operator")])

    with pytest.raises(RuntimeError, match="Operator-only"):
        prepare_orchestrated_job_resume(store, "job-1")

    assert store.work_order_updates == []
    assert store.plan_updates == []


def test_non_orchestrated_job_is_unchanged() -> None:
    store = Store([])
    assert prepare_orchestrated_job_resume(store, "job-free") is None


def test_failed_orchestrated_source_advance_is_authorized_without_reopening(monkeypatch) -> None:
    store = Store([tracked()])
    calls = []

    class Engine:
        async def advance_direct_job_source(
            self,
            job_id,
            *,
            expected_old_source,
            expected_new_source,
            _allow_failed_orchestrated_recovery=False,
        ):
            calls.append({
                "job_id": job_id,
                "old": expected_old_source,
                "new": expected_new_source,
                "allow_failed": _allow_failed_orchestrated_recovery,
            })
            row = failed_job_row()
            row["source_commit"] = expected_new_source
            return row

    monkeypatch.setattr(runtime_main, "engine", Engine())
    monkeypatch.setattr(
        runtime_main,
        "plan_orchestrator",
        SimpleNamespace(store=store),
    )
    monkeypatch.setattr(runtime_main, "view", lambda row: row)

    result = asyncio.run(
        runtime_main.advance_job_source(
            "job-1",
            JobSourceAdvanceRequest(
                expected_old_source="a" * 40,
                expected_new_source="b" * 40,
            ),
        )
    )

    assert result["status"] == "failed"
    assert result["source_commit"] == "b" * 40
    assert calls == [{
        "job_id": "job-1",
        "old": "a" * 40,
        "new": "b" * 40,
        "allow_failed": True,
    }]
    assert store.work_order_updates == []
    assert store.plan_updates == []
    assert store.storage.tracked[0]["state"] == "blocked"
    assert store.plan_status == "blocked"


def test_failed_orchestrated_job_reopens_only_after_engine_resume_succeeds(monkeypatch) -> None:
    store = Store([tracked()])
    runtime_storage = RuntimeStorage(failed_job_row())
    engine = RuntimeEngine(runtime_storage)
    queued = []

    async def enqueue(job_id):
        queued.append(job_id)

    engine.enqueue = enqueue
    monkeypatch.setattr(runtime_main, "engine", engine)
    monkeypatch.setattr(runtime_main, "plan_orchestrator", SimpleNamespace(store=store))
    monkeypatch.setattr(runtime_main, "view", lambda row: row)

    result = asyncio.run(runtime_main.run_job("job-1"))

    assert result["id"] == "job-1"
    assert result["status"] == "queued"
    assert queued == ["job-1"]
    assert runtime_storage.get("job-1")["workspace"] == "/workspaces/job-1"
    assert runtime_storage.get("job-1")["source_commit"] == "a" * 40
    assert runtime_storage.get("job-1")["progress"] == {"model_calls": 3, "input_tokens": 100}
    assert store.storage.tracked[0]["state"] == "running"
    assert store.plan_status == "executing"


def test_orchestrated_resume_failure_leaves_plan_and_work_order_blocked(monkeypatch) -> None:
    store = Store([tracked()])
    row = failed_job_row()
    row["status"] = "cancelled"
    runtime_storage = RuntimeStorage(row)
    engine = RuntimeEngine(runtime_storage)

    monkeypatch.setattr(runtime_main, "engine", engine)
    monkeypatch.setattr(runtime_main, "plan_orchestrator", SimpleNamespace(store=store))

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(runtime_main.run_job("job-1"))

    assert exc_info.value.status_code == 409
    assert runtime_storage.get("job-1")["status"] == "cancelled"
    assert store.storage.tracked[0]["state"] == "blocked"
    assert store.plan_status == "blocked"


def test_failed_orchestrated_reroute_failure_leaves_plan_and_work_order_blocked(monkeypatch) -> None:
    store = Store([tracked()])
    runtime_storage = RuntimeStorage(failed_job_row())
    engine = RuntimeEngine(runtime_storage)

    class Router:
        async def route(self, payload):
            raise RuntimeError("router unavailable")

    engine.router = Router()
    monkeypatch.setattr(runtime_main, "engine", engine)
    monkeypatch.setattr(runtime_main, "plan_orchestrator", SimpleNamespace(store=store))

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(runtime_main.run_job("job-1", JobRunRequest(reroute=True)))

    assert exc_info.value.status_code == 409
    assert runtime_storage.get("job-1")["status"] == "failed"
    assert store.storage.tracked[0]["state"] == "blocked"
    assert store.plan_status == "blocked"
