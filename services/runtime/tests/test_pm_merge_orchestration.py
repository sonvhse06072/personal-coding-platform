from __future__ import annotations

import asyncio
from copy import deepcopy

import pytest

import app.orchestrator_merge as merge_module
import app.plan_orchestrator as core_module
from app.orchestrator_merge import PlanOrchestrator
from checkpoint_fakes import CheckpointTransitions


HEAD = "b" * 40
SOURCE = "a" * 40


def work_order(work_order_id: str, *, dependencies=None, security=False) -> dict:
    return {
        "id": work_order_id,
        "objective": "bounded",
        "requested_role": "developer",
        "risk": {"level": "standard", "flags": ["security_boundary_change"] if security else []},
        "dependencies": dependencies or [],
    }


def plan_row(work_orders) -> dict:
    return {
        "plan_id": "plan-1",
        "project_id": "default",
        "status": "active",
        "ticket": {"id": "GH-98", "title": "PM merge"},
        "plan": {"work_orders": work_orders, "decision_boundaries": []},
        "baseline_revision": "baseline-r1",
        "baseline_source_commit": SOURCE,
    }


def tracked(work_order_id: str, sequence_no: int, *, state="pending", job_id=None, pr_number=None) -> dict:
    return {
        "plan_id": "plan-1",
        "work_order_id": work_order_id,
        "sequence_no": sequence_no,
        "execution_mode": "agent",
        "state": state,
        "job_id": job_id,
        "pr_number": pr_number,
        "pr_url": f"https://github.com/acme/demo/pull/{pr_number}" if pr_number else None,
        "detail": {},
    }


def accepted_job(work_order_id="WO-1", *, security=False) -> dict:
    human = {
        "required": security,
        "triggers": ["security_boundary_change"] if security else [],
        "reason": "security" if security else None,
    }
    route = {
        "strategy": {
            "human_decision": human,
            "review_policy": {
                "required": True,
                "independent": True,
                "independence_satisfied": True,
                "conditional_on_strong_evidence": False,
            },
        }
    }
    return {
        "id": "job-12345678",
        "project_id": "default",
        "status": "completed",
        "dry_run": False,
        "source_commit": SOURCE,
        "branch": "ai/job-123456",
        "task": {"title": "Fix", "flags": []},
        "repo_analysis": {
            "security_sensitive": security,
            "authentication_change": False,
            "authorization_change": False,
            "destructive_migration": False,
            "production_write": False,
        },
        "checkpoint": {
            "work_order": work_order(work_order_id, security=security),
            "approved_decisions": [],
        },
        "route": route,
        "progress": {"required_checks_passed": True, "unexpected_scope": False},
        "result": {
            "status": "accepted",
            "commit": HEAD,
            "verification": {"passed": True},
            "review": {"verdict": "pass"},
            "pm_evidence": {"unresolved_risks": [], "protected_decision_flags": []},
            "route": route,
            "progress": {"required_checks_passed": True, "unexpected_scope": False},
            "delivery": {
                "state": "ci_success",
                "ci": {"state": "success", "commit": HEAD},
                "pull_request": {
                    "number": 7,
                    "head": HEAD,
                    "head_ref": "ai/job-123456",
                    "base_ref": "main",
                },
            },
            "delivery_finalized": True,
        },
    }


def ci_none_job(work_order_id="WO-1", *, security=False) -> dict:
    job = accepted_job(work_order_id, security=security)
    job["result"]["delivery"]["state"] = "ci_none"
    job["result"]["delivery"]["ci"]["state"] = "none"
    return job


class FakeStorage:
    def __init__(self, jobs):
        self.jobs = jobs
        self.continuity = []

    def get(self, job_id):
        return deepcopy(self.jobs.get(job_id))

    def get_execution_plan(self, plan_id):
        return None

    def record_external_continuity(self, **payload):
        self.continuity.append(deepcopy(payload))


