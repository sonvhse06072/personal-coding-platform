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

# Only the three paths in the approved F2-T01 source/acceptance contract.
_F2_CI_FIRST_PATHS = frozenset({
    "web/modules/custom/pcp_f2_fixture/src/WindowOverlapDetector.php",
    "web/modules/custom/pcp_f2_fixture/tests/src/Unit/WindowOverlapDetectorTest.php",
    "web/modules/custom/pcp_f2_fixture/tests/src/Kernel/WindowOverlapServiceTest.php",
})
_F2_CI_FIRST_DOD = frozenset({
    "targeted_tests_pass", "static_analysis_pass",
    "no_unexpected_scope", "material_change",
})


def fixture_ci_handoff_candidate(
    *,
    project_id: str,
    worker_only: bool,
    verification: dict[str, Any],
    progress: dict[str, Any],
    strategy: dict[str, Any],
    checkpoint: dict[str, Any],
    diff: dict[str, Any],
) -> bool:
    """Defer *optional* F2 reviewer spend to exact-HEAD hosted CI + PM review.

    The provisional verification does not pass Unit/Kernel tests. Only an
    in-scope, non-protected F2 fast WorkOrder can reach the existing mandatory
    delivery/CI/independent-PM gates without spending another model call.
    """
    if project_id != PROJECT_ID or worker_only is not True:
        return False
    if not all(isinstance(v, dict) for v in (
        verification, progress, strategy, checkpoint, diff,
    )):
        return False
    if (
        verification.get("verification_mode") != DEFERRED_MODE
        or verification.get("passed") is not True
        or verification.get("tests_passed") is not False
        or verification.get("local_tests_executed") is not False
        or verification.get("hosted_ci_pending") is not True
        or verification.get("test_runs") != 0
        or verification.get("phases") != []
        or progress.get("tests_passed") is not False
        or progress.get("test_runs") != 0
        or progress.get("agent_succeeded") is not True
        or progress.get("material_change_present") is not True
        or progress.get("unexpected_scope") is not False
        or progress.get("important_decision_flags") not in ([], None)
        or progress.get("provider_failures") not in ([], None)
        or diff.get("diff_truncated") is not False
        or not isinstance(diff.get("diff_hash"), str)
        or not re.fullmatch(r"[0-9a-f]{64}", diff["diff_hash"])
        or any(checkpoint.get(k) for k in (
            "pending_decision", "pending_pm_reassessment",
            "pending_review_findings", "orchestrator_launch",
        ))
    ):
        return False

    paths = diff.get("changed_files")
    if (
        not isinstance(paths, list)
        or not paths
        or len(paths) > len(_F2_CI_FIRST_PATHS)
        or not all(isinstance(p, str) for p in paths)
        or len(paths) != len(set(paths))
        or not set(paths).issubset(_F2_CI_FIRST_PATHS)
        or type(diff.get("changed_file_count")) is not int
        or diff["changed_file_count"] != len(paths)
        or type(progress.get("changed_files")) is not int
        or progress["changed_files"] != len(paths)
    ):
        return False

    policy = strategy.get("review_policy")
    decision = strategy.get("human_decision")
    requirements = (strategy.get("definition_of_done") or {}).get("required")
    permissions = strategy.get("permissions")
    budget = strategy.get("budget")
    if (
        strategy.get("profile") != "fast"
        or strategy.get("planner") is not None
        or not isinstance(policy, dict)
        or policy.get("level") != "lightweight"
        or policy.get("required") is not False
        or not isinstance(decision, dict)
        or decision.get("required") is not False
        or not isinstance(requirements, list)
        or not all(isinstance(r, str) for r in requirements)
        or not set(requirements).issubset(_F2_CI_FIRST_DOD)
        or not isinstance(permissions, dict)
        or not all(permissions.get(k) is True for k in (
            "commit", "push_ai_branch", "create_pr",
        ))
        or permissions.get("auto_merge_low_risk") is not False
        or permissions.get("production_deploy") is not False
        or not isinstance(budget, dict)
        or required_ci_for_project(project_id) is None
    ):
        return False

    for field, limit in (
        ("model_calls", "max_model_calls"),
        ("iteration", "max_iterations"),
        ("changed_files", "max_changed_files"),
    ):
        used, ceiling = progress.get(field), budget.get(limit)
        if (
            type(used) is not int or type(ceiling) is not int
            or used < 1 or ceiling < 1 or used > ceiling
        ):
            return False
    cost, hard_cost = progress.get("cost_usd"), budget.get("hard_cost_usd")
    if (
        type(cost) not in (int, float)
        or type(hard_cost) not in (int, float)
        or not 0 <= cost < hard_cost
    ):
        return False
    return True


def fixture_ci_handoff_ready(
    *,
    project_id: str,
    worker_only: bool,
    verification: dict[str, Any],
    progress: dict[str, Any],
    strategy: dict[str, Any],
    checkpoint: dict[str, Any],
    diff: dict[str, Any],
) -> bool:
    """Admit provisional completion ONLY for pending GitHub CI delivery.

    The existing DeliveryAwareStorage immediately converts completion into
    truthful pending_hosted_ci (tests_passed=False); exact CI + Human/PM review
    are still required for durable acceptance.
    """
    return (
        fixture_ci_handoff_candidate(
            project_id=project_id,
            worker_only=worker_only,
            verification=verification,
            progress=progress,
            strategy=strategy,
            checkpoint=checkpoint,
            diff=diff,
        )
        and progress.get("required_checks_passed") is True
        and isinstance(checkpoint.get("last_review_report"), dict)
        and checkpoint["last_review_report"].get("verdict") == "deferred"
        and checkpoint.get("acceptance_phase") in (None, "")
    )


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
