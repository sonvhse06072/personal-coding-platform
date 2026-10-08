from __future__ import annotations

import asyncio

import pytest
from copy import deepcopy
from types import SimpleNamespace
from datetime import datetime, timezone

from app.pm_diagnostics import PMDiagnosticsService, _safe_merge_gate_reason


JOB_ID = "92abc7a33bd5438fbb6c2815e9ee3b33"


def blocked_job():
    return {
        "id": JOB_ID,
        "project_id": "chonhac",
        "status": "blocked",
        "source_commit": "a" * 40,
        "branch": "ai/92abc7a33bd5",
        "route": {"strategy": {"profile": "fast"}},
        "progress": {
            "model_calls": 8,
            "tool_calls": 12,
            "test_runs": 2,
            "changed_files": 9,
            "unexpected_scope": True,
            "failure_fingerprints": [
                "fp-old-123",
                "fp-current-456",
                "SECRET fingerprint /home/private",
            ],
            "last_agent_failure_kind": "deterministic_check",
        },
        "checkpoint": {
            "project_baseline": {"revision": "pilot-r3"},
            "canonical_intake": {
                "mode": "direct",
                "bounded_direct": True,
            },
            "last_verification_summary": {
                "passed": False,
                "phases": [
                    {"phase": "unit", "passed": True, "stdout": "SECRET-unit"},
                    {"phase": "kernel", "passed": False, "stderr": "/home/private"},
                ],
                "raw": "SECRET raw verification",
            },
            "deterministic_verification_failure_streak": {
                "signature": "verify-fp-abc123",
                "diff_hash": "diff-abc123",
                "count": 3,
                "limit": 2,
                "failing_phases": [
                    "kernel",
                    "unsafe phase /home/private",
                ],
                "verification_attempt": 4,
                "commands": ["cat /home/private/token"],
            },
            "failure_context": {
                "version": 1,
                "kind": "semantic_repair",
                "source": "pm_reassessment",
                "message": "SECRET context message /home/private/token",
                "diff_hash": "diff-abc123",
                "decision_key": "decision:key:123",
            },
        },
        "result": {
            "reason": "reassessment_stopped",
            "last_failure": "SECRET raw failure /home/private",
            "reassess": {
                "action": "stop",
                "reason": "scope expansion requires reassessment",
                "signals": ["scope_expansion"],
            },
            "commit": None,
            "delivery": {
                "state": None,
                "ci": {},
                "pull_request": {},
            },
        },
    }


class FakeStorage:
    def __init__(self):
        self.job = blocked_job()

    def get(self, job_id):
        return deepcopy(self.job) if job_id == JOB_ID else None

    def recent_events(self, job_ids, per_job_limit=30):
        assert job_ids == [JOB_ID]
        return [
            {
                "id": 9,
                "job_id": JOB_ID,
                "event_type": "developer_command_completed",
                "phase": "execution",
                "level": "error",
                "message": "raw command message SECRET-ACTIVITY",
                "data": {
                    "command": "cat /home/private/token",
                    "output": "SECRET-ACTIVITY /home/private/token",
                    "status": "failed",
                    "exit_code": 1,
                },
                "created_at": datetime(2026, 10, 7, tzinfo=timezone.utc),
            },
            {
                "id": 10,
                "job_id": JOB_ID,
                "event_type": "job_blocked",
                "phase": "blocked",
                "level": "error",
                "message": "Runtime blocked",
                "data": {
                    "from_status": "evaluating",
                    "to_status": "blocked",
                },
                "created_at": datetime(2026, 10, 7, tzinfo=timezone.utc),
            },
        ]

    def count_active_engineering_jobs(self):
        return 0