class FakeStore(CheckpointTransitions):
    def __init__(self, plan, rows):
        self.plan = deepcopy(plan)
        self.rows = [deepcopy(row) for row in rows]
        self.plan_status = "active"
        self.notifications = []

    def ensure(self):
        return None

    def register_new_plans(self):
        return []

    def active_plans(self):
        if self.plan_status == "completed":
            return []
        value = deepcopy(self.plan)
        value["status"] = self.plan_status
        return [value]

    def orchestration(self, plan_id):
        return {"plan_id": plan_id, "project_id": "default", "status": self.plan_status}

    def work_orders(self, plan_id):
        return [deepcopy(row) for row in sorted(self.rows, key=lambda item: item["sequence_no"])]

    def update_plan(self, plan_id, *, status):
        self.plan_status = status

    def update_work_order(self, plan_id, work_order_id, **fields):
        row = next(item for item in self.rows if item["work_order_id"] == work_order_id)
        row.update(deepcopy(fields))

    def any_busy_work_order(self):
        return any(row["state"] in {"running", "awaiting_merge", "waiting_human"} for row in self.rows)

    def emit_notification(self, **payload):
        self.notifications.append(deepcopy(payload))
        return True


class FakeDdev:
    def __init__(self):
        self.merged = False
        self.merge_calls = 0
        self.ci_calls = 0
        self.ci_state = "success"
        self.ci_commit = HEAD
        self.pr_overrides = {}
        self.pr_error = False
        self.ci_error = False

    async def github_pull_request(self, *, project_id, pr_number):
        if self.pr_error:
            raise RuntimeError("injected PR read failure")
        value = {
            "project_id": project_id,
            "repository": "acme/demo",
            "number": pr_number,
            "state": "closed" if self.merged else "open",
            "merged": self.merged,
            "merged_at": "2026-09-15T12:00:00Z" if self.merged else None,
            "merge_commit_sha": "c" * 40 if self.merged else None,
            "head": HEAD,
            "head_ref": "ai/job-123456",
            "base_ref": "main",
        }
        value.update(deepcopy(self.pr_overrides))
        return value

    async def github_ci(self, *, project_id, commit):
        self.ci_calls += 1
        if self.ci_error:
            raise RuntimeError("injected CI read failure")
        return {
            "project_id": project_id,
            "repository": "acme/demo",
            "state": self.ci_state,
            "commit": self.ci_commit,
        }

    async def github_merge_pull_request(self, **payload):
        self.merge_calls += 1
        assert payload["expected_head"] == HEAD
        assert payload["source_commit"] == SOURCE
        self.merged = True
        return {
            "merged": True,
            "expected_head": HEAD,
            "merge_commit_sha": "c" * 40,
            "merged_at": "2026-09-15T12:00:00Z",
        }


class FakeEngine:
    def __init__(self, storage):
        self.storage = storage
        self.ddev = FakeDdev()
        self.created = []
        self.enqueued = []

    def create_job(self, payload, *, _orchestration=None):
        self.created.append(deepcopy(payload))
        job_id = payload["_job_id"]
        self.storage.jobs[job_id] = {
            "id": job_id,
            "project_id": payload["project_id"],
            "status": "queued",
            "checkpoint": {"work_order": payload["work_order"]},
            "progress": {},
        }
        return job_id

    async def enqueue(self, job_id):
        self.enqueued.append(job_id)


class FakeAudit:
    def __init__(self):
        self.records = {}

    def ensure(self):
        return None

    def _key(self, plan_id, work_order_id, expected_head):
        return (plan_id, work_order_id, expected_head)

    def get(self, *, plan_id, work_order_id, expected_head):
        value = self.records.get(self._key(plan_id, work_order_id, expected_head))
        return deepcopy(value) if value else None

    def approve(self, **payload):
        key = self._key(payload["plan_id"], payload["work_order_id"], payload["expected_head"])
        if key in self.records:
            value = deepcopy(self.records[key])
            value["created"] = False
            return value
        value = {**deepcopy(payload), "status": "approved", "result": None}
        self.records[key] = value
        return {**deepcopy(value), "created": True}

    def finish(self, *, plan_id, work_order_id, expected_head, status, result):
        key = self._key(plan_id, work_order_id, expected_head)
        self.records[key].update({"status": status, "result": deepcopy(result)})
        return deepcopy(self.records[key])


