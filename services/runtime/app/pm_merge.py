from __future__ import annotations

from dataclasses import asdict, dataclass
import re
from typing import Any

from .pm_reassessment import baseline_covered_protected_authorized_signals
from .scope_guard import (
    baseline_authority_changes,
    changed_path_protected_signals,
    normalize_changed_paths,
)
from .state import decision_key


_PROTECTED_ALIASES = {
    "architecture_choice": "architecture_choice",
    "architecture_change": "architecture_choice",
    "architecture_invariant_change": "architecture_choice",
    "scope_change": "scope_change",
    "product_scope_change": "scope_change",
    "non_goal_change": "scope_change",
    "major_dependency_addition": "major_dependency_addition",
    "major_service_addition": "major_dependency_addition",
    "service_dependency_change": "major_dependency_addition",
    "security_boundary_change": "security_boundary_change",
    "authentication_change": "security_boundary_change",
    "authorization_change": "security_boundary_change",
    "secret_management_change": "security_boundary_change",
    "trust_boundary_change": "security_boundary_change",
    "destructive_migration": "destructive_migration",
    "destructive_data_change": "destructive_migration",
    "production_write": "production_write",
    "production_action": "production_write",
    "production_policy_change": "production_write",
    "branch_protection_change": "high_authority_governance",
    "high_authority_governance": "high_authority_governance",
    "governance_amendment": "high_authority_governance",
    "project_baseline_authority_change": "project_baseline_authority_change",
    "material_budget_expansion": "material_budget_expansion",
}

@dataclass(frozen=True)
class MergeEligibility:
    eligible: bool
    manual_only: bool
    requires_human: bool
    blockers: tuple[str, ...]
    protected_signals: tuple[str, ...]
    approved_protected_signals: tuple[str, ...]
    expected_head: str | None
    source_commit: str | None
    pr_number: int | None
    work_order_id: str | None
    evidence: dict[str, Any]

    def model_dump(self) -> dict[str, Any]:
        return asdict(self)



@dataclass(frozen=True)
class LateReviewProof:
    """Internal, store-verified attestation; never accepted from a PM control."""

    attestation_id: int
    plan_id: str
    work_order_id: str
    job_id: str
    source_commit: str
    branch: str
    expected_head: str
    pr_number: int
    diff_hash: str
    checkpoint_id: int
    checkpoint_key: str
    writer_providers: tuple[str, ...]
    reviewer_provider: str
    reviewer_model: str
    verdict: str
    review_mode: str = "cross_provider"
    writer_model_ids: tuple[str, ...] = ()
    reviewer_tier_index: int = -1
    writer_max_tier_index: int = -1
    reviewer_review_score: float = -1
    writer_max_review_score: float = -1

    def matches(self, plan: dict[str, Any], tracked: dict[str, Any], job: dict[str, Any]) -> bool:
        result = _dict(job.get("result"))
        accepted_diff = _dict(result.get("diff"))
        return (
            self.attestation_id > 0
            and self.verdict == "pass"
            and self.checkpoint_id > 0
            and bool(self.checkpoint_key)
            and bool(self.writer_providers)
            and all(bool(provider) for provider in self.writer_providers)
            and bool(self.reviewer_provider)
            and (
                (
                    self.review_mode == "cross_provider"
                    and self.reviewer_provider not in self.writer_providers
                )
                or (
                    self.review_mode == "same_provider_higher_tier"
                    and self.reviewer_provider in self.writer_providers
                    and bool(self.writer_model_ids)
                    and self.reviewer_model not in self.writer_model_ids
                    and self.writer_max_tier_index >= 0
                    and self.reviewer_tier_index > self.writer_max_tier_index
                    and self.writer_max_review_score >= 0
                    and self.reviewer_review_score > self.writer_max_review_score
                )
            )
            and bool(self.reviewer_model)
            and self.plan_id == str(plan.get("plan_id") or "")
            and self.work_order_id == str(tracked.get("work_order_id") or "")
            and self.job_id == str(job.get("id") or "")
            and self.job_id == str(tracked.get("job_id") or "")
            and self.source_commit == str(job.get("source_commit") or "")
            and self.branch == str(job.get("branch") or "")
            and self.expected_head == str(result.get("commit") or "")
            and self.pr_number == tracked.get("pr_number")
            and self.diff_hash == str(accepted_diff.get("diff_hash") or "")
            and len(self.diff_hash) == 64
        )


