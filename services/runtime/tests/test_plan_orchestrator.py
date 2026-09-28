from __future__ import annotations

import asyncio
from copy import deepcopy
from datetime import datetime, timezone

from app.plan_orchestrator import PlanOrchestrator


def work_order(work_order_id, *, dependencies=None, requested_role="developer"):
    return {
        "id": work_order_id,
        "parent_ticket": "GH-5",
        "objective": work_order_id,
        "baseline_revision": "v1",
        "source_references": [{"path": "docs/scope.md"}],
        "in_scope": ["bounded work"],
        "out_of_scope": ["unrelated work"],
        "acceptance_criteria": [{"id": f"{work_order_id}-AC", "description": "done"}],
        "constraints": ["bounded"],
        "requested_role": requested_role,
        "verification": {"required_phases": ["targeted_tests"]},
        "risk": {"level": "standard", "flags": []},
        "budget": {
            "max_profile": "standard",
            "max_model_calls": 4,
            "max_repair_iterations": 1,
            "max_wall_time_minutes": 20,
            "max_changed_files": 8,
        },
        "dependencies": dependencies or [],
    }


def plan_row(work_orders):
    return {
        "plan_id": "pm-gh-200",
        "project_id": "demo",
        "status": "active",
        "ticket_id": "GH-5",
        "ticket_title": "Recovery rehearsal",
        "github_url": "https://github.com/example/repo/issues/5#issuecomment-200",
        "baseline_revision": "v1",
        "baseline_source_commit": "a" * 40,
        "ticket": {"id": "GH-5", "title": "Recovery rehearsal", "description": "bounded"},
        "plan": {
            "scope_assessment": "in_scope",
            "summary": "bounded",
            "work_orders": work_orders,
            "decision_boundaries": [],
            "ready_work_order_ids": [work_orders[0]["id"]],
        },
        "staffing": {"mode": "external"},
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
    }


class FakeStorage:
    def __init__(self):
        self.jobs = {}

    def get(self, job_id):
        return self.jobs.get(job_id)

    def get_execution_plan(self, plan_id):
        return None


class FakeDdev:
    def __init__(self):
        self.prs = {}
        self.quiesced = []

    async def github_pull_request(self, *, project_id, pr_number):
        return deepcopy(self.prs[pr_number])

    async def quiesce_workspace(
        self,
        *,
        job_id,
        project_id,
        workspace,
        remove_data=False,
    ):
        self.quiesced.append({
            "job_id": job_id,
            "project_id": project_id,
            "workspace": workspace,
            "remove_data": remove_data,
        })
        return {
            "quiesced": True,
            "data_removed": bool(remove_data),
        }


class FakeEngine:
    def __init__(self, storage):
        self.storage = storage
        self.ddev = FakeDdev()
        self.created = []
        self.enqueued = []

    def create_job(self, payload):
        self.created.append(deepcopy(payload))
        job_id = payload["_job_id"]
        self.storage.jobs.setdefault(
            job_id,
            {
                "id": job_id,
                "project_id": payload["project_id"],
                "status": "queued",
                "checkpoint": {"work_order": payload["work_order"]},
                "result": None,
                "progress": {},
            },
        )
        return job_id

    async def enqueue(self, job_id):
        self.enqueued.append(job_id)


class FakeStore:
    def __init__(self, plan, tracked):
        self.plan = plan
        self.tracked = [dict(item) for item in tracked]
        self.plan_status = "active"
        self.plan_lifecycle = "active"
        self.notifications = []
        self.registered = []

    def ensure(self):
        return None

    def register_new_plans(self):
        result = list(self.registered)
        self.registered = []
        return result

    def active_plans(self):
        if self.plan_lifecycle != "active" or self.plan_status in {"completed", "blocked"}:
            return []
        value = deepcopy(self.plan)
        value["status"] = self.plan_status
        return [value]

    def orchestration(self, plan_id):
        return {
            "plan_id": plan_id,
            "project_id": self.plan["project_id"],
            "status": self.plan_status,
            "lifecycle": self.plan_lifecycle,
        }

    def work_orders(self, plan_id):
        return [deepcopy(item) for item in sorted(self.tracked, key=lambda row: row["sequence_no"])]

    def update_plan(self, plan_id, *, status):
        self.plan_status = status

    def update_work_order(self, plan_id, work_order_id, **fields):
        row = next(item for item in self.tracked if item["work_order_id"] == work_order_id)
        row.update(deepcopy(fields))

    def any_busy_work_order(self):
        return any(
            row.get("lifecycle", "active") == "active"
            and row["state"] in {"running", "awaiting_merge", "waiting_human"}
            for row in self.tracked
        )

    def emit_notification(self, **payload):
        if not any(item["dedupe_key"] == payload["dedupe_key"] for item in self.notifications):
            self.notifications.append(deepcopy(payload))
            return True
        return False


