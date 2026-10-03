from pathlib import Path

import pytest

from app.state import (
    checkpoint_from_row,
    clear_routing_choices_for_resume,
    clear_transient_provider_failures,
    decision_key,
    merge_progress,
    migrate_legacy_antigravity_quota_failure,
    review_repair_prompt_failure,
    semantic_response_only_turn_allowed,
    validate_workspace,
)


def test_merge_progress_preserves_consumed_budget():
    defaults = {"model_calls": 0, "iteration": 0, "agent_attempts": []}
    merged = merge_progress(defaults, {"model_calls": 5, "iteration": 3})
    assert merged["model_calls"] == 5
    assert merged["iteration"] == 3
    assert merged["agent_attempts"] == []


def test_checkpoint_migrates_legacy_initial_job_shape():
    checkpoint = checkpoint_from_row({
        "checkpoint": None,
        "repo_analysis": {
            "hints": {"estimated_files": 2},
            "provider_state": {"provider:openai": {"available": False}},
        },
    })
    assert checkpoint["hints"]["estimated_files"] == 2
    assert checkpoint["provider_state"]["provider:openai"]["available"] is False


def test_checkpoint_migrates_legacy_reviewer_repair_context() -> None:
    checkpoint = checkpoint_from_row({
        "checkpoint": {
            "last_failure": "PCP_REVIEW_FINDINGS: bounded repair",
            "pending_review_findings": {
                "diff_hash": "diff-review",
                "findings": [{"message": "remove out-of-scope dependency"}],
            },
        }
    })

    assert checkpoint["failure_context"] == {
        "version": 1,
        "kind": "semantic_repair",
        "source": "reviewer",
        "message": "PCP_REVIEW_FINDINGS: bounded repair",
        "diff_hash": "diff-review",
    }


def test_reroute_clears_stale_semantic_context_when_binding_changed() -> None:
    checkpoint = {
        "last_failure": "PCP_REVIEW_FINDINGS: bounded repair",
        "failure_context": {
            "version": 1,
            "kind": "semantic_repair",
            "source": "reviewer",
            "message": "PCP_REVIEW_FINDINGS: bounded repair",
            "diff_hash": "old-diff",
        },
        "pending_review_findings": {
            "diff_hash": "new-diff",
            "findings": [{"message": "new finding generation"}],
        },
        "executor_choice": {"id": "old-model"},
    }

    updated = clear_routing_choices_for_resume(checkpoint)

    assert "executor_choice" not in updated
    assert "last_failure" not in updated
    assert "failure_context" not in updated
    assert updated["pending_review_findings"]["diff_hash"] == "new-diff"


def test_reset_provider_failures_keeps_deterministic_model_failures_but_clears_quota_state():
    checkpoint = {
        "provider_state": {
            "provider:openai": {"available": False},
            "quota:model:antigravity_free": {"available": False},
            "quota:antigravity_gemini": {"available": False},
            "codex_plus": {"available": False},
        }
    }
    updated = clear_transient_provider_failures(checkpoint)
    assert "provider:openai" not in updated["provider_state"]
    assert "quota:model:antigravity_free" not in updated["provider_state"]
    assert "quota:antigravity_gemini" not in updated["provider_state"]
    assert updated["provider_state"]["codex_plus"]["available"] is False


def test_legacy_antigravity_quota_marker_is_narrowed_to_failed_model():
    checkpoint = {
        "provider_state": {
            "provider:google_antigravity": {
                "healthy": False,
                "available": False,
                "quota_pressure": 1.0,
            },
            "provider:openai": {"available": False},
        }
    }
    progress = {
        "provider_failures": [
            {
                "model": "antigravity_free",
                "provider": "google_antigravity",
                "kind": "quota_exhausted",
            }
        ]
    }

    updated = migrate_legacy_antigravity_quota_failure(checkpoint, progress)

    assert "provider:google_antigravity" not in updated["provider_state"]
    assert updated["provider_state"]["quota:model:antigravity_free"]["available"] is False
    assert updated["provider_state"]["quota:model:antigravity_free"]["quota_pressure"] == 1.0
    assert updated["provider_state"]["provider:openai"]["available"] is False
    assert "provider:google_antigravity" in checkpoint["provider_state"]


def test_legacy_antigravity_non_quota_failure_remains_provider_wide():
    checkpoint = {
        "provider_state": {
            "provider:google_antigravity": {"healthy": False, "available": False},
        }
    }
    progress = {
        "provider_failures": [
            {
                "model": "antigravity_free",
                "provider": "google_antigravity",
                "kind": "provider_unavailable",
            }
        ]
    }

    updated = migrate_legacy_antigravity_quota_failure(checkpoint, progress)

    assert updated == checkpoint


def test_decision_key_is_order_independent():
    a = decision_key({"triggers": ["production_write", "architecture_choice"]})
    b = decision_key({"triggers": ["architecture_choice", "production_write"]})
    assert a == b