@dataclass(frozen=True)
class PMChatReviewProof:
    """Owner-delegated GitHub PM-chat evidence; NEVER cross-provider independence."""

    attestation_id: int
    project_id: str
    plan_id: str
    work_order_id: str
    job_id: str
    source_commit: str
    branch: str
    expected_head: str
    pr_number: int
    diff_hash: str
    checkpoint_id: int
    checkpoint_key: str
    review_id: int
    review_author: str
    review_body_sha256: str
    control_comment_id: int
    verdict: str
    review_mode: str = "pm_chat_manual_review"

    def matches(self, plan: dict[str, Any], tracked: dict[str, Any], job: dict[str, Any]) -> bool:
        result = _dict(job.get("result"))
        diff = _dict(result.get("diff"))
        return bool(
            self.review_mode == "pm_chat_manual_review"
            and self.attestation_id > 0 and self.control_comment_id > 0 and self.review_id > 0
            and self.verdict == "pass" and bool(self.review_author)
            and re.fullmatch(r"[0-9a-f]{64}", self.review_body_sha256)
            and re.fullmatch(r"[0-9a-f]{64}", self.diff_hash)
            and self.project_id == str(plan.get("project_id") or "")
            and self.plan_id == str(plan.get("plan_id") or "")
            and self.work_order_id == str(tracked.get("work_order_id") or "")
            and self.job_id == str(tracked.get("job_id") or "")
            and self.job_id == str(job.get("id") or "")
            and self.source_commit == str(job.get("source_commit") or "")
            and self.branch == str(job.get("branch") or "")
            and self.expected_head == str(result.get("commit") or "")
            and self.pr_number == int(tracked.get("pr_number") or 0)
            and self.diff_hash == str(diff.get("diff_hash") or "")
            and self.checkpoint_id > 0 and bool(self.checkpoint_key)
        )


def _dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _pm_merge_enabled(autonomy: dict[str, Any]) -> bool:
    """Return project PM-merge authority with legacy config compatibility."""
    if "allow_pm_merge" in autonomy:
        return bool(autonomy.get("allow_pm_merge"))
    return bool(autonomy.get("allow_auto_merge_low_risk", False))


def _changed_paths(job: dict[str, Any]) -> list[str]:
    result = _dict(job.get("result"))
    diff = _dict(result.get("diff"))
    return normalize_changed_paths(diff.get("changed_files") or [])


def _baseline_authority_changes(job: dict[str, Any]) -> dict[str, str]:
    checkpoint = _dict(job.get("checkpoint"))
    return baseline_authority_changes(_changed_paths(job), checkpoint)


def _path_protected_signals(job: dict[str, Any]) -> set[str]:
    """Infer protected decision classes from actual accepted diff evidence."""

    checkpoint = _dict(job.get("checkpoint"))
    result = _dict(job.get("result"))
    diff = _dict(result.get("diff"))
    dependency_changes = diff.get("dependency_manifest_changes")
    return changed_path_protected_signals(
        _changed_paths(job),
        checkpoint,
        dependency_manifest_changes=(
            dependency_changes
            if isinstance(dependency_changes, list)
            else None
        ),
    )


def _protected_signals(job: dict[str, Any]) -> set[str]:
    signals: set[str] = set()
    task = _dict(job.get("task"))
    checkpoint = _dict(job.get("checkpoint"))
    work_order = _dict(checkpoint.get("work_order"))
    risk = _dict(work_order.get("risk"))
    for raw in list(task.get("flags") or []) + list(risk.get("flags") or []):
        normalized = str(raw).strip().lower()
        canonical = _PROTECTED_ALIASES.get(normalized)
        if canonical:
            signals.add(canonical)

    repo = _dict(job.get("repo_analysis"))
    if repo.get("authentication_change") or repo.get("authorization_change") or repo.get("security_sensitive"):
        signals.add("security_boundary_change")
    if repo.get("destructive_migration"):
        signals.add("destructive_migration")
    if repo.get("production_write"):
        signals.add("production_write")
    for raw in repo.get("likely_change_types") or []:
        canonical = _PROTECTED_ALIASES.get(str(raw).strip().lower())
        if canonical:
            signals.add(canonical)
    signals.update(_path_protected_signals(job))
    return signals


def _approved_route_triggers(job: dict[str, Any], route: dict[str, Any]) -> set[str]:
    checkpoint = _dict(job.get("checkpoint"))
    approved_keys = {str(item) for item in checkpoint.get("approved_decisions") or [] if str(item)}
    decision = _dict(_dict(route.get("strategy")).get("human_decision"))
    if not decision.get("required"):
        return set()
    key = decision_key(decision)
    if not key or key not in approved_keys:
        return set()
    return {str(item) for item in decision.get("triggers") or [] if str(item)}


