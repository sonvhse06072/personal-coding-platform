from __future__ import annotations

import re
from copy import deepcopy
from typing import Any

from .evidence_packs import pm_evidence_pack


_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
_LEGACY_LOST_ACCEPTANCE_REASON = "material_change_missing_without_model_fallback"
LEGACY_RECOVERY_BLOCK_REASON = "legacy_delivery_acceptance_evidence_incomplete"


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _sha(value: Any) -> str:
    candidate = str(value or "").lower()
    return candidate if _SHA_RE.fullmatch(candidate) else ""


def _positive_int(value: Any) -> bool:
    if isinstance(value, bool):
        return False
    try:
        return int(value) > 0
    except (TypeError, ValueError):
        return False


def _zero_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value == 0


def _int_or_zero(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def legacy_delivery_recovery_candidate(row: dict[str, Any]) -> bool:
    """Recognize only the legacy result-loss shape created after delivery began.

    A clean tree, an ahead branch, a commit, or a PR alone are deliberately not
    evidence here. `checkpoint.delivery` is Runtime-owned provenance written
    only after a locally accepted result entered the delivery engine.
    """
    result = _mapping(row.get("result"))
    checkpoint = _mapping(row.get("checkpoint"))
    delivery = _mapping(checkpoint.get("delivery"))
    return (
        str(result.get("reason") or "") == _LEGACY_LOST_ACCEPTANCE_REASON
        and bool(delivery.get("enabled"))
        and str(delivery.get("state") or "") == "ci_failure"
    )


def recover_legacy_accepted_result(row: dict[str, Any]) -> dict[str, Any]:
    """Reconstruct a bounded accepted result from authoritative durable state.

    Returns an assessment with `candidate`, `accepted_result`, and
    `missing_evidence`. A candidate with missing evidence must fail closed and
    must never fall through to another implementation turn.
    """
    if not legacy_delivery_recovery_candidate(row):
        return {"candidate": False, "accepted_result": None, "missing_evidence": []}

    missing: list[str] = []
    checkpoint = _mapping(row.get("checkpoint"))
    delivery = _mapping(checkpoint.get("delivery"))
    publish = _mapping(delivery.get("publish"))
    pull_request = _mapping(delivery.get("pull_request"))
    ci = _mapping(delivery.get("ci"))
    route = _mapping(row.get("route"))
    strategy = _mapping(route.get("strategy"))
    permissions = _mapping(strategy.get("permissions"))
    review_policy = _mapping(strategy.get("review_policy"))
    progress = _mapping(row.get("progress"))
    review = _mapping(checkpoint.get("last_review_report"))
    review_history = [
        _mapping(item) for item in progress.get("review_history") or []
        if isinstance(item, dict)
    ]
    last_review = review_history[-1] if review_history else {}
    work_order = _mapping(checkpoint.get("work_order"))

    job_id = str(row.get("id") or "")
    branch = str(row.get("branch") or "")
    source_commit = _sha(row.get("source_commit"))
    commit = _sha(delivery.get("commit"))
    repository = str(publish.get("repository") or "")

    def require(condition: bool, name: str) -> None:
        if not condition:
            missing.append(name)

    require(bool(job_id), "job_identity")
    require(bool(branch), "branch_identity")
    require(bool(source_commit), "source_commit_identity")
    require(bool(commit), "verified_commit_identity")
    require(bool(permissions.get("commit")), "commit_permission")
    require(bool(permissions.get("push_ai_branch")), "push_permission")
    require(bool(permissions.get("create_pr")), "pull_request_permission")

    require(str(delivery.get("branch") or "") == branch, "delivery_branch_match")
    require(publish.get("published") is True, "published_transition")
    require(str(publish.get("branch") or "") == branch, "published_branch_match")
    require(_sha(publish.get("commit")) == commit, "published_commit_match")
    require(_sha(publish.get("source_commit")) == source_commit, "published_source_match")
    require(bool(repository), "published_repository_identity")

    require(_positive_int(pull_request.get("number")), "pull_request_identity")
    require(str(pull_request.get("job_id") or "") == job_id, "pull_request_job_match")
    require(str(pull_request.get("state") or "") == "open", "pull_request_open")
    require(_sha(pull_request.get("head")) == commit, "pull_request_head_match")
    require(str(pull_request.get("head_ref") or "") == branch, "pull_request_branch_match")
    require(bool(pull_request.get("base_ref")), "pull_request_base_identity")
    require(str(pull_request.get("repository") or "") == repository, "pull_request_repository_match")

    require(str(ci.get("state") or "") == "failure", "ci_failure_transition")
    require(_sha(ci.get("commit")) == commit, "ci_commit_match")

    require(progress.get("tests_passed") is True, "deterministic_tests_passed")
    require(progress.get("required_checks_passed") is True, "required_checks_passed")
    require(progress.get("unexpected_scope") is False, "scope_check_passed")
    require(_positive_int(progress.get("test_runs")), "deterministic_test_evidence")

    require(review_policy.get("required") is True, "independent_review_required")
    require(review_policy.get("independent") is True, "independent_review_policy")
    require(review_policy.get("independence_satisfied") is True, "review_independence_satisfied")
    require(bool(strategy.get("evaluator")), "independent_reviewer_route")
    require(review.get("verdict") == "pass", "review_verdict_passed")
    require(review.get("protocol_valid") is True, "review_protocol_valid")
    require(_zero_int(review.get("finding_count")), "review_findings_resolved")
    require(last_review.get("verdict") == "pass", "review_history_verdict_passed")
    require(last_review.get("protocol_valid") is True, "review_history_protocol_valid")
    require(bool(last_review.get("model")), "review_model_identity")
    require(bool(last_review.get("provider")), "review_provider_identity")
    require(not checkpoint.get("pending_review_findings"), "no_pending_review_findings")
    require(bool(work_order.get("id")), "work_order_identity")

    if missing:
        return {
            "candidate": True,
            "accepted_result": None,
            "missing_evidence": missing,
            "commit": commit or None,
            "branch": branch or None,
        }

    verification = {
        "passed": True,
        "tests_passed": True,
        "verification_mode": "legacy_durable_recovery",
        "phases": [],
        "test_runs": _int_or_zero(progress.get("test_runs")),
        "tool_calls": _int_or_zero(progress.get("tool_calls")),
        "recovered_from": "runtime_progress_and_delivery_checkpoint",
    }
    pm_evidence = pm_evidence_pack(
        work_order_ref=str(work_order["id"]),
        outcome="accepted",
        verification_summary=verification,
        review_summary=review,
        unresolved_risks=[],
        protected_decision_flags=list(progress.get("important_decision_flags") or []),
    )
    accepted_result = {
        "status": "accepted",
        "branch": branch,
        "commit": commit,
        "verification": verification,
        "evaluator": None,
        "review": review,
        "pm_evidence": pm_evidence,
        "route": deepcopy(route),
        "route_history": deepcopy(checkpoint.get("route_history") or []),
        "progress": deepcopy(progress),
        "delivery": deepcopy(delivery),
        "delivery_finalized": False,
        "legacy_delivery_recovery": {
            "authorized": True,
            "job_id": job_id,
            "commit": commit,
            "branch": branch,
            "prior_block": deepcopy(_mapping(row.get("result"))),
            "evidence": [
                "runtime_delivery_checkpoint",
                "exact_publish_identity",
                "exact_pull_request_identity",
                "deterministic_verification_progress",
                "independent_review_summary_and_history",
                "route_permissions",
            ],
        },
    }
    return {"candidate": True, "accepted_result": accepted_result, "missing_evidence": []}


__all__ = [
    "LEGACY_RECOVERY_BLOCK_REASON",
    "legacy_delivery_recovery_candidate",
    "recover_legacy_accepted_result",
]
