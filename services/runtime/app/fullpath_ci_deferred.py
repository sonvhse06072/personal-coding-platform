"""Truthful CI-first state for the future full-PCP synthetic fixture.

Before GitHub Actions validation, deterministic tests have NOT been run locally.
The normal engine may provisionally advance a reviewer-passed diff for PR/CI,
but the durable job must never report accepted/completed or locally tested.

This does not activate the parked full-path candidate, dispatch Codex, run
DDEV, communicate with GitHub or grant a PM-review approval action.
"""
from __future__ import annotations

from copy import deepcopy
import re
from typing import Any

from .fullpath_fixture_safety import PROJECT_ID
from .required_ci import required_ci_for_project, required_github_actions_pass


DEFERRED_MODE = "hosted_ci_deferred"
WAITING_PM = "awaiting_pm_exact_head_review"
_SHA = re.compile(r"^[a-f0-9]{40}$")


def fixture_deferred_verification(
    project_id: str, *, ddev_enabled: bool
) -> dict[str, Any] | None:
    """No local tests executed. 'passed' is an internal pre-delivery routing hint.

    Persistent results are downgraded to CI-pending by stage_delivery_update.
    Only the G0 full-path fixture opts in; all legacy projects return None.
    """
    if project_id != PROJECT_ID:
        return None
    if ddev_enabled:
        return {
            "passed": False, "tests_passed": False, "tool_calls": 0,
            "test_runs": 0, "phases": [],
            "verification_mode": DEFERRED_MODE,
            "local_tests_executed": False,
            "hosted_ci_pending": True,
            "failure_text": "fullpath_local_ddev_not_authorized",
        }
    return {
        "passed": True, "tests_passed": False, "tool_calls": 0,
        "test_runs": 0, "phases": [],
        "verification_mode": DEFERRED_MODE,
        "local_tests_executed": False,
        "hosted_ci_pending": True,
        "failure_text": "",
    }


def stage_delivery_update(
    row: dict[str, Any], updates: dict[str, Any]
) -> dict[str, Any]:
    """Convert a provisional normal-Engine completion to durable CI pending.

    Called from the existing DeliveryAwareStorage; never authorizes a terminal
    transition. Missing commit, reviewer/verification evidence, or permission
    fails closed as blocked, preserving attempted acceptance as audit evidence.
    """
    fields = dict(updates)
    if row.get("project_id") != PROJECT_ID or fields.get("status") != "completed":
        return fields

    result = deepcopy(fields.get("result") or {})
    if result.get("dry_run"):
        # Dry-run is not a counted accepted engineering result.
        return fields

    original = deepcopy(result)
    verification = dict(result.get("verification") or {})
    route = result.get("route") or {}
    strategy = route.get("strategy") or {}
    permissions = strategy.get("permissions") or {}
    commit = str(result.get("commit") or "")
    branch = str(result.get("branch") or "")
    valid = (
        result.get("status") == "accepted"
        and result.get("delivery_finalized") is not True
        and verification.get("verification_mode") == DEFERRED_MODE
        and verification.get("passed") is True
        and verification.get("tests_passed") is False
        and verification.get("test_runs") == 0
        and verification.get("local_tests_executed") is False
        and verification.get("hosted_ci_pending") is True
        and bool(_SHA.fullmatch(commit))
        and branch.startswith("ai/")
        and all(permissions.get(key) is True for key in (
            "commit", "push_ai_branch", "create_pr"
        ))
        and required_ci_for_project(row["project_id"]) is not None
    )
    if not valid:
        fields.update({
            "status": "blocked",
            "error": "fullpath_ci_first_admission_failed",
            "result": {
                "reason": "fullpath_ci_first_admission_failed",
                "accepted_result": original,
            },
        })
        return fields

    verification["passed"] = False
    verification["tests_passed"] = False
    verification["hosted_ci_pending"] = True
    verification["local_tests_executed"] = False
    result["verification"] = verification
    result["acceptance_phase"] = "pending_hosted_ci"
    result["delivery_finalized"] = False
    progress = deepcopy(fields.get("progress") or {})
    progress["tests_passed"] = False
    progress["required_checks_passed"] = False
    progress["hosted_ci_pending"] = True
    checkpoint = deepcopy(fields.get("checkpoint") or {})
    checkpoint["acceptance_phase"] = "pending_hosted_ci"
    fields.update({
        "status": "delivering",
        "result": result,
        "progress": progress,
        "checkpoint": checkpoint,
    })
    return fields


def ci_passed_awaiting_review(
    *,
    row: dict[str, Any],
    result: dict[str, Any],
    progress: dict[str, Any],
    checkpoint: dict[str, Any],
    delivery: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]] | None:
    """Recognize exact hosted CI but STOP short of completed/PM approval."""
    requirement = required_ci_for_project(str(row.get("project_id") or ""))
    if requirement is None:
        return None
    commit = str(result.get("commit") or "")
    stage = str(result.get("acceptance_phase") or "")
    verification = dict(result.get("verification") or {})
    pr = delivery.get("pull_request") or {}
    if (
        not _SHA.fullmatch(commit)
        or stage != "pending_hosted_ci"
        or verification.get("verification_mode") != DEFERRED_MODE
        or verification.get("local_tests_executed") is not False
        or verification.get("hosted_ci_pending") is not True
        or verification.get("tests_passed") is not False
        or delivery.get("state") != "ci_success"
        or not required_github_actions_pass(
            delivery.get("ci") or {},
            repository=requirement[0], commit=commit,
            workflow_name=requirement[1],
        )
        or type(pr.get("number")) is not int or pr["number"] < 1
        or pr.get("head") != commit
        or pr.get("repository") != requirement[0]
        or pr.get("merged") is True
    ):
        return None

    final_result = deepcopy(result)
    final_progress = deepcopy(progress)
    final_checkpoint = deepcopy(checkpoint)
    verification.update({
        "passed": True,
        "tests_passed": True,
        "hosted_ci_pending": False,
        "hosted_ci_passed": True,
        "local_tests_executed": False,
        "verification_mode": "hosted_ci",
        "hosted_ci_commit": commit,
    })
    final_result["verification"] = verification
    final_result["acceptance_phase"] = WAITING_PM
    final_result["delivery_finalized"] = False
    final_progress["tests_passed"] = True
    final_progress["required_checks_passed"] = True
    final_progress["hosted_ci_pending"] = False
    final_checkpoint["acceptance_phase"] = WAITING_PM
    return final_result, final_progress, final_checkpoint
