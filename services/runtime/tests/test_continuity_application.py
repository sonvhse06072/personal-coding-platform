from __future__ import annotations

import asyncio

from app.continuity import MANAGED_END, MANAGED_START
from app.orchestrator_merge import PlanOrchestrator


class FakeDdev:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.calls: list[dict] = []

    async def apply_continuity(self, **payload):
        self.calls.append(dict(payload))
        if self.fail:
            raise RuntimeError("publication unavailable")
        return {"state": "merged", "pr_number": 123}


class FakeEngine:
    def __init__(self, *, fail: bool = False) -> None:
        self.ddev = FakeDdev(fail=fail)


class FakeStorage:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def record_external_continuity(self, **payload):
        self.calls.append(dict(payload))
        return {
            "event_type": payload["event_type"],
            "project_id": payload["project_id"],
            "job_id": payload["job_id"],
            "status": "completed",
            "work_order_id": "WO-1",
            "branch": "ai/job-1",
            "outcome": "accepted",
            "attention": {"human_interventions": 0, "avoidable_blocks": 0},
            "telemetry": {
                "first_pass_success": True,
                "repair_count": 0,
                "provider_failures": 0,
                "quota_failures": 0,
            },
            "detail": dict(payload["payload"]),
            "authority": {
                "mutable_target": "docs/project/current-state.md",
                "direct_durable_policy_write_allowed": False,
                "application_path": "normal_git_branch_pr_authority",
            },
        }


def service(*, fail: bool = False) -> PlanOrchestrator:
    value = PlanOrchestrator.__new__(PlanOrchestrator)
    value.engine = FakeEngine(fail=fail)
    return value


def proposal() -> dict:
    return {
        "event_type": "pr_merged",
        "project_id": "fixture",
        "job_id": "job-1",
        "status": "completed",
        "work_order_id": "WO-1",
        "branch": "ai/job-1",
        "outcome": "accepted",
        "attention": {"human_interventions": 0, "avoidable_blocks": 0},
        "telemetry": {
            "first_pass_success": True,
            "repair_count": 0,
            "provider_failures": 0,
            "quota_failures": 0,
        },
        "detail": {"pr_number": 9, "authority": "pm_controlled_merge"},
    }


def test_pr_merged_continuity_sends_only_bounded_rendered_payload_to_executor() -> None:
    svc = service()

    asyncio.run(svc._apply_merge_continuity(proposal()))

    calls = svc.engine.ddev.calls
    assert len(calls) == 1
    payload = calls[0]
    assert payload["event_type"] == "pr_merged"
    assert payload["project_id"] == "fixture"
    assert len(payload["continuity_key"]) == 64
    assert payload["managed_section"].startswith(MANAGED_START)
    assert payload["managed_section"].endswith(MANAGED_END)
    assert payload["managed_section"].count(MANAGED_START) == 1
    assert payload["managed_section"].count(MANAGED_END) == 1
    assert "github" not in payload
    assert "repository" not in payload
    assert "path" not in payload


def test_continuity_application_failure_is_advisory_after_engineering_merge() -> None:
    svc = service(fail=True)

    # Publication errors are deliberately swallowed; an already-confirmed
    # engineering merge must not be turned back into a task failure.
    asyncio.run(svc._apply_merge_continuity(proposal()))

    assert len(svc.engine.ddev.calls) == 1


def test_non_merge_proposals_are_not_auto_applied_in_b1() -> None:
    svc = service()
    value = {**proposal(), "event_type": "job_blocked"}

    asyncio.run(svc._apply_merge_continuity(value))

    assert svc.engine.ddev.calls == []


def test_record_merge_continuity_returns_persisted_proposal_for_post_reconcile_application() -> None:
    svc = service()
    svc.storage = FakeStorage()

    value = svc._record_merge_continuity(
        {"project_id": "fixture"},
        {"id": "job-1"},
        {
            "number": 9,
            "merge_commit_sha": "c" * 40,
            "merged_at": "2026-09-16T18:14:49Z",
        },
    )

    assert value is not None
    assert value["event_type"] == "pr_merged"
    assert value["detail"]["authority"] == "pm_controlled_merge"
    assert svc.storage.calls[0]["event_type"] == "pr_merged"
