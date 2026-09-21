from __future__ import annotations

import asyncio
from copy import deepcopy
from types import SimpleNamespace

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
                "max_input_tokens": 8_000_000,
                "max_output_tokens": 1_000_000,
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
                    "max_model_calls": {"estimate": 20, "working_target": 25, "emergency_limit": 40},
                    "max_input_tokens": {"estimate": 2_000_000, "working_target": 2_500_000, "emergency_limit": 8_000_000},
                    "max_output_tokens": {"estimate": 300_000, "working_target": 375_000, "emergency_limit": 1_000_000},
                    "max_tool_calls": {"estimate": 200, "working_target": 260, "emergency_limit": 400},
                    "max_iterations": {"estimate": 12, "working_target": 16, "emergency_limit": 24},
                    "max_repair_iterations": {"estimate": 5, "working_target": 7, "emergency_limit": 12},
                    "max_test_runs": {"estimate": 18, "working_target": 24, "emergency_limit": 40},
                    "max_wall_time_minutes": {"estimate": 90, "working_target": 120, "emergency_limit": 180},
                },
            },
        }
    }


def dec_job():
    normalized = WorkOrder.model_validate(deepcopy(RAW_WORK_ORDER))
    return {
        "id": "eec59b13651c54559c10ce204380a68e",
        "project_id": "chonhac",
        "status": "blocked",
        "source_commit": "b143fbb001c2006ec82570619802b607085fbeb0",
        "workspace": "/home/sonvh/.coding-platform/workspaces/eec59b13651c54559c10ce204380a68e",
        "branch": "ai/eec59b13651c",
        "task": {"title": "DEC-025C"},
        "repo_analysis": {"estimated_files": 8},
        "route": {
            "strategy": {
                "profile": "complex",
                "budget": {
                    "max_model_calls": 22,
                    "max_input_tokens": 2_000_000,
                    "max_output_tokens": 300_000,
                    "max_tool_calls": 305,
                    "max_iterations": 18,
                    "max_repair_iterations": 11,
                    "max_test_runs": 29,
                    "max_wall_time_minutes": 116,
                    "max_changed_files": 30,
                },
            }
        },
        "progress": {
            "model_calls": 22,
            "input_tokens": 2_274_574,
            "output_tokens": 120_000,
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
            "last_failure": "input-token budget exceeded",
            "reassess": {
                "action": "stop",
                "reason": "input-token budget exceeded",
                "signals": ["hard_budget_overrun"],
            },
        },
        "error": None,
    }


class FakeQueryResult:
    def fetchall(self):
        return [{"plan_id": "pm-gh-5650852312"}]


class FakeConnection:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, _query):
        return FakeQueryResult()


class FakeStorage:
    def __init__(self):
        self.job = dec_job()

    def connect(self):
        return FakeConnection()

    def get_execution_plan(self, _plan_id):
        return {"plan": {"work_orders": [deepcopy(RAW_WORK_ORDER)]}}

    def get(self, job_id):
        return deepcopy(self.job) if job_id == self.job["id"] else None

    def update(self, job_id, **fields):
        assert job_id == self.job["id"]
        self.job.update(deepcopy(fields))


class FakeStore:
    def __init__(self):
        self.work_order_updates = []
        self.plan_updates = []

    def any_busy_work_order(self):
        return False

    def work_orders(self, _plan_id):
        return [{
            "plan_id": "pm-gh-5650852312",
            "work_order_id": "DEC-025C-1-recovery-tooling-r2",
            "execution_mode": "agent",
            "state": "blocked",
            "job_id": "eec59b13651c54559c10ce204380a68e",
            "detail": {"preserved": True},
        }]

    def update_work_order(self, plan_id, work_order_id, **fields):
        self.work_order_updates.append((plan_id, work_order_id, deepcopy(fields)))

    def update_plan(self, plan_id, *, status):
        self.plan_updates.append((plan_id, status))


class FakeDelegate:
    def __init__(self, reassess=None):
        self.reassess_result = reassess or {
            "action": "continue",
            "reason": "Within material circuit breakers and no anomaly detected",
            "signals": ["budget_estimate_exceeded:max_input_tokens"],
        }

    async def route(self, _payload):
        return deepcopy(fresh_route())

    async def reassess(self, _payload):
        return deepcopy(self.reassess_result)


class FakeEngine:
    def __init__(self, delegate):
        self.router = SimpleNamespace(delegate=delegate)
        self.enqueued = []

    async def enqueue(self, job_id):
        self.enqueued.append(job_id)


def test_dec_token_overrun_auto_adopts_fresh_healthy_envelope_on_same_job():
    storage = FakeStorage()
    store = FakeStore()
    engine = FakeEngine(FakeDelegate())
    recovery = LegacyAdaptiveRecovery(storage, engine, store)

    result = asyncio.run(recovery.recover_one())

    assert result is not None
    assert result["job_id"] == "eec59b13651c54559c10ce204380a68e"
    assert result["previous_budget"]["max_input_tokens"] == 2_000_000
    assert result["new_budget"]["max_input_tokens"] == 8_000_000
    assert storage.job["status"] == "queued"
    assert storage.job["workspace"] == "/home/sonvh/.coding-platform/workspaces/eec59b13651c54559c10ce204380a68e"
    assert storage.job["source_commit"] == "b143fbb001c2006ec82570619802b607085fbeb0"
    assert storage.job["branch"] == "ai/eec59b13651c"
    assert storage.job["progress"]["input_tokens"] == 2_274_574
    assert storage.job["checkpoint"]["work_order"]["budget"]["mode"] == "legacy_hard"
    audit = storage.job["checkpoint"]["legacy_adaptive_adoptions"][-1]
    assert audit["previous_budget"]["max_input_tokens"] == 2_000_000
    assert audit["new_budget"]["max_input_tokens"] == 8_000_000
    assert engine.enqueued == ["eec59b13651c54559c10ce204380a68e"]
    assert store.work_order_updates[-1][2]["state"] == "running"
    assert store.plan_updates[-1] == ("pm-gh-5650852312", "executing")


def test_dec_token_overrun_stays_blocked_when_fresh_reassessment_finds_anomaly():
    storage = FakeStorage()
    engine = FakeEngine(FakeDelegate(reassess={
        "action": "stop",
        "reason": "Circuit breaker: repeated failure",
        "signals": ["repeated_failure:abc123"],
    }))
    recovery = LegacyAdaptiveRecovery(storage, engine, FakeStore())

    assert asyncio.run(recovery.recover_one()) is None
    assert storage.job["status"] == "blocked"
    assert storage.job["progress"]["input_tokens"] == 2_274_574
    assert engine.enqueued == []


def test_dec_token_overrun_above_fresh_high_water_auto_adopts_when_reassessment_is_healthy():
    storage = FakeStorage()
    storage.job["progress"]["input_tokens"] = 8_072_466
    store = FakeStore()
    engine = FakeEngine(FakeDelegate())
    recovery = LegacyAdaptiveRecovery(storage, engine, store)

    result = asyncio.run(recovery.recover_one())

    assert result is not None
    assert result["job_id"] == "eec59b13651c54559c10ce204380a68e"
    assert storage.job["status"] == "queued"
    assert storage.job["progress"]["input_tokens"] == 8_072_466
    assert storage.job["workspace"] == "/home/sonvh/.coding-platform/workspaces/eec59b13651c54559c10ce204380a68e"
    assert engine.enqueued == ["eec59b13651c54559c10ce204380a68e"]
    assert store.work_order_updates[-1][2]["state"] == "running"
    assert store.plan_updates[-1] == ("pm-gh-5650852312", "executing")
