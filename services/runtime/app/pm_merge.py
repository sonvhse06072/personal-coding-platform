from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import PurePosixPath
from typing import Any

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

_HIGH_AUTHORITY_PATHS = {
    "agents.md",
    "docs/project/constitution.md",
    "docs/project/architecture.md",
    "docs/project/operating-model.md",
    "docs/project/efficiency-model.md",
    "config/projects.yml",
    "config/routing-policy.yml",
    "config/models.yml",
}
_SCOPE_PATHS = {
    "docs/project/roadmap.md",
    "docs/project/requirements.md",
    "docs/project/project-plan.md",
}
_DEPENDENCY_MANIFESTS = {
    "composer.json",
    "composer.lock",
    "package.json",
    "package-lock.json",
    "pnpm-lock.yaml",
    "yarn.lock",
    "pyproject.toml",
    "poetry.lock",
    "pipfile",
    "pipfile.lock",
    "go.mod",
    "go.sum",
    "cargo.toml",
    "cargo.lock",
    "gemfile",
    "gemfile.lock",
    "dockerfile",
    "docker-compose.yml",
    "docker-compose.yaml",
    "compose.yml",
    "compose.yaml",
}
_SECURITY_PATH_TERMS = {
    "auth",
    "authentication",
    "authorization",
    "permission",
    "permissions",
    "security",
    "secret",
    "secrets",
    "credential",
    "credentials",
    "access_control",
}
_PRODUCTION_PATH_TERMS = {
    "deploy",
    "deployment",
    "production",
    "prod",
    "terraform",
    "ansible",
    "helm",
    "kubernetes",
    "k8s",
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


def _dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _changed_paths(job: dict[str, Any]) -> list[str]:
    result = _dict(job.get("result"))
    diff = _dict(result.get("diff"))
    paths: list[str] = []
    for raw in diff.get("changed_files") or []:
        value = str(raw).strip().replace("\\", "/")
        if not value:
            continue
        candidates = value.split(" -> ") if " -> " in value else [value]
        for candidate in candidates:
            normalized = candidate.strip()
            while normalized.startswith("./"):
                normalized = normalized[2:]
            normalized = normalized.lower()
            if normalized and normalized not in paths:
                paths.append(normalized)
    return paths


def _baseline_authority_changes(job: dict[str, Any]) -> dict[str, str]:
    """Return authority classes for changed paths from the pinned baseline snapshot."""

    checkpoint = _dict(job.get("checkpoint"))
    baseline = _dict(checkpoint.get("project_baseline"))
    rules = baseline.get("authority") or []
    authority_by_path: dict[str, str] = {}
    for raw in rules:
        rule = _dict(raw)
        path = str(rule.get("path") or "").strip().replace("\\", "/").lower()
        authority = str(rule.get("authority") or "").strip()
        if path and authority:
            authority_by_path[path] = authority

    changed: dict[str, str] = {}
    for path in _changed_paths(job):
        authority = authority_by_path.get(path)
        if authority:
            changed[path] = authority
    return changed


def _path_protected_signals(job: dict[str, Any]) -> set[str]:
    """Infer protected decision classes from the actual accepted diff paths.

    WorkOrder/task risk metadata is predictive. The accepted diff is executable
    evidence, so sensitive path families get a second deterministic fail-closed
    check before merge. These rules intentionally prefer a manual owner merge over
    silently merging an unclassified governance/security/dependency change.
    """
    signals: set[str] = set()
    baseline_authority = _baseline_authority_changes(job)
    if "human_owner_protected" in set(baseline_authority.values()):
        signals.add("project_baseline_authority_change")

    for path in _changed_paths(job):
        pure = PurePosixPath(path)
        name = pure.name.lower()
        parts = {part.lower() for part in pure.parts}
        stem_parts = set(name.replace("-", "_").replace(".", "_").split("_"))

        if path in _HIGH_AUTHORITY_PATHS or path.startswith(".github/workflows/"):
            signals.add("high_authority_governance")
        if path in _SCOPE_PATHS:
            signals.add("scope_change")

        if (
            name in _DEPENDENCY_MANIFESTS
            or (name.startswith("requirements") and name.endswith(".txt"))
            or path.startswith(("helm/", "charts/", "k8s/", "kubernetes/"))
        ):
            signals.add("major_dependency_addition")

        if _SECURITY_PATH_TERMS & (parts | stem_parts):
            signals.add("security_boundary_change")

        if "migration" in parts or "migrations" in parts or "schema" in stem_parts:
            signals.add("destructive_migration")

        if _PRODUCTION_PATH_TERMS & (parts | stem_parts):
            signals.add("production_write")

    return signals


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
) -> MergeEligibility:
    """Evaluate PM merge authority from durable evidence only.

    This function performs no GitHub mutation and does not infer approval from a
    successful implementation. Protected decisions require the exact durable
    Runtime approval key; otherwise the merge stays behind a Human Owner gate.
    """
    blockers: list[str] = []
    human_blockers: list[str] = []
    autonomy = _dict(project.get("autonomy"))
    manual_only = not bool(autonomy.get("allow_auto_merge_low_risk", False))

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
    if str(delivery.get("state") or "") != "ci_success":
        blockers.append("ci_not_successful")
    ci = _dict(delivery.get("ci"))
    if str(ci.get("state") or "") != "success":
        blockers.append("current_delivery_ci_evidence_not_success")
    if expected_head and ci.get("commit") and str(ci.get("commit")) != expected_head:
        blockers.append("ci_commit_mismatch")

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

    risk_level = str(_dict(work_order.get("risk")).get("level") or "standard")
    if risk_level not in {"routine", "standard"}:
        human_blockers.append("work_order_risk_not_low")

    if checkpoint.get("pending_decision"):
        human_blockers.append("unresolved_job_human_decision")

    route_decision = _dict(strategy.get("human_decision"))
    approved_route = _approved_route_triggers(job, route)
    if route_decision.get("required") and not approved_route:
        human_blockers.append("route_human_decision_not_durably_approved")

    protected = _protected_signals(job)
    approved_protected = protected & approved_route
    unapproved_protected = protected - approved_protected
    if unapproved_protected:
        human_blockers.append("protected_change_without_matching_owner_approval")

    if review_policy.get("required"):
        if str(review.get("verdict") or "") != "pass":
            blockers.append("required_independent_review_not_passed")
        if review_policy.get("independent") and review_policy.get("independence_satisfied") is False:
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
        "risk_level": risk_level,
        "changed_files": _changed_paths(job),
        "baseline_authority_changes": _baseline_authority_changes(job),
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


__all__ = ["MergeEligibility", "evaluate_pm_merge"]
