from __future__ import annotations

import asyncio
from copy import deepcopy
from types import SimpleNamespace

from app.engine import WorkOrderRouterProxy
from app.legacy_adaptive_recovery import LegacyAdaptiveRecovery
from app.work_order import WorkOrder


RAW_WORK_ORDER = {
    "id": "DEC-025C-1-recovery-tooling-r2",
    "parent_ticket": "GH-5",
    "objective": "Complete the bounded recovery rehearsal tooling",
    "baseline_revision": "mvp-v1-2026-09-13",
    "source_references": [{"path": "docs/PROJECT-CONTEXT.md"}],
    "in_scope": ["recovery rehearsal tooling"],
    "out_of_scope": ["production deployment"],
    "acceptance_criteria": [{"id": "AC1", "description": "Deterministic checks pass"}],
    "constraints": [],
    "requested_role": "developer",
    "verification": {"required_phases": ["targeted_tests", "full_tests"]},
    "risk": {"level": "high", "flags": []},
    "budget": {
        "max_profile": "complex",
        "max_model_calls": 15,
        "max_repair_iterations": 4,
        "max_wall_time_minutes": 60,
        "max_changed_files": 30,
    },
    "dependencies": [],
}


def fresh_route():
    return {
        "strategy": {
            "profile": "complex",
            "budget": {
                "max_model_calls": 40,
                "max_tool_calls": 400,
                "max_iterations": 24,
                "max_repair_iterations": 12,
                "max_test_runs": 40,
                "max_wall_time_minutes": 180,
                "max_changed_files": 30,
            },
            "adaptive_budget": {
                "enabled": True,
                "effort_pressure": 0.8,
                "dimensions": {
                    "max_model_calls": {
                        "estimate": 20,
                        "working_target": 25,
                        "emergency_limit": 40,
                    },
                    "max_test_runs": {
                        "estimate": 18,
                        "working_target": 24,
                        "emergency_limit": 40,
                    },
                    "max_repair_iterations": {
                        "estimate": 5,
                        "working_target": 7,
                        "emergency_limit": 12,
                    },
                },
            },
        }
    }


def blocked_job(*, model_calls=22):
    normalized = WorkOrder.model_validate(deepcopy(RAW_WORK_ORDER))
    return {
        "id": "job-1",
        "project_id": "chonhac",
        "status": "blocked",
        "source_commit": "b143fbb",
        "workspace": "/workspaces/job-1",
        "branch": "ai/job-1",
        "task": {"title": "DEC-025C"},
        "repo_analysis": {"estimated_files": 8},
        "route": {
            "strategy": {
                "profile": "complex",
                "budget": {
                    "max_model_calls": 22,
                    "max_tool_calls": 160,
                    "max_iterations": 8,
                    "max_repair_iterations": 5,
                    "max_test_runs": 16,
                    "max_wall_time_minutes": 110,
                    "max_changed_files": 30,
                },
            }
        },
        "progress": {
            "model_calls": model_calls,
            "tool_calls": 73,
            "iteration": 5,
            "repair_iterations": 5,
            "test_runs": 16,
            "elapsed_minutes": 96.02,
            "important_decision_flags": [],
            "unexpected_scope": False,
        },
        "checkpoint": {
            "work_order": normalized.model_dump(mode="json"),
            "provider_state": {},
            "route_history": [],
            "approved_decisions": [],
        },
        "result": {
            "reason": "reassessment_stopped",
            "last_failure": "model-call budget exhausted",
            "reassess": {
                "action": "stop",
                "reason": "model-call budget exhausted",
                "signals": ["hard_budget_guard"],
            },
        },
        "error": None,
    }


class FakeQueryResult:
    def __init__(self, rows):
        self.rows = rows

    def fetchall(self):
        return deepcopy(self.rows)


class FakeConnection:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, _query):
        return FakeQueryResult([{"plan_id": "plan-1"}])


class FakeStorage:
    def __init__(self, job, raw_work_order=None):
        self.job = deepcopy(job)
        self.raw_work_order = deepcopy(raw_work_order or RAW_WORK_ORDER)
        self.updates = []

    def connect(self):
        return FakeConnection()

    def get_execution_plan(self, _plan_id):
        return {"plan": {"work_orders": [deepcopy(self.raw_work_order)]}}

    def get(self, job_id):
        return deepcopy(self.job) if job_id == self.job["id"] else None

    def update(self, job_id, **fields):
        assert job_id == self.job["id"]
        self.job.update(deepcopy(fields))
        self.updates.append(deepcopy(fields))


class FakeStore:
    def __init__(self):
        self.work_order_updates = []
        self.plan_updates = []

    def any_busy_work_order(self):
        return False

    def work_orders(self, _plan_id):
        return [
            {
                "plan_id": "plan-1",
                "work_order_id": "DEC-025C-1-recovery-tooling-r2",
                "execution_mode": "agent",
                "state": "blocked",
                "job_id": "job-1",
                "detail": {"preserved": True},
            }
        ]

    def update_work_order(self, plan_id, work_order_id, **fields):
        self.work_order_updates.append((plan_id, work_order_id, deepcopy(fields)))

    def update_plan(self, plan_id, *, status):
        self.plan_updates.append((plan_id, status))


