from __future__ import annotations

import asyncio
from copy import deepcopy
from datetime import datetime, timezone

from app.provider_capacity_recovery import ProviderCapacityRecovery


class Result:
    def __init__(self, rows):
        self.rows = deepcopy(rows)

    def fetchall(self):
        return deepcopy(self.rows)

    def fetchone(self):
        return deepcopy(self.rows[0]) if self.rows else None


class Connection:
    def __init__(self, storage):
        self.storage = storage

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, sql, params=None):
        if "SELECT plan_id FROM cp_plan_orchestrations" in sql:
            return Result([{"plan_id": "plan-1"}])
        if "SELECT * FROM cp_plan_work_orders WHERE job_id=%s" in sql:
            job_id = str((params or [""])[0])
            rows = [
                row for row in self.storage.work_orders
                if row.get("job_id") == job_id
            ]
            return Result(rows)
        raise AssertionError(f"unexpected SQL: {sql}")


class Storage:
    def __init__(self, job):
        self.job = deepcopy(job)
        self.work_orders = [
            {
                "plan_id": "plan-1",
                "work_order_id": "WO-1",
                "execution_mode": "agent",
                "state": "blocked",
                "job_id": job["id"],
                "detail": {"reason": "provider_failure_without_fallback"},
            }
        ]

    def connect(self):
        return Connection(self)

    def get(self, job_id):
        return deepcopy(self.job) if job_id == self.job["id"] else None

    def update(self, job_id, **fields):
        assert job_id == self.job["id"]
        self.job.update(deepcopy(fields))


class Store:
    def __init__(self, storage):
        self.storage = storage
        self.plan_status = "blocked"

    def ensure(self):
        return None

    def any_busy_work_order(self):
        return any(
            row["state"] in {"running", "awaiting_merge", "waiting_human"}
            for row in self.storage.work_orders
        )

    def work_orders(self, plan_id):
        return [
            deepcopy(row)
            for row in self.storage.work_orders
            if row["plan_id"] == plan_id
        ]

    def orchestration(self, plan_id):
        if plan_id != "plan-1":
            return None
        return {"plan_id": plan_id, "status": self.plan_status}

    def update_work_order(self, plan_id, work_order_id, **fields):
        row = next(
            row for row in self.storage.work_orders
            if row["plan_id"] == plan_id and row["work_order_id"] == work_order_id
        )
        row.update(deepcopy(fields))

    def update_plan(self, plan_id, *, status):
        assert plan_id == "plan-1"
        self.plan_status = status


class Router:
    def __init__(self, *, fail=False):
        self.fail = fail
        self.payloads = []

    async def route(self, payload):
        self.payloads.append(deepcopy(payload))
        if self.fail:
            raise RuntimeError("No eligible model")
        return {
            "strategy": {
                "budget_mode": "adaptive",
                "executor": {
                    "id": "codex_terra",
                    "provider": "openai",
                    "adapter": "codex_cli",
                    "model": "gpt-5.6-terra",
                    "quota_group": "codex_chatgpt_plus",
                },
            }
        }


class Engine:
    def __init__(self, router):
        self.router = router
        self.enqueued = []

    async def enqueue(self, job_id):
        self.enqueued.append(job_id)


class Coordinator:
    def __init__(self, *, recovered):
        self.recovered = recovered
        self.inputs = []

    async def reconcile(self, state):
        self.inputs.append(deepcopy(state))
        key = "quota:codex_chatgpt_plus"
        telemetry = {
            key: {
                "healthy": True,
                "available": True,
                "authoritative": True,
                "observed_at": "2026-09-20T02:00:00+00:00",
            }
        }
        if not self.recovered:
            return deepcopy(state), [], telemetry
        merged = deepcopy(state)
        merged[key] = {
            "healthy": True,
            "available": True,
            "authoritative": True,
            "observed_at": "2026-09-20T02:00:00+00:00",
            "rehabilitated_from": "2026-09-20T01:00:00+00:00",
        }
        return merged, [key], telemetry


def job():
    return {
        "id": "job-1",
        "project_id": "demo",
        "status": "blocked",
        "source_commit": "a" * 40,
        "task": {"title": "continue healthy work"},
        "repo_analysis": {"estimated_files": 14},
        "route": {"strategy": {"budget_mode": "adaptive"}},
        "progress": {
            "model_calls": 94,
            "iteration": 51,
            "repair_iterations": 37,
            "provider_failures": [
                {
                    "model": "codex_terra",
                    "provider": "openai",
                    "kind": "quota_exhausted",
                }
            ],
            "important_decision_flags": [],
            "unexpected_scope": False,
        },
        "checkpoint": {
            "provider_state": {
                "provider:openai": {
                    "healthy": False,
                    "available": False,
                    "quota_pressure": 1.0,
                    "error_rate": 1.0,
                }
            },
            "route_history": [],
            "approved_decisions": [],
            "work_order": {"id": "WO-1"},
        },
        "result": {"reason": "provider_failure_without_fallback"},
        "error": None,
        "updated_at": datetime(2026, 9, 20, 1, 0, tzinfo=timezone.utc),
    }


def service(*, recovered=True, route_fail=False):
    storage = Storage(job())
    store = Store(storage)
    router = Router(fail=route_fail)
    engine = Engine(router)
    coordinator = Coordinator(recovered=recovered)
    recovery = ProviderCapacityRecovery(
        storage,
        engine,
        store,
        coordinator=coordinator,
    )
    return recovery, storage, store, engine, router, coordinator


def test_authoritative_quota_recovery_reopens_exact_same_job():
    recovery, storage, store, engine, router, coordinator = service()

    result = asyncio.run(recovery.recover_one())

    assert result is not None
    assert result["job_id"] == "job-1"
    assert result["rehabilitated_keys"] == ["quota:codex_chatgpt_plus"]
    assert storage.job["status"] == "queued"
    assert storage.job["progress"]["model_calls"] == 94
    assert storage.job["progress"]["iteration"] == 51
    assert storage.job["progress"]["repair_iterations"] == 37
    assert "provider:openai" not in storage.job["checkpoint"]["provider_state"]
    assert "quota:codex_chatgpt_plus" not in storage.job["checkpoint"]["provider_state"]
    assert storage.work_orders[0]["state"] == "running"
    assert store.plan_status == "executing"
    assert engine.enqueued == ["job-1"]
    assert router.payloads
    assert "provider:openai" not in router.payloads[0]["provider_state"]
    assert "quota:codex_chatgpt_plus" not in router.payloads[0]["provider_state"]
    assert coordinator.inputs[0]["quota:codex_chatgpt_plus"]["failure_kind"] == "quota_exhausted"


def test_no_authoritative_rehabilitation_leaves_job_untouched():
    recovery, storage, store, engine, router, _ = service(recovered=False)
    before = deepcopy(storage.job)

    result = asyncio.run(recovery.recover_one())

    assert result is None
    assert storage.job == before
    assert storage.work_orders[0]["state"] == "blocked"
    assert store.plan_status == "blocked"
    assert engine.enqueued == []
    assert router.payloads == []


def test_fresh_route_failure_leaves_durable_block_untouched():
    recovery, storage, store, engine, router, _ = service(route_fail=True)
    before = deepcopy(storage.job)

    result = asyncio.run(recovery.recover_one())

    assert result is None
    assert storage.job == before
    assert storage.work_orders[0]["state"] == "blocked"
    assert store.plan_status == "blocked"
    assert engine.enqueued == []
    assert len(router.payloads) == 1