class FakeControls:
    def standalone_remote_actions(self, job_id):
        assert job_id == JOB_ID
        return {
            "job_id": job_id,
            "generation": "generation-exact",
            "reason": "reassessment_stopped",
            "phase": "reassessment",
            "actions": [
                {
                    "action_type": "pm_scope_reassess",
                    "label": "PM review file scope",
                }
            ],
        }

    def remote_pending_actions(self, job_id):
        assert job_id == JOB_ID
        return {
            "job_id": job_id,
            "plan_id": "plan-1",
            "work_order_id": "WO-1",
            "generation": "orchestrated-generation",
            "actions": [
                {
                    "control_action_id": "action-exact-12345678",
                    "action_type": "resume_same",
                }
            ],
        }


class FakeCollaboration:
    def list(self, job_id):
        assert job_id == JOB_ID
        return []


class FakeDdev:
    def __init__(self):
        self.comments = []

    async def github_pull_request(self, **kwargs):
        return {}

    async def github_ci(self, **kwargs):
        return {}

    async def project_worktree_state(self, *, project_id):
        return {
            "project_id": project_id,
            "workspace_mode": "direct",
            "branch": "main",
            "head": "a" * 40,
            "clean": True,
            "base_branch": "main",
            "origin_base_head": "a" * 40,
        }

    async def health(self):
        return True

    async def upsert_managed_comment(self, **kwargs):
        self.comments.append(kwargs)
        return {
            "comment_id": 900,
            "comment_url": "https://github.com/acme/demo/issues/77#issuecomment-900",
            "state": "created",
        }


class FakeRouter:
    async def health(self):
        return True


class FakeEngine:
    def __init__(self):
        self.ddev = FakeDdev()
        self.router = FakeRouter()
        self.collaboration = FakeCollaboration()


class FakePlanStore:
    def __init__(self, project_id="chonhac"):
        self.project_id = project_id

    def orchestration(self, plan_id):
        if plan_id != "plan-1":
            return None
        return {
            "plan_id": plan_id,
            "project_id": self.project_id,
        }


class FakeOrchestrator:
    def __init__(self, project_id="chonhac"):
        self.controls = FakeControls()
        self.store = FakePlanStore(project_id)

    def progress(self, plan_id):
        return {
            "plan_id": plan_id,
            "state": "supervised_hold",
            "next": ["EE-0-02"],
            "supervision": {
                "mode": "supervised",
                "state": "held",
                "generation": 4,
                "continuation_key": "plan:continue:" + ("d" * 64),
                "ready_work_order_ids": ["EE-0-02"],
                "checkpoint": {"id": 9, "checkpoint_key": "checkpoint-9"},
            },
            "last_checkpoint": {
                "id": 8,
                "work_order_id": "EE-0-01",
                "kind": "merged",
            },
        }


def test_diagnostics_publish_sanitized_exact_blocker_evidence():
    storage = FakeStorage()
    engine = FakeEngine()
    service = PMDiagnosticsService(
        storage,
        engine,
        FakeOrchestrator(),
    )

    result = asyncio.run(
        service.collect_and_publish(
            project_id="chonhac",
            issue_number=77,
            control_comment_id=123,
            job_id=JOB_ID,
            plan_id="plan-1",
            collectors=[
                "job",
                "attention",
                "plan_progress",
                "recent_activity",
                "worktree",
                "runtime_health",
            ],
        )
    )

    assert result["status"] == "published"
    assert result["comment_id"] == 900
    assert len(engine.ddev.comments) == 1
    request = engine.ddev.comments[0]
    assert request["project_id"] == "chonhac"
    assert request["issue_number"] == 77
    assert request["channel"] == "diagnostic"
    assert request["identity"] == "control:123"
    body = request["body"]
    assert "reassessment_stopped" in body
    assert "generation-exact" in body
    assert "pm_scope_reassess" in body
    assert "supervised_hold" in body
    assert '"last_verification_summary"' in body
    assert '"phase": "unit"' in body
    assert '"phase": "kernel"' in body
    assert '"passed": false' in body
    assert '"signature": "verify-fp-abc123"' in body
    assert '"count": 3' in body
    assert '"limit": 2' in body
    assert '"verification_attempt": 4' in body
    assert '"kind": "semantic_repair"' in body
    assert '"source": "pm_reassessment"' in body
    assert '"decision_key": "decision:key:123"' in body
    assert "fp-current-456" in body
    assert "deterministic_check" in body
    assert "SECRET raw failure" not in body
    assert "SECRET context message" not in body
    assert "SECRET raw verification" not in body
    assert "SECRET-unit" not in body
    assert "SECRET fingerprint" not in body
    assert "SECRET-ACTIVITY" not in body
    assert "cat /home/private/token" not in body
    assert "/home/private" not in body


