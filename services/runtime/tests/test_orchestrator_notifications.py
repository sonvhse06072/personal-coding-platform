from __future__ import annotations

import asyncio
from copy import deepcopy

from app.orchestrator_notifications import PlanOrchestrator


class FakeQueryResult:
    def __init__(self, rows):
        self.rows = rows

    def fetchall(self):
        return deepcopy(self.rows)


class FakeConnection:
    def __init__(self, storage):
        self.storage = storage

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, sql, params=None):
        if "SELECT plan_id FROM cp_plan_orchestrations" in sql:
            return FakeQueryResult([{"plan_id": "pm-gh-200"}])
        raise AssertionError(f"unexpected fake SQL: {sql}")


class FakeStorage:
    def __init__(self, jobs=None):
        self.jobs = jobs or {}

    def get(self, job_id):
        return self.jobs.get(job_id)

    def get_execution_plan(self, plan_id):
        return {
            "id": plan_id,
            "project_id": "demo",
            "ticket": {"id": "GH-5", "title": "Recovery", "description": "bounded"},
        }

    def connect(self):
        return FakeConnection(self)


class FakeDdev:
    async def github_pull_request(self, *, project_id, pr_number):
        return {"number": pr_number, "state": "open", "merged": False}


class FakeEngine:
    def __init__(self):
        self.ddev = FakeDdev()


class FakeControls:
    def __init__(self):
        self.orchestrator = None

    def ensure(self):
        return None

    def manual_merge_advisory(self, pr_url):
        return {
            "title": "MANUAL MERGE REQUIRED",
            "phase": "delivery",
            "reason": "awaiting_merge",
            "summary": "PR passed its automated gates and is ready for manual merge.",
            "cause": "Manual merge policy.",
            "preserved": ["Downstream work is pending."],
            "impact": "Plan waits for owner merge.",
            "recommended": "Review and merge manually.",
            "metrics": [],
            "action_specs": [],
        }

    def waiting_human_advisory(self, work_order, job):
        return {
            "title": "HUMAN DECISION REQUIRED",
            "phase": "decision",
            "reason": "human_decision_required",
            "summary": "Owner decision required.",
            "cause": "Governance gate.",
            "preserved": [],
            "impact": "Job waits.",
            "recommended": "Review the decision.",
            "metrics": [],
            "action_specs": [],
        }

    def blocked_advisory(self, work_order, job):
        result = (job or {}).get("result") or {}
        reason = result.get("reason") or (work_order.get("detail") or {}).get("reason") or "work_order_blocked"
        metrics = []
        if reason == "execution_budget_exhausted":
            metrics = [{"key": "max_model_calls", "label": "Model calls", "used": 10, "limit": 10}]
        return {
            "title": "WORKORDER BLOCKED",
            "phase": "execution",
            "reason": reason,
            "summary": "Runtime execution is blocked.",
            "cause": "A bounded safety gate stopped the job.",
            "preserved": ["Same job/workspace and progress are preserved."],
            "impact": "Downstream work stays pending.",
            "recommended": "Use a bounded owner action.",
            "metrics": metrics,
            "action_specs": [],
        }

    def create_actions(self, *, plan, work_order, job, advisory, ttl_hours=48):
        if advisory["reason"] == "execution_budget_exhausted":
            return [
                {
                    "label": "➕ +4 Model calls",
                    "action_id": "opaque-action-id",
                    "callback_data": "act:opaque-action-id",
                }
            ]
        if advisory["reason"] == "awaiting_merge":
            return [{"label": "🔗 Open PR", "url": work_order.get("pr_url")}]
        return [{"label": "📋 Chi tiết", "action_id": "details-action", "callback_data": "act:details-action"}]


class FakeStore:
    def __init__(self, rows):
        self.rows = [dict(row) for row in rows]
        self.plan_status = "active"
        self.notifications = []

    def ensure(self):
        return None

    def register_new_plans(self):
        return []

    def active_plans(self):
        if self.plan_status in {"blocked", "completed", "waiting_human"}:
            return []
        return [plan()]

    def any_busy_work_order(self):
        return any(item["state"] in {"running", "awaiting_merge", "waiting_human"} for item in self.rows)

    def work_orders(self, plan_id):
        return [deepcopy(row) for row in self.rows]

    def update_work_order(self, plan_id, work_order_id, **fields):
        row = next(item for item in self.rows if item["work_order_id"] == work_order_id)
        row.update(deepcopy(fields))
        row["updated_at"] = "t1"

    def update_plan(self, plan_id, *, status):
        self.plan_status = status

    def orchestration(self, plan_id):
        return {
            "plan_id": plan_id,
            "project_id": "demo",
            "status": self.plan_status,
            "ticket_id": "GH-5",
            "github_url": "https://github.com/example/repo/issues/5",
            "updated_at": "p1",
        }

    def emit_notification(self, **payload):
        if not any(item["dedupe_key"] == payload["dedupe_key"] for item in self.notifications):
            self.notifications.append(deepcopy(payload))
            return True
        return False


