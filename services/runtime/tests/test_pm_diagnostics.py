from __future__ import annotations

import asyncio
from copy import deepcopy
from datetime import datetime, timezone

from app.pm_diagnostics import PMDiagnosticsService


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
        },
        "checkpoint": {
            "project_baseline": {"revision": "pilot-r3"},
            "canonical_intake": {
                "mode": "direct",
                "bounded_direct": True,
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
    assert "SECRET raw failure" not in body
    assert "SECRET-ACTIVITY" not in body
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