def evaluate_pm_merge(
    *,
    project: dict[str, Any],
    plan: dict[str, Any],
    tracked: dict[str, Any],
    job: dict[str, Any],
    pr: dict[str, Any],
    current_ci: dict[str, Any] | None = None,
    late_review_proof: LateReviewProof | None = None,
    pm_chat_review_proof: PMChatReviewProof | None = None,
) -> MergeEligibility:
    """Evaluate PM merge authority from durable evidence plus bounded live CI.

    This function performs no GitHub mutation and does not infer approval from a
    successful implementation. Protected decisions require the exact durable
    Runtime approval key; otherwise the merge stays behind a Human Owner gate.

    A finalized delivery that persisted `ci_none` may use a fresh exact-head
    GitHub CI observation supplied by orchestration. That compatibility path is
    accepted only when the persisted CI commit and fresh CI commit both bind to
    the verified commit; the merge boundary independently re-reads CI again
    immediately before mutation.
    """
    blockers: list[str] = []
    human_blockers: list[str] = []
    autonomy = _dict(project.get("autonomy"))
    pm_merge_enabled = _pm_merge_enabled(autonomy)
    manual_only = not pm_merge_enabled

    plan_doc = _dict(plan.get("plan"))
    if plan_doc.get("decision_boundaries"):
        human_blockers.append("unresolved_plan_decision_boundaries")

    if str(job.get("status") or "") != "completed":
        blockers.append("job_not_completed")
    if bool(job.get("dry_run", False)):
        blockers.append("dry_run_not_mergeable")

    result = _dict(job.get("result"))
    checkpoint = _dict(job.get("checkpoint"))
    work_order = _dict(checkpoint.get("work_order"))
    route = _dict(result.get("route") or job.get("route"))
    strategy = _dict(route.get("strategy"))
    progress = _dict(result.get("progress") or job.get("progress"))
    delivery = _dict(result.get("delivery"))
    delivery_pr = _dict(delivery.get("pull_request"))
    verification = _dict(result.get("verification"))
    pm_evidence = _dict(result.get("pm_evidence"))
    review = _dict(result.get("review"))
    review_policy = _dict(strategy.get("review_policy"))

    expected_head = str(result.get("commit") or "").strip() or None
    source_commit = str(job.get("source_commit") or "").strip() or None
    work_order_id = str(work_order.get("id") or "").strip() or None
    try:
        pr_number = int(tracked.get("pr_number")) if tracked.get("pr_number") else None
    except (TypeError, ValueError):
        pr_number = None

    if result.get("status") != "accepted":
        blockers.append("job_result_not_accepted")
    if not expected_head:
        blockers.append("missing_verified_commit")
    if not source_commit:
        blockers.append("missing_source_commit")
    if not work_order_id or work_order_id != str(tracked.get("work_order_id") or ""):
        blockers.append("work_order_identity_mismatch")
    if str(tracked.get("job_id") or "") != str(job.get("id") or ""):
        blockers.append("job_identity_mismatch")
    if not pr_number or int(pr.get("number") or 0) != pr_number:
        blockers.append("pull_request_identity_mismatch")

    if not bool(progress.get("required_checks_passed")):
        blockers.append("required_checks_not_passed")
    if not bool(verification.get("passed")):
        blockers.append("deterministic_verification_not_passed")
    if bool(progress.get("unexpected_scope")):
        blockers.append("unexpected_scope")
    if pm_evidence.get("unresolved_risks"):
        blockers.append("pm_evidence_has_unresolved_risks")
    if pm_evidence.get("protected_decision_flags"):
        human_blockers.append("pm_evidence_has_protected_decision_flags")

    if not bool(result.get("delivery_finalized")):
        blockers.append("delivery_not_finalized")
    ci = _dict(delivery.get("ci"))
    live_ci = _dict(current_ci)
    if expected_head and ci.get("commit") and str(ci.get("commit")) != expected_head:
        blockers.append("ci_commit_mismatch")
    fresh_ci_success = bool(
        str(delivery.get("state") or "") == "ci_none"
        and str(ci.get("state") or "") == "none"
        and expected_head
        and str(ci.get("commit") or "") == expected_head
        and str(live_ci.get("state") or "") == "success"
        and str(live_ci.get("commit") or "") == expected_head
    )
    if str(delivery.get("state") or "") != "ci_success" and not fresh_ci_success:
        blockers.append("ci_not_successful")
    if str(ci.get("state") or "") != "success" and not fresh_ci_success:
        blockers.append("current_delivery_ci_evidence_not_success")
    if (
        live_ci
        and expected_head
        and live_ci.get("commit")
        and str(live_ci.get("commit")) != expected_head
    ):
        blockers.append("current_github_ci_commit_mismatch")

    if delivery_pr:
        if pr_number and int(delivery_pr.get("number") or 0) != pr_number:
            blockers.append("delivery_pr_number_mismatch")
        if expected_head and str(delivery_pr.get("head") or "") != expected_head:
            blockers.append("delivery_pr_head_mismatch")
        if str(delivery_pr.get("head_ref") or "") != str(job.get("branch") or ""):
            blockers.append("delivery_pr_branch_mismatch")

    if str(pr.get("state") or "") != "open" or bool(pr.get("merged")):
        blockers.append("pull_request_not_open_unmerged")
    if expected_head and str(pr.get("head") or "") != expected_head:
        blockers.append("pull_request_head_mismatch")
    if str(pr.get("head_ref") or "") != str(job.get("branch") or ""):
        blockers.append("pull_request_branch_mismatch")
    expected_base = str(project.get("base_branch") or "main")
    if str(pr.get("base_ref") or "") != expected_base:
        blockers.append("pull_request_base_mismatch")

    # WorkOrder risk level controls routing/profile/verification policy, but it
    # is not itself a Human Owner decision. Merge authority is determined by
    # explicit protected/unresolved decision evidence below.
    risk_level = str(_dict(work_order.get("risk")).get("level") or "standard")

    if checkpoint.get("pending_decision"):
        human_blockers.append("unresolved_job_human_decision")

    route_decision = _dict(strategy.get("human_decision"))
    approved_route = _approved_route_triggers(job, route)
    if route_decision.get("required") and not approved_route:
        human_blockers.append("route_human_decision_not_durably_approved")

    protected = _protected_signals(job)
    accepted_diff = _dict(result.get("diff"))
    baseline_covered_protected = baseline_covered_protected_authorized_signals(
        checkpoint,
        diff_hash=str(accepted_diff.get("diff_hash") or ""),
        current_signals=protected,
        baseline_revision=str(
            (checkpoint.get("project_baseline") or {}).get("revision") or ""
        ),
    )
    approved_protected = protected & (
        approved_route | baseline_covered_protected
    )
    unapproved_protected = protected - approved_protected
    if unapproved_protected:
        human_blockers.append("protected_change_without_matching_owner_approval")

    if review_policy.get("required"):
        if str(review.get("verdict") or "") != "pass":
            blockers.append("required_independent_review_not_passed")
        if review_policy.get("independent") and review_policy.get("independence_satisfied") is False:
            if not (
                (
                    isinstance(late_review_proof, LateReviewProof)
                    and late_review_proof.matches(plan, tracked, job)
                )
                or (
                    isinstance(pm_chat_review_proof, PMChatReviewProof)
                    and pm_chat_review_proof.matches(plan, tracked, job)
                )
            ):
                blockers.append("required_review_independence_not_satisfied")
    elif review_policy.get("conditional_on_strong_evidence"):
        verdict = str(review.get("verdict") or "")
        skipped = verdict == "skipped" and int(progress.get("review_skipped_strong_evidence", 0) or 0) > 0
        if verdict != "pass" and not skipped:
            blockers.append("conditional_review_has_no_pass_or_strong_evidence_skip")

    all_blockers = tuple(dict.fromkeys(blockers + human_blockers))
    requires_human = bool(human_blockers)
    eligible = not manual_only and not all_blockers
    evidence = {
        "job_id": job.get("id"),
        "work_order_id": work_order_id,
        "pr_number": pr_number,
        "expected_head": expected_head,
        "source_commit": source_commit,
        "branch": job.get("branch"),
        "base_branch": expected_base,
        "delivery_state": delivery.get("state"),
        "ci_state": ci.get("state"),
        "verification_passed": verification.get("passed"),
        "required_checks_passed": progress.get("required_checks_passed"),
        "review_verdict": review.get("verdict"),
        "review_required": bool(review_policy.get("required")),
        "late_review_attestation_id": (
            late_review_proof.attestation_id
            if isinstance(late_review_proof, LateReviewProof)
            and late_review_proof.matches(plan, tracked, job)
            else None
        ),
        "late_review_mode": (
            late_review_proof.review_mode
            if isinstance(late_review_proof, LateReviewProof)
            and late_review_proof.matches(plan, tracked, job)
            else None
        ),
        # A manual Owner-delegated review is recorded separately, never
        # reclassified as independent model-provider provenance.
        "pm_chat_review_attestation_id": (
            pm_chat_review_proof.attestation_id
            if isinstance(pm_chat_review_proof, PMChatReviewProof)
            and pm_chat_review_proof.matches(plan, tracked, job)
            else None
        ),
        "pm_chat_review_mode": (
            "pm_chat_manual_review"
            if isinstance(pm_chat_review_proof, PMChatReviewProof)
            and pm_chat_review_proof.matches(plan, tracked, job)
            else None
        ),
        "risk_level": risk_level,
        "pm_merge_enabled": pm_merge_enabled,
        "changed_files": _changed_paths(job),
        "baseline_authority_changes": _baseline_authority_changes(job),
        "baseline_covered_pm_authorized_protected_signals": sorted(
            baseline_covered_protected
        ),
    }
    return MergeEligibility(
        eligible=eligible,
        manual_only=manual_only,
        requires_human=requires_human,
        blockers=all_blockers,
        protected_signals=tuple(sorted(protected)),
        approved_protected_signals=tuple(sorted(approved_protected)),
        expected_head=expected_head,
        source_commit=source_commit,
        pr_number=pr_number,
        work_order_id=work_order_id,
        evidence=evidence,
    )