def test_pending_pm_review_repair_remains_in_prompt_across_provider_interruption():
    checkpoint = {
        "pending_review_repair": {
            "message": "PCP_PM_REVIEW_REPAIR: bounded finding",
        }
    }

    combined = review_repair_prompt_failure(checkpoint, "Provider failure: unavailable")

    assert combined.startswith("PCP_PM_REVIEW_REPAIR: bounded finding")
    assert "LATEST_OPERATIONAL_CONTEXT" in combined
    assert "Provider failure: unavailable" in combined


def test_large_operational_context_truncates_without_removing_pm_repair_instruction():
    message = "PCP_PM_REVIEW_REPAIR: " + " ".join(["bounded-finding"] * 1200)
    operational = "OPERATIONAL_START:" + ("provider-noise " * 3000) + ":OPERATIONAL_END"
    checkpoint = {"pending_review_repair": {"message": message}}

    combined = review_repair_prompt_failure(checkpoint, operational)

    assert combined.startswith(message)
    assert len(combined) == 30000
    assert "LATEST_OPERATIONAL_CONTEXT" in combined
    assert "OPERATIONAL_START" not in combined
    assert combined.endswith(":OPERATIONAL_END")


def test_validate_workspace_requires_exact_job_directory(tmp_path: Path):
    root = tmp_path / "workspaces"
    workspace = root / "job12345"
    (workspace / ".git").mkdir(parents=True)
    assert validate_workspace(root, "job12345", workspace) == workspace.resolve()

    other = root / "other"
    (other / ".git").mkdir(parents=True)
    with pytest.raises(RuntimeError):
        validate_workspace(root, "job12345", other)


def test_pending_reviewer_finding_survives_pm_reassessment_failure_on_resume() -> None:
    checkpoint = {
        "work_order": {"id": "GH-63-PILOT-01"},
        "pending_review_findings": {
            "diff_hash": "dec031-diff",
            "findings": [
                {
                    "id": "DEC031-CACHE-01",
                    "severity": "high",
                    "category": "security",
                    "message": "Propagate the gate config cacheability.",
                    "evidence_refs": ["ShowPositionAccessControlHandler.php"],
                }
            ],
        },
        "last_review_report": {
            "verdict": "fail",
            "summary": "DEC-031 gate cache invalidation is incomplete.",
        },
    }

    failure = review_repair_prompt_failure(
        checkpoint,
        'invalid model selection: --effort is not supported for model "gemini-3.8-flash-medium"',
    )

    assert failure is not None
    assert failure.startswith("PCP_REVIEW_FINDINGS: ")
    assert "DEC031-CACHE-01" in failure
    assert "GH-63-PILOT-01" in failure
    assert "sha256:dec031-diff" in failure
    assert "LATEST_OPERATIONAL_CONTEXT" in failure
    assert "invalid model selection" in failure


def test_pending_pm_review_repair_still_takes_priority_over_reviewer_findings() -> None:
    checkpoint = {
        "pending_review_repair": {"message": "PCP_PM_REVIEW_REPAIR: exact delivered repair"},
        "pending_review_findings": {
            "diff_hash": "review-diff",
            "findings": [{"id": "F-1", "message": "older reviewer finding"}],
        },
    }

    failure = review_repair_prompt_failure(checkpoint, "provider temporarily unavailable")

    assert failure is not None
    assert failure.startswith("PCP_PM_REVIEW_REPAIR: exact delivered repair")
    assert "LATEST_OPERATIONAL_CONTEXT" in failure
    assert "older reviewer finding" not in failure


def test_reviewer_semantic_rebuttal_may_be_response_only() -> None:
    message = "PCP_REVIEW_FINDINGS: bounded evidence question"
    checkpoint = {
        "last_failure": message,
        "failure_context": {
            "version": 1,
            "kind": "semantic_repair",
            "source": "reviewer",
            "message": message,
            "diff_hash": "review-diff",
        },
        "pending_review_findings": {
            "diff_hash": "review-diff",
            "findings": [{"id": "F-1", "message": "Prove this with repository evidence"}],
        },
    }

    assert semantic_response_only_turn_allowed(checkpoint) is True


@pytest.mark.parametrize(
    ("action", "allowed"),
    [
        ("request_developer_response", True),
        ("request_repair", False),
    ],
)
def test_pm_semantic_turn_distinguishes_response_from_repair(
    action: str,
    allowed: bool,
) -> None:
    message = "PCP_PM_REASSESSMENT: bounded PM instruction"
    checkpoint = {
        "last_failure": message,
        "failure_context": {
            "version": 1,
            "kind": "semantic_repair",
            "source": "pm_reassessment",
            "message": message,
            "diff_hash": "pm-diff",
        },
        "last_pm_reassessment": {
            "diff_hash": "pm-diff",
            "decision": {"action": action},
        },
    }

    assert semantic_response_only_turn_allowed(checkpoint) is allowed