def service(rows, jobs, work_orders, monkeypatch, *, allow_auto=True):
    storage = FakeStorage(deepcopy(jobs))
    engine = FakeEngine(storage)
    store = FakeStore(plan_row(work_orders), rows)
    orchestrator = PlanOrchestrator(storage, engine, store=store)
    orchestrator.merge_audit = FakeAudit()
    def config(project_id):
        return {
            "base_branch": "main",
            "autonomy": {
                "allow_pm_merge": allow_auto,
                "allow_auto_merge_low_risk": allow_auto,
                "allow_production_deploy": False,
            },
        }

    monkeypatch.setattr(merge_module, "project_config", config)
    monkeypatch.setattr(core_module, "project_config", config)
    return orchestrator, storage, engine, store


def test_eligible_pr_merges_once_then_unlocks_dependency(monkeypatch) -> None:
    first = work_order("WO-1")
    second = work_order("WO-2", dependencies=["WO-1"])
    svc, storage, engine, store = service(
        [
            tracked("WO-1", 0, state="awaiting_merge", job_id="job-12345678", pr_number=7),
            tracked("WO-2", 1),
        ],
        {"job-12345678": accepted_job()},
        [first, second],
        monkeypatch,
    )

    result = asyncio.run(svc.tick())

    assert engine.ddev.merge_calls == 1
    assert store.rows[0]["state"] == "completed"
    assert store.rows[0]["detail"]["merge_commit_sha"] == "c" * 40
    assert result["launched"]["work_order_id"] == "WO-2"
    assert store.rows[1]["state"] == "running"
    merged = store.checkpoint_history[0]
    assert merged["kind"] == "merged"
    assert merged["evidence"]["merge_commit"] == "c" * 40
    assert merged["evidence"]["next"] == ["WO-2"]
    audit = next(iter(svc.merge_audit.records.values()))
    assert audit["status"] == "merged"
    assert storage.continuity[0]["event_type"] == "pr_merged"


def test_high_risk_eligible_pr_merges_without_owner_gate(monkeypatch) -> None:
    first = work_order("WO-1")
    first["risk"]["level"] = "high"
    svc, storage, engine, store = service(
        [tracked("WO-1", 0, state="awaiting_merge", job_id="job-12345678", pr_number=7)],
        {"job-12345678": accepted_job()},
        [first],
        monkeypatch,
    )
    storage.jobs["job-12345678"]["checkpoint"]["work_order"]["risk"]["level"] = "high"

    asyncio.run(svc.tick())

    assert engine.ddev.merge_calls == 1
    assert store.rows[0]["state"] == "completed"
    assert store.rows[0]["detail"]["pm_merge"]["requires_human"] is False
    assert store.rows[0]["detail"]["pm_merge"]["evidence"]["risk_level"] == "high"


def test_blocked_parent_reconciles_same_completed_delivery_then_pm_merges(monkeypatch) -> None:
    svc, storage, engine, store = service(
        [tracked("WO-1", 0, state="blocked", job_id="job-12345678")],
        {"job-12345678": accepted_job()},
        [work_order("WO-1")],
        monkeypatch,
    )
    store.plan_status = "blocked"

    result = asyncio.run(svc.tick())

    assert engine.ddev.merge_calls == 1
    assert store.rows[0]["state"] == "completed"
    assert store.plan_status == "completed"
    assert result["launched"] is None
    assert [item["kind"] for item in store.checkpoint_history] == [
        "recovered_accepted",
        "merged",
    ]
    recovered = store.checkpoint_history[0]
    assert recovered["state"] == "awaiting_merge"
    assert recovered["evidence"]["produced_commit"] == HEAD
    assert store.rows[0]["detail"]["recovered_from_blocked"] is True