def test_diagnostics_reject_cross_project_plan_binding():
    storage = FakeStorage()
    engine = FakeEngine()
    service = PMDiagnosticsService(
        storage,
        engine,
        FakeOrchestrator(project_id="other-project"),
    )

    try:
        asyncio.run(
            service.collect_and_publish(
                project_id="chonhac",
                issue_number=77,
                control_comment_id=124,
                job_id=JOB_ID,
                plan_id="plan-1",
                collectors=["plan_progress"],
            )
        )
    except RuntimeError as exc:
        assert "plan project identity mismatch" in str(exc)
    else:
        raise AssertionError("cross-project diagnostic plan must fail closed")

    assert engine.ddev.comments == []


def test_orchestrated_attention_exposes_exact_durable_action_identity():
    storage = FakeStorage()
    storage.job["checkpoint"].pop("canonical_intake", None)
    storage.job["checkpoint"]["pending_decision"] = {
        "key": "architecture_choice",
        "source": "reassessment",
        "decision": {
            "required": True,
            "triggers": ["architecture_choice"],
            "reason": "Choose the already-reviewed architecture boundary.",
        },
    }
    engine = FakeEngine()
    service = PMDiagnosticsService(
        storage,
        engine,
        FakeOrchestrator(),
    )

    result = asyncio.run(
        service.collect_and_publish(
            project_id="chonhac",
            issue_number=77,
            control_comment_id=125,
            job_id=JOB_ID,
            plan_id="plan-1",
            collectors=["job", "attention"],
        )
    )

    assert result["status"] == "published"
    body = engine.ddev.comments[-1]["body"]
    assert "orchestrated-generation" in body
    assert "action-exact-12345678" in body
    assert "resume_same" in body
    assert "plan-1" in body
    assert "WO-1" in body
    assert "architecture_choice" in body
    assert "Choose the already-reviewed architecture boundary." in body
    assert "SECRET raw failure" not in body


def test_failure_evidence_rejects_malformed_list_shapes():
    storage = FakeStorage()
    storage.job["checkpoint"]["deterministic_verification_failure_streak"][
        "failing_phases"
    ] = "kernel"
    storage.job["progress"]["failure_fingerprints"] = "fingerprint"
    engine = FakeEngine()
    service = PMDiagnosticsService(
        storage,
        engine,
        FakeOrchestrator(),
    )

    asyncio.run(
        service.collect_and_publish(
            project_id="chonhac",
            issue_number=77,
            control_comment_id=126,
            job_id=JOB_ID,
            plan_id="plan-1",
            collectors=["job"],
        )
    )

    body = engine.ddev.comments[-1]["body"]
    assert '"failing_phases"' not in body
    assert '"recent_failure_fingerprints"' not in body
    assert '"signature": "verify-fp-abc123"' in body


