from __future__ import annotations

import pytest
from pathlib import Path

from app.continuity import (
    MANAGED_END,
    MANAGED_START,
    assert_mutable_continuity_target,
    continuity_proposal,
    render_managed_current_state,
)


def proposal() -> dict:
    row = {
        "id": "job-1",
        "project_id": "project-a",
        "status": "completed",
        "branch": "ai/job-1",
        "checkpoint": {"work_order": {"id": "WO-1"}},
        "result": {"status": "accepted"},
    }
    return continuity_proposal(
        row,
        event_type="job_terminal",
        attention_summary={
            "human_interventions": 1,
            "avoidable_blocks": 0,
            "time_waiting_for_owner_seconds": 12.0,
        },
        telemetry={
            "task_outcome": "accepted",
            "first_pass_success": True,
            "repair_count": 0,
            "provider_failures": 0,
            "quota_failures": 0,
        },
    )


def test_continuity_renderer_replaces_managed_state_instead_of_appending_history() -> None:
    existing = (
        "# Current state\n\n"
        f"{MANAGED_START}\nold stale state\n{MANAGED_END}\n\n"
        "## Durable notes\nKeep this text.\n"
    )

    first = render_managed_current_state(existing, proposal())
    second = render_managed_current_state(first, {**proposal(), "status": "blocked", "outcome": "blocked"})

    assert first.count(MANAGED_START) == 1
    assert second.count(MANAGED_START) == 1
    assert "old stale state" not in first
    assert "Runtime state: `blocked`; outcome: `blocked`." in second
    assert "## Durable notes\nKeep this text." in second


def test_continuity_renderer_requires_existing_managed_markers() -> None:
    with pytest.raises(ValueError, match="managed continuity markers"):
        render_managed_current_state("# Current state\n", proposal())


def test_continuity_authority_allows_only_mutable_current_state_document() -> None:
    assert_mutable_continuity_target("docs/project/current-state.md")

    for path in (
        "docs/project/architecture.md",
        "docs/project/constitution.md",
        "docs/project/efficiency-model.md",
        "docs/project/roadmap.md",
    ):
        with pytest.raises(ValueError, match="only target docs/project/current-state.md"):
            assert_mutable_continuity_target(path)


def test_proposal_explicitly_denies_direct_durable_policy_writes() -> None:
    value = proposal()
    assert value["authority"]["mutable_target"] == "docs/project/current-state.md"
    assert value["authority"]["direct_durable_policy_write_allowed"] is False
    assert value["authority"]["application_path"] == "normal_git_branch_pr_authority"


def test_continuity_carries_only_bounded_incident_candidate() -> None:
    row = {
        "id": "job-incident",
        "project_id": "project-a",
        "status": "blocked",
        "branch": "ai/job-incident",
        "checkpoint": {"work_order": {"id": "WO-incident"}},
        "result": {"reason": "repeated_deterministic_verification_failure"},
    }
    candidate = {
        "id": "incident:abc",
        "signals": ["verification_retry_anomaly"],
        "evidence_refs": ["runtime:job:job-incident"],
    }

    value = continuity_proposal(
        row,
        event_type="job_blocked",
        telemetry={
            "task_outcome": "blocked",
            "incident_learning": {"candidate": candidate},
        },
    )

    assert value["incident_learning"]["candidate"] == candidate
    assert "raw_log" not in str(value["incident_learning"])



def test_real_project_t1_has_single_replaceable_continuity_block() -> None:
    repo_root = Path(__file__).resolve().parents[3]
    path = repo_root / "docs/project/current-state.md"
    existing = path.read_text(encoding="utf-8")
    assert existing.count(MANAGED_START) == 1
    assert existing.count(MANAGED_END) == 1

    first = render_managed_current_state(existing, proposal())
    second = render_managed_current_state(first, proposal())
    assert first == second  # idempotent; no growing history
    assert first.count(MANAGED_START) == first.count(MANAGED_END) == 1
    assert "No automated `pr_merged` continuity publication" not in first
    assert "## Active PCP issues and owner attention" in first
    assert "## Immediate next safe actions" in first
    assert "## Standing safety boundary" in first
    assert "Event: `job_terminal`" in first
    assert len(first.encode("utf-8")) < 15000