def test_blocked_parent_ci_none_recovers_from_fresh_exact_head_ci_then_pm_merges(monkeypatch) -> None:
    svc, storage, engine, store = service(
        [tracked("WO-1", 0, state="blocked", job_id="job-12345678")],
        {"job-12345678": ci_none_job()},
        [work_order("WO-1")],
        monkeypatch,
    )
    store.plan_status = "blocked"

    result = asyncio.run(svc.tick())

    assert result["launched"] is None
    assert engine.ddev.merge_calls == 1
    assert engine.ddev.ci_calls == 2
    assert store.rows[0]["state"] == "completed"
    assert store.plan_status == "completed"
    assert [item["kind"] for item in store.checkpoint_history] == [
        "recovered_accepted",
        "merged",
    ]
    assert store.checkpoint_history[0]["evidence"]["produced_commit"] == HEAD
    assert store.rows[0]["detail"]["recovery_ci_source"] == "fresh_github_exact_head"


@pytest.mark.parametrize(
    "case",
    [
        "pr_number",
        "pr_head",
        "pr_branch",
        "pr_base",
        "pr_closed",
        "pr_merged",
        "ci_pending",
        "ci_commit",
        "pr_error",
        "ci_error",
    ],
)
def test_blocked_parent_ci_none_live_recovery_fails_closed(case, monkeypatch) -> None:
    svc, storage, engine, store = service(
        [tracked("WO-1", 0, state="blocked", job_id="job-12345678")],
        {"job-12345678": ci_none_job()},
        [work_order("WO-1")],
        monkeypatch,
    )
    store.plan_status = "blocked"

    if case == "pr_number":
        engine.ddev.pr_overrides["number"] = 8
    elif case == "pr_head":
        engine.ddev.pr_overrides["head"] = "d" * 40
    elif case == "pr_branch":
        engine.ddev.pr_overrides["head_ref"] = "ai/other"
    elif case == "pr_base":
        engine.ddev.pr_overrides["base_ref"] = "develop"
    elif case == "pr_closed":
        engine.ddev.pr_overrides["state"] = "closed"
    elif case == "pr_merged":
        engine.ddev.pr_overrides["merged"] = True
    elif case == "ci_pending":
        engine.ddev.ci_state = "pending"
    elif case == "ci_commit":
        engine.ddev.ci_commit = "c" * 40
    elif case == "pr_error":
        engine.ddev.pr_error = True
    elif case == "ci_error":
        engine.ddev.ci_error = True
    else:
        raise AssertionError(f"unknown case: {case}")

    result = asyncio.run(svc.tick())

    assert result["launched"] is None
    assert engine.ddev.merge_calls == 0
    assert store.rows[0]["state"] == "blocked"
    assert store.plan_status == "blocked"
    assert getattr(store, "checkpoint_history", []) == []


def test_ci_none_awaiting_merge_waits_for_late_ci_without_permanent_block(monkeypatch) -> None:
    svc, storage, engine, store = service(
        [tracked("WO-1", 0, state="awaiting_merge", job_id="job-12345678", pr_number=7)],
        {"job-12345678": ci_none_job()},
        [work_order("WO-1")],
        monkeypatch,
    )
    store.plan_status = "waiting_merge"
    engine.ddev.ci_state = "pending"

    first = asyncio.run(svc.tick())

    assert first["launched"] is None
    assert engine.ddev.merge_calls == 0
    assert store.rows[0]["state"] == "awaiting_merge"
    assert store.plan_status == "waiting_merge"
    assert getattr(store, "checkpoint_history", []) == []

    engine.ddev.ci_state = "success"
    second = asyncio.run(svc.tick())

    assert second["launched"] is None
    assert engine.ddev.merge_calls == 1
    assert store.rows[0]["state"] == "completed"
    assert store.plan_status == "completed"