class FakeDelegate:
    def __init__(self, *, reassess=None):
        self.route_calls = 0
        self.reassess_calls = 0
        self.reassess_result = reassess or {
            "action": "continue",
            "reason": "Within budget and no circuit-break condition detected",
            "signals": ["budget_headroom_active:max_model_calls"],
        }

    async def route(self, _payload):
        self.route_calls += 1
        return fresh_route()

    async def reassess(self, _payload):
        self.reassess_calls += 1
        return deepcopy(self.reassess_result)


class FakeEngine:
    def __init__(self, delegate):
        self.router = SimpleNamespace(delegate=delegate)
        self.enqueued = []

    async def enqueue(self, job_id):
        self.enqueued.append(job_id)


def test_pre_adaptive_budget_block_adopts_fresh_envelope_and_same_job():
    storage = FakeStorage(blocked_job())
    store = FakeStore()
    delegate = FakeDelegate()
    engine = FakeEngine(delegate)
    recovery = LegacyAdaptiveRecovery(storage, engine, store)

    result = asyncio.run(recovery.recover_one())

    assert result is not None
    assert result["job_id"] == "job-1"
    assert result["previous_budget"]["max_model_calls"] == 22
    assert result["new_budget"]["max_model_calls"] == 40
    assert result["new_budget"]["max_test_runs"] == 40
    assert storage.job["status"] == "queued"
    assert storage.job["workspace"] == "/workspaces/job-1"
    assert storage.job["source_commit"] == "b143fbb"
    assert storage.job["progress"]["model_calls"] == 22
    assert storage.job["progress"]["test_runs"] == 16
    assert storage.job["progress"]["repair_iterations"] == 5
    assert storage.job["checkpoint"]["work_order"]["budget"]["mode"] == "legacy_hard"
    assert storage.job["checkpoint"]["legacy_adaptive_adoptions"][-1]["new_budget"]["max_model_calls"] == 40
    assert store.work_order_updates[-1][2]["state"] == "running"
    assert store.plan_updates[-1] == ("plan-1", "executing")
    assert engine.enqueued == ["job-1"]


def test_explicit_legacy_hard_raw_contract_is_never_auto_adopted():
    raw = deepcopy(RAW_WORK_ORDER)
    raw["budget"]["mode"] = "legacy_hard"
    storage = FakeStorage(blocked_job(), raw_work_order=raw)
    delegate = FakeDelegate()
    recovery = LegacyAdaptiveRecovery(storage, FakeEngine(delegate), FakeStore())

    assert asyncio.run(recovery.recover_one()) is None
    assert delegate.route_calls == 0
    assert storage.job["status"] == "blocked"


def test_repeated_failure_signal_fails_closed_without_resuming():
    storage = FakeStorage(blocked_job())
    delegate = FakeDelegate(
        reassess={
            "action": "stop",
            "reason": "Circuit breaker: repeated failure",
            "signals": ["repeated_failure:abc123"],
        }
    )
    engine = FakeEngine(delegate)
    recovery = LegacyAdaptiveRecovery(storage, engine, FakeStore())

    assert asyncio.run(recovery.recover_one()) is None
    assert storage.job["status"] == "blocked"
    assert engine.enqueued == []


def test_current_usage_at_fresh_emergency_ceiling_fails_closed():
    storage = FakeStorage(blocked_job(model_calls=40))
    delegate = FakeDelegate()
    engine = FakeEngine(delegate)
    recovery = LegacyAdaptiveRecovery(storage, engine, FakeStore())

    assert asyncio.run(recovery.recover_one()) is None
    assert storage.job["status"] == "blocked"
    assert engine.enqueued == []


def test_adopted_job_keeps_adaptive_budget_on_later_reroute():
    storage = FakeStorage(blocked_job())
    delegate = FakeDelegate()
    recovery = LegacyAdaptiveRecovery(storage, FakeEngine(delegate), FakeStore())

    assert asyncio.run(recovery.recover_one()) is not None
    assert storage.job["checkpoint"]["work_order"]["budget"]["mode"] == "legacy_hard"
    assert storage.job["checkpoint"]["legacy_adaptive_adoptions"]

    proxy = WorkOrderRouterProxy(delegate, storage)
    rerouted = asyncio.run(
        proxy.route(
            {
                "job_id": "job-1",
                "project_id": "chonhac",
                "repository": "chonhac",
                "source_commit": "b143fbb",
                "task": {"title": "DEC-025C"},
                "repo": {"estimated_files": 8},
                "provider_state": {},
            }
        )
    )

    budget = rerouted["strategy"]["budget"]
    assert budget["max_model_calls"] == 40
    assert budget["max_test_runs"] == 40
    assert budget["max_repair_iterations"] == 12
    assert budget["max_wall_time_minutes"] == 180
    # The stored governing WorkOrder remains immutable despite effective adaptive routing.
    assert storage.job["checkpoint"]["work_order"]["budget"]["mode"] == "legacy_hard"