def test_safe_merge_gate_reason_requires_exact_checkpoint_and_fixed_code():
    progress = {
        "state": "blocked",
        "last_checkpoint": {
            "id": 182,
            "checkpoint_key": "wo:blocked:exact",
            "work_order_id": "EE-0-04",
            "job_id": JOB_ID,
            "kind": "blocked",
            "state": "blocked",
        },
    }
    checkpoint = {
        **progress["last_checkpoint"],
        "evidence": {"reason": "pm_merge_ineligible:pm_evidence_has_unresolved_risks"},
    }
    snapshot = {"blocked_checkpoint": checkpoint}
    assert _safe_merge_gate_reason(snapshot, progress) == (
        "pm_merge_ineligible:pm_evidence_has_unresolved_risks"
    )

    for known in (
        "pm_merge_replay_rejected",
        "uncertain_merge_attempt",
        "pull_request_closed_without_merge",
    ):
        checkpoint["evidence"]["reason"] = known
        assert _safe_merge_gate_reason(snapshot, progress) == known

    for untrusted in (
        "pm_merge_ineligible:bad/secret",
        "pm_merge_ineligible:arbitrary_secret_code",
        "arbitrary /home/owner/token",
        "pm_merge_ineligible:" + "x" * 140,
        "orchestrated_job_missing",
    ):
        checkpoint["evidence"]["reason"] = untrusted
        assert _safe_merge_gate_reason(snapshot, progress) is None

    checkpoint["evidence"]["reason"] = "pm_merge_ineligible:ci_not_successful"
    progress["last_checkpoint"]["id"] = 183
    assert _safe_merge_gate_reason(snapshot, progress) is None
    progress["last_checkpoint"]["id"] = 182
    progress["state"] = "awaiting_merge"
    assert _safe_merge_gate_reason(snapshot, progress) is None


def test_diagnostics_publishes_only_bound_merge_gate_reason():
    checkpoint = {
        "id": 182,
        "checkpoint_key": "wo:blocked:exact",
        "work_order_id": "EE-0-04",
        "job_id": JOB_ID,
        "kind": "blocked",
        "state": "blocked",
        "evidence": {"reason": "pm_merge_ineligible:pm_evidence_has_unresolved_risks"},
    }

    class BlockedPlanStore(FakePlanStore):
        def progress_snapshot(self, plan_id):
            assert plan_id == "plan-1"
            return {"blocked_checkpoint": deepcopy(checkpoint)}

    class BlockedOrchestrator(FakeOrchestrator):
        def __init__(self):
            super().__init__()
            self.store = BlockedPlanStore()

        def progress(self, plan_id):
            assert plan_id == "plan-1"
            return {
                "plan_id": plan_id,
                "state": "blocked",
                "next": [],
                "last_checkpoint": {
                    key: checkpoint[key]
                    for key in ("id", "checkpoint_key", "work_order_id", "job_id", "kind", "state")
                },
            }

    storage = FakeStorage()
    engine = FakeEngine()
    service = PMDiagnosticsService(storage, engine, BlockedOrchestrator())
    result = asyncio.run(service.collect_and_publish(
        project_id="chonhac",
        issue_number=77,
        control_comment_id=127,
        job_id=None,
        plan_id="plan-1",
        collectors=["plan_progress"],
    ))
    assert result["status"] == "published"
    body = engine.ddev.comments[-1]["body"]
    assert '"merge_gate_reason": "pm_merge_ineligible:pm_evidence_has_unresolved_risks"' in body

    checkpoint["evidence"]["reason"] = "pm_merge_ineligible:bad/private"
    asyncio.run(service.collect_and_publish(
        project_id="chonhac",
        issue_number=77,
        control_comment_id=128,
        job_id=None,
        plan_id="plan-1",
        collectors=["plan_progress"],
    ))
    sanitized = engine.ddev.comments[-1]["body"]
    assert "merge_gate_reason" not in sanitized
    assert "bad/private" not in sanitized