def test_blocked_parent_recovery_fails_closed_on_delivery_head_mismatch(monkeypatch) -> None:
    job = accepted_job()
    job["result"]["delivery"]["pull_request"]["head"] = "d" * 40
    svc, storage, engine, store = service(
        [tracked("WO-1", 0, state="blocked", job_id="job-12345678")],
        {"job-12345678": job},
        [work_order("WO-1")],
        monkeypatch,
    )
    store.plan_status = "blocked"

    result = asyncio.run(svc.tick())

    assert engine.ddev.merge_calls == 0
    assert store.rows[0]["state"] == "blocked"
    assert store.plan_status == "blocked"
    assert result["launched"] is None
    assert getattr(store, "checkpoint_history", []) == []


@pytest.mark.parametrize(
    "case",
    [
        "result_status",
        "delivery_finalized",
        "delivery_state",
        "ci_state",
        "ci_commit",
        "branch",
        "verified_commit",
        "pr_number",
    ],
)
def test_blocked_parent_recovery_requires_exact_finalized_delivery(case, monkeypatch) -> None:
    job = accepted_job()
    if case == "result_status":
        job["result"]["status"] = "rejected"
    elif case == "delivery_finalized":
        job["result"]["delivery_finalized"] = False
    elif case == "delivery_state":
        job["result"]["delivery"]["state"] = "ci_failed"
    elif case == "ci_state":
        job["result"]["delivery"]["ci"]["state"] = "failure"
    elif case == "ci_commit":
        job["result"]["delivery"]["ci"]["commit"] = "c" * 40
    elif case == "branch":
        job["result"]["delivery"]["pull_request"]["head_ref"] = "ai/other-child"
    elif case == "verified_commit":
        job["result"]["commit"] = ""
    elif case == "pr_number":
        job["result"]["delivery"]["pull_request"]["number"] = None
    else:
        raise AssertionError(f"unknown case: {case}")

    svc, storage, engine, store = service(
        [tracked("WO-1", 0, state="blocked", job_id="job-12345678")],
        {"job-12345678": job},
        [work_order("WO-1")],
        monkeypatch,
    )
    store.plan_status = "blocked"

    result = asyncio.run(svc.tick())

    assert engine.ddev.merge_calls == 0
    assert store.rows[0]["state"] == "blocked"
    assert store.plan_status == "blocked"
    assert result["launched"] is None
    assert getattr(store, "checkpoint_history", []) == []


def test_blocked_parent_recovery_moves_plan_out_of_blocked_before_manual_merge_gate(monkeypatch) -> None:
    svc, storage, engine, store = service(
        [tracked("WO-1", 0, state="blocked", job_id="job-12345678")],
        {"job-12345678": accepted_job()},
        [work_order("WO-1")],
        monkeypatch,
        allow_auto=False,
    )
    store.plan_status = "blocked"

    result = asyncio.run(svc.tick())

    assert engine.ddev.merge_calls == 0
    assert store.rows[0]["state"] == "awaiting_merge"
    assert store.rows[0]["pr_number"] == 7
    assert store.rows[0]["pr_url"] is None
    assert store.plan_status == "waiting_merge"
    assert result["launched"] is None
    assert [item["kind"] for item in store.checkpoint_history] == ["recovered_accepted"]


def test_blocked_plan_never_launches_another_pending_child(monkeypatch) -> None:
    job = accepted_job()
    job["result"]["delivery_finalized"] = False
    svc, storage, engine, store = service(
        [
            tracked("WO-1", 0, state="blocked", job_id="job-12345678"),
            tracked("WO-2", 1),
        ],
        {"job-12345678": job},
        [work_order("WO-1"), work_order("WO-2")],
        monkeypatch,
    )
    store.plan_status = "blocked"

    result = asyncio.run(svc.tick())

    assert result["launched"] is None
    assert engine.created == []
    assert engine.enqueued == []
    assert store.rows[0]["state"] == "blocked"
    assert store.rows[1]["state"] == "pending"
    assert store.plan_status == "blocked"