def tracked(work_order_id, sequence_no, *, execution_mode="agent", state="pending", **extra):
    return {
        "plan_id": "pm-gh-200",
        "work_order_id": work_order_id,
        "sequence_no": sequence_no,
        "execution_mode": execution_mode,
        "state": state,
        "lifecycle": "active",
        "job_id": None,
        "pr_number": None,
        "pr_url": None,
        "detail": {},
        **extra,
    }


def orchestrator(work_orders, tracked_rows):
    storage = FakeStorage()
    engine = FakeEngine(storage)
    store = FakeStore(plan_row(work_orders), tracked_rows)
    return PlanOrchestrator(storage, engine, store=store), storage, engine, store


def test_tick_launches_only_first_dependency_ready_work_order_and_is_idempotent():
    first = work_order("WO-1")
    second = work_order("WO-2", dependencies=["WO-1"])
    service, storage, engine, store = orchestrator(
        [first, second],
        [tracked("WO-1", 0), tracked("WO-2", 1)],
    )

    result = asyncio.run(service.tick())

    assert result["launched"]["work_order_id"] == "WO-1"
    assert len(engine.created) == 1
    assert len(engine.enqueued) == 1
    assert engine.created[0]["source_commit"] is None
    assert store.tracked[0]["state"] == "running"
    assert store.tracked[1]["state"] == "pending"

    asyncio.run(service.tick())
    assert len(engine.created) == 1
    assert len(engine.enqueued) == 1


def test_superseded_blocked_work_is_not_busy_and_does_not_block_eligible_work():
    original = work_order("UI-CL-1-responsive-regression-matrix")
    unrelated = work_order("UNRELATED-ELIGIBLE")
    service, storage, engine, store = orchestrator(
        [original, unrelated],
        [
            tracked(
                original["id"],
                0,
                state="blocked",
                lifecycle="superseded",
                job_id="4283bb02a28a5c96b71f7bb1bc5e3676",
                superseded_by_plan_id="pm-gh-r2",
                superseded_by_work_order_id="UI-CL-1-responsive-regression-matrix-r2",
            ),
            tracked(unrelated["id"], 1),
        ],
    )
    storage.jobs["4283bb02a28a5c96b71f7bb1bc5e3676"] = {
        "id": "4283bb02a28a5c96b71f7bb1bc5e3676",
        "status": "blocked",
        "result": {"reason": "work_order_policy_rejected"},
        "progress": {"model_calls": 0},
    }

    result = asyncio.run(service.tick())

    assert result["launched"]["work_order_id"] == "UNRELATED-ELIGIBLE"
    assert engine.created[0]["work_order"]["id"] == "UNRELATED-ELIGIBLE"
    assert store.tracked[0]["state"] == "blocked"
    assert store.tracked[0]["job_id"] == "4283bb02a28a5c96b71f7bb1bc5e3676"
    assert storage.jobs["4283bb02a28a5c96b71f7bb1bc5e3676"]["result"]["reason"] == (
        "work_order_policy_rejected"
    )
    assert store.tracked[1]["state"] == "running"


def test_completed_ci_job_waits_for_manual_merge_then_unlocks_dependency():
    first = work_order("WO-1")
    second = work_order("WO-2", dependencies=["WO-1"])
    service, storage, engine, store = orchestrator(
        [first, second],
        [tracked("WO-1", 0, state="running", job_id="job-1"), tracked("WO-2", 1)],
    )
    storage.jobs["job-1"] = {
        "id": "job-1",
        "status": "completed",
        "result": {
            "delivery": {
                "state": "ci_success",
                "pull_request": {"number": 7, "url": "https://github.com/example/repo/pull/7"},
            }
        },
        "progress": {},
    }

    asyncio.run(service.tick())
    assert store.tracked[0]["state"] == "awaiting_merge"
    assert store.tracked[1]["state"] == "pending"
    assert engine.created == []

    engine.ddev.prs[7] = {
        "number": 7,
        "state": "closed",
        "merged": True,
        "merged_at": "2026-09-13T03:00:00Z",
        "merge_commit_sha": "merge123",
    }
    result = asyncio.run(service.tick())

    assert store.tracked[0]["state"] == "completed"
    assert result["launched"]["work_order_id"] == "WO-2"
    assert store.tracked[1]["state"] == "running"


