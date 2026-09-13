from __future__ import annotations

from contextlib import contextmanager
from copy import deepcopy

import pytest

from app.orchestrator_resume import prepare_orchestrated_job_resume, reopen_orchestrated_job


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


def tracked(*, mode="agent", state="blocked"):
    return {
        "plan_id": "pm-gh-1",
        "work_order_id": "WO-1",
        "execution_mode": mode,
        "state": state,
        "job_id": "job-1",
        "detail": {"reason": "old block", "job_id": "job-1"},
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