def test_blocked_parent_recovery_is_idempotent_across_repeated_ticks(monkeypatch) -> None:
    svc, storage, engine, store = service(
        [tracked("WO-1", 0, state="blocked", job_id="job-12345678")],
        {"job-12345678": accepted_job()},
        [work_order("WO-1")],
        monkeypatch,
    )
    store.plan_status = "blocked"

    first = asyncio.run(svc.tick())
    second = asyncio.run(svc.tick())

    assert first["launched"] is None
    assert second["launched"] is None
    assert engine.ddev.merge_calls == 1
    assert store.rows[0]["state"] == "completed"
    assert store.plan_status == "completed"
    assert [item["kind"] for item in store.checkpoint_history] == [
        "recovered_accepted",
        "merged",
    ]


def test_project_opt_out_keeps_stable_manual_merge_gate(monkeypatch) -> None:
    svc, storage, engine, store = service(
        [tracked("WO-1", 0, state="awaiting_merge", job_id="job-12345678", pr_number=7)],
        {"job-12345678": accepted_job()},
        [work_order("WO-1")],
        monkeypatch,
        allow_auto=False,
    )

    asyncio.run(svc.tick())
    first_detail = deepcopy(store.rows[0]["detail"])
    asyncio.run(svc.tick())

    assert engine.ddev.merge_calls == 0
    assert store.rows[0]["state"] == "awaiting_merge"
    assert store.rows[0]["detail"] == first_detail
    assert store.rows[0]["detail"]["pm_merge"]["manual_only"] is True


def test_protected_unapproved_work_stays_owner_manual_merge_gate(monkeypatch) -> None:
    svc, storage, engine, store = service(
        [tracked("WO-1", 0, state="awaiting_merge", job_id="job-12345678", pr_number=7)],
        {"job-12345678": accepted_job(security=True)},
        [work_order("WO-1", security=True)],
        monkeypatch,
    )

    asyncio.run(svc.tick())
    asyncio.run(svc.tick())

    assert engine.ddev.merge_calls == 0
    assert store.rows[0]["state"] == "awaiting_merge"
    assert store.rows[0]["detail"]["pm_merge"]["owner_required"] is True
    assert "protected_change_without_matching_owner_approval" in store.rows[0]["detail"]["pm_merge"]["blockers"]


def test_approved_without_result_is_observation_only_and_never_replayed(monkeypatch) -> None:
    svc, storage, engine, store = service(
        [tracked("WO-1", 0, state="awaiting_merge", job_id="job-12345678", pr_number=7)],
        {"job-12345678": accepted_job()},
        [work_order("WO-1")],
        monkeypatch,
    )
    key = ("plan-1", "WO-1", HEAD)
    svc.merge_audit.records[key] = {
        "plan_id": "plan-1",
        "work_order_id": "WO-1",
        "job_id": "job-12345678",
        "project_id": "default",
        "pr_number": 7,
        "expected_head": HEAD,
        "source_commit": SOURCE,
        "status": "approved",
        "result": None,
    }

    asyncio.run(svc.tick())

    assert engine.ddev.merge_calls == 0
    assert store.rows[0]["state"] == "blocked"
    assert store.rows[0]["detail"]["reason"] == "uncertain_merge_attempt"
    assert svc.merge_audit.records[key]["status"] == "uncertain"


def test_crash_recovery_accepts_only_observed_exact_merged_pr(monkeypatch) -> None:
    svc, storage, engine, store = service(
        [tracked("WO-1", 0, state="awaiting_merge", job_id="job-12345678", pr_number=7)],
        {"job-12345678": accepted_job()},
        [work_order("WO-1")],
        monkeypatch,
    )
    engine.ddev.merged = True
    key = ("plan-1", "WO-1", HEAD)
    svc.merge_audit.records[key] = {
        "plan_id": "plan-1",
        "work_order_id": "WO-1",
        "job_id": "job-12345678",
        "project_id": "default",
        "pr_number": 7,
        "expected_head": HEAD,
        "source_commit": SOURCE,
        "status": "approved",
        "result": None,
    }

    asyncio.run(svc.tick())

    assert engine.ddev.merge_calls == 0
    assert store.rows[0]["state"] == "completed"
    assert svc.merge_audit.records[key]["status"] == "observed_merged"