def plan():
    return {
        "plan_id": "pm-gh-200",
        "project_id": "demo",
        "ticket": {"id": "GH-5", "title": "Recovery", "description": "bounded"},
        "github_url": "https://github.com/example/repo/issues/5",
        "plan": {"work_orders": [], "decision_boundaries": []},
    }


def row(*, state="running", job_id="job-1", execution_mode="agent"):
    return {
        "plan_id": "pm-gh-200",
        "work_order_id": "WO-1",
        "sequence_no": 0,
        "execution_mode": execution_mode,
        "state": state,
        "job_id": job_id,
        "pr_number": None,
        "pr_url": None,
        "detail": {},
        "updated_at": "t0",
    }


def service(storage, store):
    return PlanOrchestrator(storage, FakeEngine(), store=store, controls=FakeControls())


def test_ci_green_pr_transition_notifies_manual_merge_required():
    storage = FakeStorage(
        {
            "job-1": {
                "id": "job-1",
                "status": "completed",
                "result": {
                    "delivery": {
                        "state": "ci_success",
                        "pull_request": {
                            "number": 9,
                            "url": "https://github.com/example/repo/pull/9",
                        },
                    }
                },
                "progress": {},
            }
        }
    )
    store = FakeStore([row()])
    orchestrator = service(storage, store)

    asyncio.run(orchestrator.tick())

    assert store.rows[0]["state"] == "awaiting_merge"
    assert len(store.notifications) == 1
    event = store.notifications[0]
    assert event["event_type"] == "human_decision_required"
    assert event["github_url"] == "https://github.com/example/repo/pull/9"
    assert "manual merge" in event["summary"].lower()
    assert event["payload"]["advisory"]["reason"] == "awaiting_merge"
    assert event["payload"]["actions"][0]["url"].endswith("/pull/9")


def test_quota_exhaustion_notifies_even_when_job_can_keep_running():
    storage = FakeStorage(
        {
            "job-1": {
                "id": "job-1",
                "status": "executing",
                "result": None,
                "progress": {
                    "provider_failures": [
                        {
                            "model": "codex_plus",
                            "provider": "openai",
                            "kind": "quota_exhausted",
                        }
                    ]
                },
            }
        }
    )
    store = FakeStore([row()])
    orchestrator = service(storage, store)

    asyncio.run(orchestrator.tick())
    asyncio.run(orchestrator.tick())

    assert store.rows[0]["state"] == "running"
    assert len(store.notifications) == 1
    event = store.notifications[0]
    assert event["event_type"] == "provider_quota_exhausted"
    assert event["severity"] == "warning"
    assert event["payload"]["actions"] == []
    assert "fallback" in event["payload"]["advisory"]["cause"].lower()


def test_budget_block_transition_emits_diagnostic_and_context_action():
    storage = FakeStorage(
        {
            "job-1": {
                "id": "job-1",
                "status": "blocked",
                "result": {
                    "reason": "execution_budget_exhausted",
                    "last_failure": "model-call budget exhausted",
                },
                "progress": {"model_calls": 10},
            }
        }
    )
    store = FakeStore([row()])
    orchestrator = service(storage, store)

    asyncio.run(orchestrator.tick())

    assert store.rows[0]["state"] == "blocked"
    assert store.plan_status == "blocked"
    assert len(store.notifications) == 1
    event = store.notifications[0]
    assert event["event_type"] == "work_order_blocked"
    assert event["payload"]["advisory"]["reason"] == "execution_budget_exhausted"
    assert event["payload"]["advisory"]["metrics"][0]["used"] == 10
    assert event["payload"]["actions"][0]["callback_data"] == "act:opaque-action-id"


def test_operator_block_emits_one_rich_event_without_core_duplicate():
    storage = FakeStorage()
    store = FakeStore([row(state="waiting_human", job_id=None, execution_mode="operator")])
    store.plan_status = "waiting_human"
    orchestrator = service(storage, store)

    result = asyncio.run(
        orchestrator.resolve_operator(
            plan_id="pm-gh-200",
            work_order_id="WO-1",
            action="block",
            note="operator found a recovery mismatch",
        )
    )

    assert result["status"] == "blocked"
    assert store.rows[0]["state"] == "blocked"
    assert len(store.notifications) == 1
    assert store.notifications[0]["event_type"] == "work_order_blocked"
    assert store.notifications[0]["payload"]["advisory"]["reason"] == "operator_blocked"
