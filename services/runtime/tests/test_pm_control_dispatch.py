from __future__ import annotations

import asyncio
from copy import deepcopy

import pytest

from app.pm_control import PMControlEnvelope
from app.pm_control_dispatch import PMControlDispatcher
from app import pm_control_dispatch


HEAD = "b" * 40
SOURCE = "a" * 40


def direct_job():
    route = {
        "strategy": {
            "human_decision": {"required": False, "triggers": []},
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
        "project_id": "demo",
        "status": "completed",
        "source_commit": SOURCE,
        "branch": "ai/job-123456",
        "task": {"title": "Bounded fix", "task_type": "bugfix", "flags": []},
        "repo_analysis": {
            "security_sensitive": False,
            "authentication_change": False,
            "authorization_change": False,
            "destructive_migration": False,
            "production_write": False,
        },
        "checkpoint": {
            "project_baseline": {"revision": "v1", "authority": [], "references": {}},
            "canonical_intake": {
                "policy_version": 1,
                "mode": "direct",
                "bounded_direct": True,
                "decomposition_required": False,
            },
            "approved_decisions": [],
        },
        "route": route,
        "progress": {"required_checks_passed": True, "unexpected_scope": False},
        "result": {
            "status": "accepted",
            "commit": HEAD,
            "verification": {"passed": True},
            "review": {"verdict": "pass", "findings": []},
            "diff": {"diff_hash": "diff-1", "changed_files": []},
            "pm_evidence": {
                "unresolved_risks": [],
                "protected_decision_flags": [],
            },
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


class FakeStorage:
    def __init__(self):
        self.jobs = {"job-12345678": direct_job()}

    def get(self, job_id):
        row = self.jobs.get(job_id)
        return deepcopy(row) if row is not None else None


class FakeDdev:
    def __init__(self):
        self.merged = False
        self.merge_calls = []

    async def github_pull_request(self, *, project_id, pr_number):
        return {
            "project_id": project_id,
            "number": pr_number,
            "state": "closed" if self.merged else "open",
            "merged": self.merged,
            "head": HEAD,
            "head_ref": "ai/job-123456",
            "base_ref": "main",
            "merge_commit_sha": "c" * 40 if self.merged else None,
        }

    async def github_ci(self, *, project_id, commit):
        return {"state": "success", "commit": commit}

    async def github_merge_pull_request(self, **kwargs):
        self.merge_calls.append(kwargs)
        self.merged = True
        return {"merged": True, "merge_commit_sha": "c" * 40}


class FakeEngine:
    def __init__(self):
        self.ddev = FakeDdev()
        self.decisions = []
        self.repairs = []

    async def resolve_human_decision(
        self,
        job_id,
        *,
        action,
        note,
        expected_decision_key,
    ):
        self.decisions.append(
            (job_id, action, note, expected_decision_key)
        )
        return {"id": job_id, "status": "queued"}

    async def request_review_repair(
        self,
        job_id,
        *,
        expected_commit,
        finding,
        evidence,
        references,
    ):
        self.repairs.append(
            {
                "job_id": job_id,
                "expected_commit": expected_commit,
                "finding": finding,
                "evidence": evidence,
                "references": references,
            }
        )
        return {"id": job_id, "status": "queued"}


class FakeControls:
    def __init__(self):
        self.actions = {
            "control-12345678": {
                "action_id": "control-12345678",
                "action_type": "pm_scope_reassess",
                "job_id": "job-12345678",
                "generation_fingerprint": "generation-1",
            }
        }
        self.executed = []

    def get_action(self, action_id):
        value = self.actions.get(action_id)
        return deepcopy(value) if value else None

    async def execute_remote(
        self,
        action_id,
        *,
        expected_job_id,
        expected_generation,
    ):
        self.executed.append(
            (action_id, expected_job_id, expected_generation)
        )
        return {
            "status": "executed",
            "action_id": action_id,
            "job_id": expected_job_id,
        }


class FakeStore:
    def orchestration(self, plan_id):
        if plan_id != "plan-1":
            return None
        return {"plan_id": plan_id, "project_id": "demo"}


class FakeOrchestrator:
    def __init__(self):
        self.store = FakeStore()
        self.controls = FakeControls()
        self.ticks = 0
        self.continues = []

    async def tick(self):
        self.ticks += 1
        return {"launched": None}

    async def continue_plan(self, **kwargs):
        self.continues.append(kwargs)
        return {"status": "active", "released_generation": kwargs["generation"]}


def dispatcher():
    storage = FakeStorage()
    engine = FakeEngine()
    orchestrator = FakeOrchestrator()
    return PMControlDispatcher(storage, engine, orchestrator), storage, engine, orchestrator


def envelope(action, **values):
    return PMControlEnvelope(
        schema_version=1,
        project_id="demo",
        action=action,
        **values,
    )


def test_remote_decision_and_review_repair_use_exact_existing_primitives():
    dispatch, _, engine, orchestrator = dispatcher()

    status, result = asyncio.run(
        dispatch.dispatch(
            envelope(
                "resolve_job_decision",
                job_id="job-12345678",
                decision_key="decision:key:1",
                decision="approve",
                note="Owner approved",
            ),
            comment_id=10,
            issue_number=77,
        )
    )
    assert status == "executed"
    assert result["job_status"] == "queued"
    assert engine.decisions == [
        (
            "job-12345678",
            "approve",
            "Owner approved",
            "decision:key:1",
        )
    ]
    assert orchestrator.ticks == 1

    status, _ = asyncio.run(
        dispatch.dispatch(
            envelope(
                "review_repair",
                job_id="job-12345678",
                expected_commit=HEAD,
                finding="Repair the exact reviewed finding.",
                references=["GH-77"],
            ),
            comment_id=11,
            issue_number=77,
        )
    )
    assert status == "executed"
    assert engine.repairs[0]["expected_commit"] == HEAD
    assert engine.repairs[0]["evidence"]["comment_id"] == 11


def test_remote_resume_requires_runtime_issued_action_type_and_generation():
    dispatch, _, _, orchestrator = dispatcher()

    status, result = asyncio.run(
        dispatch.dispatch(
            envelope(
                "resume_same_job",
                job_id="job-12345678",
                blocker_generation="generation-1",
                control_action_id="control-12345678",
            ),
            comment_id=12,
            issue_number=77,
        )
    )
    assert status == "executed"
    assert result["underlying_action_type"] == "pm_scope_reassess"
    assert orchestrator.controls.executed == [
        ("control-12345678", "job-12345678", "generation-1")
    ]

    orchestrator.controls.actions["control-12345678"]["action_type"] = "recheck_ci"
    with pytest.raises(RuntimeError, match="cannot execute action_type"):
        asyncio.run(
            dispatch.dispatch(
                envelope(
                    "resume_same_job",
                    job_id="job-12345678",
                    blocker_generation="generation-1",
                    control_action_id="control-12345678",
                ),
                comment_id=13,
                issue_number=77,
            )
        )


def test_supervised_continue_preserves_exact_generation_contract():
    dispatch, _, _, orchestrator = dispatcher()
    key = "plan:continue:" + ("d" * 64)

    status, result = asyncio.run(
        dispatch.dispatch(
            envelope(
                "continue_supervised_plan",
                plan_id="plan-1",
                generation=4,
                continuation_key=key,
                checkpoint_id=9,
                checkpoint_key="checkpoint-9",
                ready_work_order_ids=["EE-0-02"],
            ),
            comment_id=14,
            issue_number=63,
        )
    )

    assert status == "executed"
    assert result["generation"] == 4
    assert orchestrator.continues == [
        {
            "plan_id": "plan-1",
            "generation": 4,
            "continuation_key": key,
            "checkpoint_id": 9,
            "checkpoint_key": "checkpoint-9",
            "ready_work_order_ids": ["EE-0-02"],
        }
    ]


def test_standalone_merge_revalidates_exact_job_pr_ci_and_confirms_merge(monkeypatch):
    dispatch, _, engine, _ = dispatcher()
    monkeypatch.setattr(
        pm_control_dispatch,
        "project_config",
        lambda project_id: {
            "base_branch": "main",
            "autonomy": {
                "allow_pm_merge": True,
                "allow_auto_merge_low_risk": True,
                "allow_production_deploy": False,
            },
        },
    )

    status, result = asyncio.run(
        dispatch.dispatch(
            envelope(
                "merge_standalone_job",
                job_id="job-12345678",
                source_commit=SOURCE,
                expected_commit=HEAD,
                expected_head=HEAD,
                branch="ai/job-123456",
                pr_number=7,
                base_branch="main",
                review_reference="GH-77 exact diff reviewed",
            ),
            comment_id=15,
            issue_number=77,
        )
    )

    assert status == "executed"
    assert result["merge_commit_sha"] == "c" * 40
    assert result["eligibility"]["eligible"] is True
    assert len(engine.ddev.merge_calls) == 1
    assert engine.ddev.merge_calls[0]["expected_head"] == HEAD


def test_standalone_merge_rejects_stale_command_before_github_mutation(monkeypatch):
    dispatch, _, engine, _ = dispatcher()
    monkeypatch.setattr(
        pm_control_dispatch,
        "project_config",
        lambda project_id: {
            "base_branch": "main",
            "autonomy": {
                "allow_pm_merge": True,
                "allow_auto_merge_low_risk": True,
            },
        },
    )

    with pytest.raises(RuntimeError, match="expected head mismatch"):
        asyncio.run(
            dispatch.dispatch(
                envelope(
                    "merge_standalone_job",
                    job_id="job-12345678",
                    source_commit=SOURCE,
                    expected_commit=HEAD,
                    expected_head="e" * 40,
                    branch="ai/job-123456",
                    pr_number=7,
                    base_branch="main",
                    review_reference="stale",
                ),
                comment_id=16,
                issue_number=77,
            )
        )

    assert engine.ddev.merge_calls == []


def test_future_slice_actions_are_explicitly_non_mutating():
    dispatch, _, _, _ = dispatcher()

    status, result = asyncio.run(
        dispatch.dispatch(
            envelope(
                "request_diagnostics",
                job_id="job-12345678",
                diagnostic_collectors=["job"],
            ),
            comment_id=17,
            issue_number=77,
        )
    )

    assert status == "unsupported_action_dispatch"
    assert result["status"] == "pending_future_slice"
