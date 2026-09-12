from __future__ import annotations

import asyncio
from copy import deepcopy

from app.orchestrator_notifications import PlanOrchestrator


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


class FakeDdev:
    async def github_pull_request(self, *, project_id, pr_number):
        return {"number": pr_number, "state": "open", "merged": False}


class FakeEngine:
    def __init__(self):
        self.ddev = FakeDdev()


class FakeStore:
    def __init__(self, rows):
        self.rows = [dict(row) for row in rows]
        self.plan_status = "active"
        self.notifications = []

    def work_orders(self, plan_id):
        return [deepcopy(row) for row in self.rows]

    def update_work_order(self, plan_id, work_order_id, **fields):
        row = next(item for item in self.rows if item["work_order_id"] == work_order_id)
        row.update(deepcopy(fields))

    def update_plan(self, plan_id, *, status):
        self.plan_status = status

    def orchestration(self, plan_id):
        return {
            "plan_id": plan_id,
            "project_id": "demo",
            "status": self.plan_status,
            "ticket_id": "GH-5",
            "github_url": "https://github.com/example/repo/issues/5",
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
    }


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
    service = PlanOrchestrator(storage, FakeEngine(), store=store)

    asyncio.run(service._reconcile_plan(plan()))

    assert store.rows[0]["state"] == "awaiting_merge"
    assert len(store.notifications) == 1
    event = store.notifications[0]
    assert event["event_type"] == "human_decision_required"
    assert event["github_url"] == "https://github.com/example/repo/pull/9"
    assert "manual merge" in event["summary"].lower()


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
    service = PlanOrchestrator(storage, FakeEngine(), store=store)

    asyncio.run(service._reconcile_plan(plan()))
    asyncio.run(service._reconcile_plan(plan()))

    assert store.rows[0]["state"] == "running"
    assert len(store.notifications) == 1
    event = store.notifications[0]
    assert event["event_type"] == "provider_quota_exhausted"
    assert event["severity"] == "warning"
    assert "fallback" in event["summary"].lower()


def test_operator_block_emits_event_without_execution_plan_shape_bug():
    storage = FakeStorage()
    store = FakeStore([row(state="waiting_human", job_id=None, execution_mode="operator")])
    service = PlanOrchestrator(storage, FakeEngine(), store=store)

    result = asyncio.run(
        service.resolve_operator(
            plan_id="pm-gh-200",
            work_order_id="WO-1",
            action="block",
            note="operator found a recovery mismatch",
        )
    )

    assert result["status"] == "blocked"
    assert store.rows[0]["state"] == "blocked"
    assert store.notifications[0]["event_type"] == "work_order_blocked"