def evaluate_standalone_pm_merge(
    *,
    project: dict[str, Any],
    job: dict[str, Any],
    pr: dict[str, Any],
    pr_number: int,
    current_ci: dict[str, Any],
) -> MergeEligibility:
    """Evaluate exact-head PM merge authority for one canonical direct job."""

    blockers: list[str] = []
    human_blockers: list[str] = []
    autonomy = _dict(project.get("autonomy"))
    pm_merge_enabled = _pm_merge_enabled(autonomy)
    manual_only = not pm_merge_enabled

    result = _dict(job.get("result"))
    checkpoint = _dict(job.get("checkpoint"))
    canonical_intake = _dict(checkpoint.get("canonical_intake"))
    route = _dict(result.get("route") or job.get("route"))
    strategy = _dict(route.get("strategy"))
    progress = _dict(result.get("progress") or job.get("progress"))
    delivery = _dict(result.get("delivery"))
    delivery_pr = _dict(delivery.get("pull_request"))
    persisted_ci = _dict(delivery.get("ci"))
    verification = _dict(result.get("verification"))
    pm_evidence = _dict(result.get("pm_evidence"))
    review = _dict(result.get("review"))
    review_policy = _dict(strategy.get("review_policy"))

    expected_head = str(result.get("commit") or "").strip() or None
    source_commit = str(job.get("source_commit") or "").strip() or None
    branch = str(job.get("branch") or "").strip()
    expected_base = str(project.get("base_branch") or "main")

    if str(job.get("status") or "") != "completed":
        blockers.append("job_not_completed")
    if bool(job.get("dry_run", False)):
        blockers.append("dry_run_not_mergeable")
    if (
        canonical_intake.get("mode") != "direct"
        or canonical_intake.get("bounded_direct") is not True
    ):
        blockers.append("canonical_bounded_direct_intake_required")
    if result.get("status") != "accepted":
        blockers.append("job_result_not_accepted")
    if not expected_head:
        blockers.append("missing_verified_commit")
    if not source_commit:
        blockers.append("missing_source_commit")
    if not branch:
        blockers.append("missing_job_branch")
    if int(pr.get("number") or 0) != int(pr_number):
        blockers.append("pull_request_identity_mismatch")

    if not bool(progress.get("required_checks_passed")):
        blockers.append("required_checks_not_passed")
    if not bool(verification.get("passed")):
        blockers.append("deterministic_verification_not_passed")
    if bool(progress.get("unexpected_scope")):
        blockers.append("unexpected_scope")
    if pm_evidence.get("unresolved_risks"):
        blockers.append("pm_evidence_has_unresolved_risks")
    if pm_evidence.get("protected_decision_flags"):
        human_blockers.append("pm_evidence_has_protected_decision_flags")

    if not bool(result.get("delivery_finalized")):
        blockers.append("delivery_not_finalized")
    if str(delivery.get("state") or "") not in {"ci_success", "ci_none"}:
        blockers.append("delivery_state_not_mergeable")
    if (
        expected_head
        and persisted_ci.get("commit")
        and str(persisted_ci.get("commit")) != expected_head
    ):
        blockers.append("persisted_ci_commit_mismatch")
    if (
        str(current_ci.get("state") or "") != "success"
        or not expected_head
        or str(current_ci.get("commit") or "") != expected_head
    ):
        blockers.append("fresh_exact_head_ci_not_successful")

    if not delivery_pr:
        blockers.append("delivery_pr_missing")
    else:
        if int(delivery_pr.get("number") or 0) != int(pr_number):
            blockers.append("delivery_pr_number_mismatch")
        if expected_head and str(delivery_pr.get("head") or "") != expected_head:
            blockers.append("delivery_pr_head_mismatch")
        if str(delivery_pr.get("head_ref") or "") != branch:
            blockers.append("delivery_pr_branch_mismatch")

    if str(pr.get("state") or "") != "open" or bool(pr.get("merged")):
        blockers.append("pull_request_not_open_unmerged")
    if expected_head and str(pr.get("head") or "") != expected_head:
        blockers.append("pull_request_head_mismatch")
    if str(pr.get("head_ref") or "") != branch:
        blockers.append("pull_request_branch_mismatch")
    if str(pr.get("base_ref") or "") != expected_base:
        blockers.append("pull_request_base_mismatch")

    if checkpoint.get("pending_decision"):
        human_blockers.append("unresolved_job_human_decision")

    route_decision = _dict(strategy.get("human_decision"))
    approved_route = _approved_route_triggers(job, route)
    if route_decision.get("required") and not approved_route:
        human_blockers.append("route_human_decision_not_durably_approved")

    protected = _protected_signals(job)
    accepted_diff = _dict(result.get("diff"))
    baseline_covered_protected = baseline_covered_protected_authorized_signals(
        checkpoint,
        diff_hash=str(accepted_diff.get("diff_hash") or ""),
        current_signals=protected,
        baseline_revision=str(
            (checkpoint.get("project_baseline") or {}).get("revision") or ""
        ),
    )
    approved_protected = protected & (
        approved_route | baseline_covered_protected
    )
    unapproved_protected = protected - approved_protected
    if unapproved_protected:
        human_blockers.append("protected_change_without_matching_owner_approval")

    if review_policy.get("required"):
        if str(review.get("verdict") or "") != "pass":
            blockers.append("required_independent_review_not_passed")
        if (
            review_policy.get("independent")
            and review_policy.get("independence_satisfied") is False
        ):
            blockers.append("required_review_independence_not_satisfied")
    elif review_policy.get("conditional_on_strong_evidence"):
        verdict = str(review.get("verdict") or "")
        skipped = (
            verdict == "skipped"
            and int(progress.get("review_skipped_strong_evidence", 0) or 0) > 0
        )
        if verdict != "pass" and not skipped:
            blockers.append("conditional_review_has_no_pass_or_strong_evidence_skip")

    all_blockers = tuple(dict.fromkeys(blockers + human_blockers))
    return MergeEligibility(
        eligible=bool(pm_merge_enabled and not all_blockers),
        manual_only=manual_only,
        requires_human=bool(human_blockers),
        blockers=all_blockers,
        protected_signals=tuple(sorted(protected)),
        approved_protected_signals=tuple(sorted(approved_protected)),
        expected_head=expected_head,
        source_commit=source_commit,
        pr_number=int(pr_number),
        work_order_id=None,
        evidence={
            "job_id": job.get("id"),
            "pr_number": int(pr_number),
            "expected_head": expected_head,
            "source_commit": source_commit,
            "branch": branch,
            "base_branch": expected_base,
            "delivery_state": delivery.get("state"),
            "persisted_ci_state": persisted_ci.get("state"),
            "fresh_ci_state": current_ci.get("state"),
            "verification_passed": verification.get("passed"),
            "required_checks_passed": progress.get("required_checks_passed"),
            "review_verdict": review.get("verdict"),
            "review_required": bool(review_policy.get("required")),
            "pm_merge_enabled": pm_merge_enabled,
            "changed_files": _changed_paths(job),
            "baseline_authority_changes": _baseline_authority_changes(job),
            "baseline_covered_pm_authorized_protected_signals": sorted(
                baseline_covered_protected
            ),
            "canonical_bounded_direct": (
                canonical_intake.get("mode") == "direct"
                and canonical_intake.get("bounded_direct") is True
            ),
        },
    )


__all__ = ["MergeEligibility", "evaluate_pm_merge", "evaluate_standalone_pm_merge"]