def test_review_repair_reopens_same_awaiting_merge_work_order():
    first = work_order("WO-1")
    second = work_order("WO-2", dependencies=["WO-1"])
    service, storage, engine, store = orchestrator(
        [first, second],
        [
            tracked("WO-1", 0, state="awaiting_merge", job_id="job-1", pr_number=7),
            tracked("WO-2", 1),
        ],
    )
    storage.jobs["job-1"] = {
        "id": "job-1",
        "status": "queued",
        "checkpoint": {"pending_review_repair": {"request_id": "repair-1"}},
        "progress": {},
    }

    result = asyncio.run(service.tick())

    assert result["launched"] is None
    assert store.tracked[0]["state"] == "running"
    assert store.tracked[0]["job_id"] == "job-1"
    assert store.tracked[0]["pr_number"] == 7
    assert store.tracked[0]["detail"]["review_repair_reopened"] is True
    assert store.tracked[1]["state"] == "pending"
    assert store.plan_status == "executing"
    assert engine.ddev.prs == {}


def test_operator_work_order_holds_and_emits_deduplicated_notification():
    operator = work_order("WO-OP", requested_role="operator")
    service, storage, engine, store = orchestrator(
        [operator],
        [tracked("WO-OP", 0, execution_mode="operator")],
    )

    asyncio.run(service.tick())
    asyncio.run(service.tick())

    assert store.tracked[0]["state"] == "waiting_human"
    assert store.plan_status == "waiting_human"
    assert engine.created == []
    assert [item["event_type"] for item in store.notifications] == ["operator_action_required"]


def test_provider_quota_without_fallback_blocks_plan_and_notifies_owner():
    wo = work_order("WO-1")
    service, storage, engine, store = orchestrator(
        [wo],
        [tracked("WO-1", 0, state="running", job_id="job-1")],
    )
    storage.jobs["job-1"] = {
        "id": "job-1",
        "status": "blocked",
        "result": {"reason": "provider_failure_without_fallback"},
        "progress": {
            "provider_failures": [
                {"model": "some-model", "provider": "some-provider", "kind": "quota_exhausted"}
            ]
        },
    }

    asyncio.run(service.tick())

    assert store.tracked[0]["state"] == "blocked"
    assert store.plan_status == "blocked"
    assert store.notifications[0]["event_type"] == "provider_quota_exhausted"
    assert "quota" in store.notifications[0]["summary"].lower()


def test_operator_completion_allows_plan_to_complete_and_emits_ticket_notification():
    operator = work_order("WO-OP", requested_role="operator")
    service, storage, engine, store = orchestrator(
        [operator],
        [tracked("WO-OP", 0, execution_mode="operator", state="waiting_human")],
    )

    result = asyncio.run(
        service.resolve_operator(
            plan_id="pm-gh-200",
            work_order_id="WO-OP",
            action="complete",
            note="bounded rehearsal evidence accepted",
        )
    )

    assert result["status"] == "completed"
    assert store.tracked[0]["state"] == "completed"
    assert any(item["event_type"] == "ticket_completed" for item in store.notifications)


def test_deterministic_job_id_is_stable_per_plan_work_order():
    first = PlanOrchestrator._deterministic_job_id("plan-a", "wo-a")
    second = PlanOrchestrator._deterministic_job_id("plan-a", "wo-a")
    other = PlanOrchestrator._deterministic_job_id("plan-a", "wo-b")

    assert first == second
    assert first != other
    assert len(first) == 32

def test_repo_hints_treat_work_order_risk_flags_as_protected_change_authority():
    wo = work_order("WO-1")
    wo["risk"]["flags"] = ["frontend_tests", "verification_secrecy"]

    hints = PlanOrchestrator._repo_hints(wo)

    assert hints["security_sensitive"] is False
    assert hints["authentication_change"] is False
    assert hints["authorization_change"] is False
    assert hints["schema_change"] is False
    assert hints["external_api"] is False
    assert hints["production_write"] is False
    assert hints["destructive_migration"] is False

    wo["risk"]["flags"] = [
        "security_sensitive",
        "authentication_change",
        "authorization_change",
        "schema_change",
        "external_api",
        "production_write",
        "destructive_migration",
    ]
    hints = PlanOrchestrator._repo_hints(wo)

    assert hints["security_sensitive"] is True
    assert hints["authentication_change"] is True
    assert hints["authorization_change"] is True
    assert hints["schema_change"] is True
    assert hints["external_api"] is True
    assert hints["production_write"] is True
    assert hints["destructive_migration"] is True