def test_late_review_diagnostic_publishes_registry_only_capacity_floor(monkeypatch):
    from app import pm_diagnostics

    storage = FakeStorage()
    storage.job["status"] = "completed"
    storage.job["result"] = {
        **dict(storage.job.get("result") or {}),
        "diff": {"diff_hash": "d" * 64},
    }
    engine = FakeEngine()
    orchestrator = FakeOrchestrator()
    orchestrator.late_reviews = SimpleNamespace(
        store=SimpleNamespace(
            status=lambda *, plan_id, job_id: {
                "id": 15,
                "status": "no_capacity",
                "expected_head": "b" * 40,
                "checkpoint_id": 182,
                "reviewer_provider": None,
                "reviewer_model": None,
                "review_mode": None,
                "attestation_id": None,
            },
        ),
    )
    monkeypatch.setattr(
        pm_diagnostics, "registered_review_capacity",
        lambda job: {
            "status": "registry_evaluated",
            "source": "registered_models_not_live_capacity",
            "max_writer_tier": "premium",
            "max_writer_review_score": 9,
            "strict_higher_tier_registry_model_ids": [],
            "capacity_is_live": False,
        },
    )
    service = PMDiagnosticsService(storage, engine, orchestrator)

    response = asyncio.run(
        service.collect_and_publish(
            project_id="chonhac",
            issue_number=77,
            control_comment_id=777,
            plan_id="plan-1",
            job_id=JOB_ID,
            collectors=["late_review"],
        )
    )
    assert response["status"] == "published"
    body = engine.ddev.comments[-1]["body"]
    assert '"status": "no_capacity"' in body
    assert '"max_writer_tier": "premium"' in body
    assert '"strict_higher_tier_registry_model_ids": []' in body
    assert '"capacity_is_live": false' in body
    assert '"persisted_accepted_diff_sha256": "' + "d" * 64 + '"' in body
    assert "SECRET" not in body




def test_reviewer_capacity_diagnostic_only_checks_completed_job_in_exact_blocked_gate(monkeypatch):
    from app import pm_diagnostics as module

    storage = FakeStorage()
    storage.job["status"] = "completed"
    engine = FakeEngine()
    seen = []
    async def fake_probe(*, job, router):
        seen.append((job["id"], router))
        return {
            "status": "no_eligible_cross_provider_now",
            "staffing_checked": True,
            "staffing_is_model_invocation": False,
        }
    monkeypatch.setattr(module, "probe_reviewer_capacity", fake_probe)

    class ExactBlockedStore(FakePlanStore):
        def __init__(self):
            super().__init__("chonhac")
            self.reason = "pm_merge_ineligible:required_review_independence_not_satisfied"
            self.plan_state = "blocked"

        def orchestration(self, plan_id):
            value = super().orchestration(plan_id)
            return {**value, "status": self.plan_state} if value else None

        def work_orders(self, plan_id):
            return [{
                "work_order_id": "WO-1",
                "job_id": JOB_ID,
                "state": "blocked",
                "detail": {"reason": self.reason},
            }]

    orchestration = FakeOrchestrator()
    orchestration.store = ExactBlockedStore()
    service = PMDiagnosticsService(storage, engine, orchestration)

    response = asyncio.run(service.collect_and_publish(
        project_id="chonhac", issue_number=77, control_comment_id=184,
        job_id=JOB_ID, plan_id="plan-1",
        collectors=["reviewer_capacity"],
    ))
    assert response["status"] == "published"
    assert response["collectors"] == ["reviewer_capacity"]
    assert seen == [(JOB_ID, engine.router)]
    body = engine.ddev.comments[-1]["body"]
    assert "no_eligible_cross_provider_now" in body
    assert '"staffing_is_model_invocation": false' in body

    for state, reason in (
        ("active", "pm_merge_ineligible:required_review_independence_not_satisfied"),
        ("blocked", "unrelated_failure"),
    ):
        orchestration.store.plan_state = state
        orchestration.store.reason = reason
        with pytest.raises(RuntimeError, match="exact blocked merge gate"):
            asyncio.run(service.collect_and_publish(
                project_id="chonhac", issue_number=77,
                control_comment_id=185, job_id=JOB_ID,
                plan_id="plan-1", collectors=["reviewer_capacity"],
            ))
        assert len(seen) == 1