def test_terminal_agent_job_quiesces_workspace_before_blocking_plan():
    wo = work_order("WO-1")
    service, storage, engine, store = orchestrator(
        [wo],
        [tracked("WO-1", 0, state="running", job_id="job-1")],
    )
    storage.jobs["job-1"] = {
        "id": "job-1",
        "project_id": "demo",
        "workspace": "/tmp/workspaces/job-1",
        "status": "blocked",
        "result": {"reason": "provider_failure_without_fallback"},
        "progress": {},
    }

    asyncio.run(service.tick())

    assert engine.ddev.quiesced == [{
        "job_id": "job-1",
        "project_id": "demo",
        "workspace": "/tmp/workspaces/job-1",
        "remove_data": False,
    }]
    assert store.tracked[0]["state"] == "blocked"
    assert store.tracked[0]["detail"]["resource_quiesce"] == {
        "quiesced": True,
        "data_removed": False,
    }


def test_completed_agent_job_quiesces_workspace_before_awaiting_merge():
    wo = work_order("WO-1")
    service, storage, engine, store = orchestrator(
        [wo],
        [tracked("WO-1", 0, state="running", job_id="job-1")],
    )
    storage.jobs["job-1"] = {
        "id": "job-1",
        "project_id": "demo",
        "workspace": "/tmp/workspaces/job-1",
        "status": "completed",
        "result": {
            "delivery": {
                "state": "ci_success",
                "pull_request": {
                    "number": 7,
                    "url": "https://github.com/example/repo/pull/7",
                },
            }
        },
        "progress": {},
    }

    asyncio.run(service.tick())

    assert engine.ddev.quiesced == [{
        "job_id": "job-1",
        "project_id": "demo",
        "workspace": "/tmp/workspaces/job-1",
        "remove_data": True,
    }]
    assert store.tracked[0]["state"] == "awaiting_merge"
    assert store.tracked[0]["detail"]["resource_quiesce"] == {
        "quiesced": True,
        "data_removed": True,
    }

def test_cancelled_agent_job_releases_ddev_data_before_blocking_plan():
    wo = work_order("WO-1")
    service, storage, engine, store = orchestrator(
        [wo],
        [tracked("WO-1", 0, state="running", job_id="job-1")],
    )
    storage.jobs["job-1"] = {
        "id": "job-1",
        "project_id": "demo",
        "workspace": "/tmp/workspaces/job-1",
        "status": "cancelled",
        "result": {},
        "progress": {},
    }

    asyncio.run(service.tick())

    assert engine.ddev.quiesced == [{
        "job_id": "job-1",
        "project_id": "demo",
        "workspace": "/tmp/workspaces/job-1",
        "remove_data": True,
    }]
    assert store.tracked[0]["state"] == "blocked"
    assert store.tracked[0]["detail"]["resource_quiesce"] == {
        "quiesced": True,
        "data_removed": True,
    }



def test_direct_project_lease_defers_launch_until_repo_is_available(monkeypatch):
    first = work_order("WO-DIRECT")
    service, storage, engine, store = orchestrator(
        [first],
        [tracked("WO-DIRECT", 0)],
    )
    candidate = service._deterministic_job_id("pm-gh-200", "WO-DIRECT")

    monkeypatch.setattr(
        "app.plan_orchestrator.project_config",
        lambda project_id: {
            "runtime": {
                "workspace_mode": "direct",
                "exclusive_project_lease": True,
            }
        },
    )
    storage.project_lease = lambda project_id: {
        "project_id": project_id,
        "owner_job_id": "another-job",
        "state": "active",
    }

    deferred = asyncio.run(service.tick())

    assert deferred["launched"] is None
    assert engine.created == []
    assert engine.enqueued == []
    assert store.tracked[0]["state"] == "pending"

    storage.project_lease = lambda project_id: {
        "project_id": project_id,
        "owner_job_id": candidate,
        "state": "active",
    }

    launched = asyncio.run(service.tick())

    assert launched["launched"]["job_id"] == candidate
    assert len(engine.created) == 1
    assert engine.enqueued == [candidate]
