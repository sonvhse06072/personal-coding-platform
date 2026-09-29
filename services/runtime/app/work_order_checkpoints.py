"""Bounded lifecycle evidence and identities; no execution or mutation authority."""
from __future__ import annotations

import hashlib
import json
import re
import uuid
from typing import Any


_SAFE_IDENTITY = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]*$")
_SAFE_REF = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]*$")
_SAFE_COMMIT = re.compile(r"^[0-9a-fA-F]{7,64}$")
_OUTCOMES = {
    "pass", "fail", "accepted", "repair", "blocked",
    "needs_human_decision", "not_required",
}
_PM_ACTIONS = {"approve_continue", "repair", "human_decision", "request_explanation"}
_PUBLIC_BLOCK_REASONS = {
    "approved_merge_has_no_confirmed_result",
    "blocked",
    "cancelled",
    "collaboration_cancelled",
    "collaboration_failed",
    "collaboration_pm_handoff",
    "delivery_missing_verified_commit",
    "evaluator_protocol_failure_without_fallback",
    "evaluator_provider_failure_without_fallback",
    "execution_budget_exhausted",
    "failed",
    "github_ci_infrastructure_failure",
    "github_ci_timeout",
    "github_delivery_failed",
    "github_delivery_budget_exhausted",
    "human_decision_required",
    "human_decision_rejected",
    "interrupted",
    "malformed_reviewer_output",
    "material_change_missing_without_model_fallback",
    "merge_not_confirmed",
    "missing_pull_request_number",
    "no_effect",
    "operator_blocked",
    "orchestrated_job_missing",
    "planner_budget_exhausted",
    "planner_failed",
    "planner_provider_failure_without_fallback",
    "pm_reassessment_blocked",
    "pm_reassessment_failed",
    "pm_reassessment_invalid_protected_approval",
    "pm_reassessment_unresolved_after_human_approval",
    "preflight_budget_exhausted",
    "preflight_failed",
    "provider_failure_without_fallback",
    "pull_request_closed_without_merge",
    "reassessment_stopped",
    "repair_churn_circuit_breaker",
    "review_repair_missing_new_commit",
    "unsafe_bare_completion",
    "work_order_definition_missing",
    "work_order_policy_rejected",
}
_REROUTE_REASONS = {
    "evaluator_protocol_failure_without_fallback",
    "evaluator_provider_failure_without_fallback",
    "malformed_reviewer_output",
    "material_change_missing_without_model_fallback",
    "planner_failed",
    "planner_provider_failure_without_fallback",
    "pm_reassessment_failed",
    "provider_failure_without_fallback",
}
_HUMAN_DECISION_REASONS = {
    "approved_merge_has_no_confirmed_result",
    "delivery_missing_verified_commit",
    "github_delivery_budget_exhausted",
    "human_decision_required",
    "human_decision_rejected",
    "merge_not_confirmed",
    "missing_pull_request_number",
    "pm_reassessment_invalid_protected_approval",
    "pm_reassessment_unresolved_after_human_approval",
    "repair_churn_circuit_breaker",
}
_BUDGET_DECISION_REASONS = {
    "planner_budget_exhausted",
    "preflight_budget_exhausted",
    "execution_budget_exhausted",
}
_DELIVERY_RECOVERY_REASONS = {
    "github_ci_infrastructure_failure",
    "github_ci_timeout",
    "github_delivery_failed",
}
_REPLAN_REASONS = {
    "orchestrated_job_missing",
    "pull_request_closed_without_merge",
    "work_order_definition_missing",
    "work_order_policy_rejected",
}


def launch_identity(plan_id: str, work_order_id: str) -> dict[str, str]:
    if any(not isinstance(value, str) or not value or value != value.strip() for value in (plan_id, work_order_id)):
        raise RuntimeError("Invalid orchestrator launch identity")
    return {"plan_id": plan_id, "work_order_id": work_order_id,
            "job_id": uuid.uuid5(uuid.NAMESPACE_URL, f"coding-platform:{plan_id}:{work_order_id}").hex}


def orchestrator_launch(job: dict[str, Any]) -> dict[str, str] | None:
    """Internal reservation, never accepted from public job creation payloads."""
    checkpoint = job.get("checkpoint") or {}
    if "orchestrator_launch" not in checkpoint:
        return None
    marker = checkpoint["orchestrator_launch"]
    if not isinstance(marker, dict):
        raise RuntimeError("Invalid orchestrator launch reservation")
    identity = launch_identity(marker.get("plan_id"), marker.get("work_order_id"))
    if (any(marker.get(key) != value for key, value in identity.items())
            or job.get("id") != identity["job_id"]
            or marker.get("state") not in {"held", "ready", "launched"}
            or (checkpoint.get("work_order") or {}).get("id") != identity["work_order_id"]):
        raise RuntimeError("Mismatched orchestrator launch reservation")
    return marker


def ready_work_order_ids(plan: dict[str, Any], states: dict[str, str]) -> list[str]:
    definitions = {item["id"]: item for item in plan.get("work_orders") or []}
    return [
        work_order_id for work_order_id, state in states.items()
        if state == "pending" and work_order_id in definitions
        and all(states.get(dep) == "completed" for dep in definitions[work_order_id].get("dependencies") or [])
    ]


def _object(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _text(value: Any, limit: int = 200) -> str | None:
    if not isinstance(value, str) or not value:
        return None
    return value.replace("\x00", "").encode("utf-8", errors="replace")[:limit].decode("utf-8", errors="ignore")


def _safe_text(value: Any, pattern: re.Pattern[str], limit: int) -> str | None:
    value = _text(value, limit)
    return value if value and pattern.fullmatch(value) else None


def _verification_summary(value: Any) -> dict[str, Any] | None:
    verification = _object(value)
    summary: dict[str, Any] = {}
    if type(verification.get("passed")) is bool:
        summary["passed"] = verification["passed"]
    phases = verification.get("phases")
    if isinstance(phases, list):
        summary["phases"] = [
            {"phase": phase, "passed": item["passed"]}
            for item in phases[:16] if isinstance(item, dict)
            and (phase := _safe_text(item.get("phase"), _SAFE_IDENTITY, 80))
            and type(item.get("passed")) is bool
        ]
    return summary or None


def verification_checkpoint_summary(value: Any) -> dict[str, Any] | None:
    """Return the same bounded deterministic evidence used by checkpoints."""
    return _verification_summary(value)


def checkpoint_evidence(
    tracked: dict[str, Any], job: dict[str, Any] | None = None,
    *, pr: dict[str, Any] | None = None, reason: str | None = None,
) -> dict[str, Any]:
    """Copy only known scalar identities, outcomes, phase booleans and counters."""
    job = job or {}
    result = _object(job.get("result"))
    checkpoint = _object(job.get("checkpoint"))
    delivery = _object(result.get("delivery"))
    delivered_pr = _object(delivery.get("pull_request"))
    pr = pr or delivered_pr
    decision = _object(checkpoint.get("pending_decision"))
    repair = _object(checkpoint.get("pending_review_repair")) or _object(checkpoint.get("active_review_repair"))
    evidence: dict[str, Any] = {}
    for key, value, limit in (
        ("source_commit", job.get("source_commit"), 200),
        ("produced_commit", result.get("commit"), 200),
        ("branch", job.get("branch") or result.get("branch"), 300),
        ("pr_url", pr.get("url") or tracked.get("pr_url"), 1000),
        ("pr_head", pr.get("head") or delivered_pr.get("head"), 200),
        ("merge_commit", pr.get("merge_commit_sha"), 200),
        ("merged_at", pr.get("merged_at"), 100),
        ("decision_source", decision.get("source"), 100),
        ("decision_key", decision.get("key"), 500),
        ("review_repair_request_id", repair.get("request_id"), 200),
        ("expected_commit", repair.get("expected_commit"), 200),
        ("reason", reason, 1000),
    ):
        text = _text(value, limit)
        if text is not None:
            evidence[key] = text
    if reason and _text(reason, 1000) != reason:
        evidence["reason_sha256"] = hashlib.sha256(reason.encode("utf-8")).hexdigest()
    number = pr.get("number") or repair.get("pr_number") or tracked.get("pr_number")
    if type(number) is int and number > 0:
        evidence["pr_number"] = number
    progress = _object(job.get("progress"))
    for key in ("repair_iterations", "verification_attempts", "model_calls", "test_runs", "changed_files"):
        value = progress.get(key)
        if type(value) is int and 0 <= value <= 2**63 - 1:
            evidence[key] = value
    epoch = _object(checkpoint.get("review_repair_churn_epoch"))
    verification = (
        _object(result.get("verification"))
        or _object(checkpoint.get("last_verification_summary"))
        or _object(epoch.get("latest_verification_summary"))
    )
    summary = _verification_summary(verification)
    if summary is not None:
        evidence["verification"] = summary
    review = _object(result.get("review")) or _object(checkpoint.get("last_review_report"))
    pm = _object(result.get("pm_evidence"))
    for key, value in (("review_verdict", review.get("verdict")), ("pm_outcome", pm.get("outcome"))):
        if isinstance(value, str) and value in _OUTCOMES:
            evidence[key] = value
    pm_decision = _object(_object(checkpoint.get("last_pm_reassessment")).get("decision"))
    action = pm_decision.get("action")
    if isinstance(action, str) and action in _PM_ACTIONS:
        evidence["pm_action"] = action
    return evidence


def blocked_evidence_checkpoint_rows(
    conn: Any, plan_id: str, work_orders: list[dict[str, Any]],
) -> dict[str, Any]:
    """Read only the bounded checkpoint rows needed for a blocked-plan pack."""
    blocked = next((row for row in work_orders if row.get("state") == "blocked"), None)
    if blocked is None:
        return {
            "completed_checkpoints": [],
            "current_checkpoint_history": [],
            "blocked_checkpoint": None,
            "last_good_checkpoint": None,
        }
    completed = list(conn.execute(
        """SELECT c.* FROM cp_plan_work_order_checkpoints c
        JOIN cp_plan_work_orders w
          ON w.plan_id=c.plan_id AND w.work_order_id=c.work_order_id
        WHERE c.plan_id=%s AND w.lifecycle='active' AND w.state='completed'
          AND c.kind IN ('completed','merged')
          AND c.job_id IS NOT DISTINCT FROM w.job_id
        ORDER BY w.sequence_no,w.work_order_id,c.id""",
        (plan_id,),
    ).fetchall())
    current_history = list(conn.execute(
        """SELECT c.* FROM cp_plan_work_order_checkpoints c
        WHERE c.plan_id=%s AND c.work_order_id=%s
          AND c.job_id IS NOT DISTINCT FROM %s
        ORDER BY c.id DESC LIMIT 32""",
        (plan_id, blocked["work_order_id"], blocked.get("job_id")),
    ).fetchall())
    blocked_checkpoint = next(
        (checkpoint for checkpoint in current_history if checkpoint.get("kind") == "blocked"),
        None,
    )
    last_good = None
    if blocked_checkpoint is not None:
        last_good = conn.execute(
            """SELECT c.* FROM cp_plan_work_order_checkpoints c
            JOIN cp_plan_work_orders w
              ON w.plan_id=c.plan_id AND w.work_order_id=c.work_order_id
            WHERE c.plan_id=%s AND c.id < %s AND w.lifecycle='active'
              AND c.kind IN ('completed','merged')
              AND c.job_id IS NOT DISTINCT FROM w.job_id
            ORDER BY c.id DESC LIMIT 1""",
            (plan_id, blocked_checkpoint["id"]),
        ).fetchone()
    return {
        "completed_checkpoints": completed,
        "current_checkpoint_history": current_history,
        "blocked_checkpoint": blocked_checkpoint,
        "last_good_checkpoint": last_good,
    }


def checkpoint_read_model(checkpoint: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(checkpoint, dict):
        return None
    result: dict[str, Any] = {}
    if type(checkpoint.get("id")) is int and checkpoint["id"] > 0:
        result["id"] = checkpoint["id"]
    for key, limit in (
        ("checkpoint_key", 500), ("work_order_id", 200), ("kind", 200),
        ("state", 200), ("job_id", 200),
    ):
        value = _safe_text(checkpoint.get(key), _SAFE_IDENTITY, limit)
        if value is not None:
            result[key] = value
    created_at = checkpoint.get("created_at")
    if hasattr(created_at, "isoformat"):
        result["created_at"] = created_at.isoformat()
    elif (value := _text(created_at, 100)) is not None:
        result["created_at"] = value

    evidence = _object(checkpoint.get("evidence"))
    public: dict[str, Any] = {}
    for key in ("source_commit", "produced_commit", "pr_head", "merge_commit"):
        value = _safe_text(evidence.get(key), _SAFE_COMMIT, 64)
        if value is not None:
            public[key] = value
    branch = _safe_text(evidence.get("branch"), _SAFE_REF, 300)
    if branch is not None:
        public["branch"] = branch
    if type(evidence.get("pr_number")) is int and evidence["pr_number"] > 0:
        public["pr_number"] = evidence["pr_number"]
    merged_at = _text(evidence.get("merged_at"), 100)
    if merged_at is not None and re.fullmatch(r"[0-9TZ:+. -]{10,100}", merged_at):
        public["merged_at"] = merged_at
    verification = _verification_summary(evidence.get("verification"))
    if verification is not None:
        public["verification"] = verification
    for key in ("review_verdict", "pm_outcome"):
        value = evidence.get(key)
        if isinstance(value, str) and value in _OUTCOMES:
            public[key] = value
    action = evidence.get("pm_action")
    if isinstance(action, str) and action in _PM_ACTIONS:
        public["pm_action"] = action
    for key in ("repair_iterations", "verification_attempts", "model_calls", "test_runs", "changed_files"):
        value = evidence.get(key)
        if type(value) is int and 0 <= value <= 2**63 - 1:
            public[key] = value
    result["evidence"] = public
    return result


def _blocked_reason(evidence: dict[str, Any]) -> tuple[str, str | None]:
    reason = evidence.get("reason")
    if isinstance(reason, str) and reason in _PUBLIC_BLOCK_REASONS:
        reason_hash = str(evidence.get("reason_sha256") or "")
        return reason, reason_hash if _SAFE_COMMIT.fullmatch(reason_hash) else None
    if isinstance(reason, str) and reason:
        return "unclassified_block", hashlib.sha256(reason.encode("utf-8")).hexdigest()
    return "blocked_checkpoint_evidence_unavailable", None


def _next_safe_action(evidence: dict[str, Any], job_id: Any) -> str:
    reason = evidence.get("reason")
    if not isinstance(reason, str):
        reason = None
    # The current block reason outranks PM evidence retained from an earlier epoch.
    if reason in _HUMAN_DECISION_REASONS | _BUDGET_DECISION_REASONS:
        return "human_decision"
    if reason in _REROUTE_REASONS:
        return "reroute"
    if reason in _DELIVERY_RECOVERY_REASONS:
        return "retry_delivery"
    if reason in _REPLAN_REASONS:
        return "replan"
    if reason not in _PUBLIC_BLOCK_REASONS and (
        evidence.get("pm_outcome") == "needs_human_decision"
        or evidence.get("pm_action") == "human_decision"
        or isinstance(evidence.get("decision_key"), str)
    ):
        return "human_decision"
    if job_id is None:
        return "replan"
    return "repair"


def blocked_plan_evidence(snapshot: dict[str, Any]) -> dict[str, Any] | None:
    """Project one advisory-only blocked diagnosis from durable checkpoint state."""
    rows = [dict(row) for row in snapshot.get("work_orders") or []]
    blocked = next((row for row in rows if row.get("state") == "blocked"), None)
    if blocked is None:
        return None
    raw_checkpoint = snapshot.get("blocked_checkpoint")
    checkpoint = checkpoint_read_model(dict(raw_checkpoint)) if raw_checkpoint is not None else None
    evidence = _object((raw_checkpoint or {}).get("evidence"))
    history_rows = list((snapshot.get("current_checkpoint_history") or [])[:32])
    if not history_rows and isinstance(raw_checkpoint, dict):
        history_rows = [raw_checkpoint]
    current_history = [
        _object(item.get("evidence"))
        for item in history_rows
        if isinstance(item, dict)
    ]
    latest_verification = next(
        (summary for item in current_history
         if (summary := _verification_summary(item.get("verification"))) is not None),
        None,
    )
    latest_outcome: dict[str, str] = {}
    for key, allowed in (
        ("review_verdict", _OUTCOMES),
        ("pm_outcome", _OUTCOMES),
        ("pm_action", _PM_ACTIONS),
    ):
        value = next((item.get(key) for item in current_history if item.get(key) in allowed), None)
        if isinstance(value, str):
            latest_outcome[key] = value
    current_branch = next((
        branch for item in current_history
        if (branch := _safe_text(item.get("branch"), _SAFE_REF, 300)) is not None
    ), None)
    reason, reason_sha256 = _blocked_reason(evidence)
    definitions = {
        item.get("id"): item for item in _object(
            _object(snapshot.get("orchestration")).get("plan")
        ).get("work_orders", [])
        if isinstance(item, dict)
    }
    completed_by_work_order = {
        row.get("work_order_id"): row
        for row in snapshot.get("completed_checkpoints") or []
        if isinstance(row, dict)
    }
    completed = []
    pending = []
    for row in rows[:30]:
        work_order_id = _safe_text(row.get("work_order_id"), _SAFE_IDENTITY, 200)
        if work_order_id is None:
            continue
        if row.get("state") == "completed":
            completed.append({
                "work_order_id": work_order_id,
                "checkpoint": checkpoint_read_model(completed_by_work_order.get(work_order_id)),
            })
        elif row.get("state") == "pending":
            definition = _object(definitions.get(row.get("work_order_id")))
            dependencies = [
                value for value in (
                    _safe_text(item, _SAFE_IDENTITY, 200)
                    for item in (definition.get("dependencies") or [])[:30]
                ) if value is not None
            ]
            pending.append({
                "work_order_id": work_order_id,
                "state": "pending",
                "job_id": _safe_text(row.get("job_id"), _SAFE_IDENTITY, 200),
                "dependencies": dependencies,
            })
    current = {
        "work_order_id": _safe_text(blocked.get("work_order_id"), _SAFE_IDENTITY, 200),
        "job_id": _safe_text(blocked.get("job_id"), _SAFE_IDENTITY, 200),
        "branch": current_branch,
        "checkpoint_id": checkpoint.get("id") if checkpoint else None,
        "checkpoint_key": checkpoint.get("checkpoint_key") if checkpoint else None,
    }
    pack = {
        "completed_work_orders": completed,
        "current": current,
        "reason": reason,
        "latest_verification": latest_verification,
        "latest_outcome": latest_outcome or None,
        "pending_work_orders": pending,
        "last_known_good_checkpoint": checkpoint_read_model(snapshot.get("last_good_checkpoint")),
        "next_safe_action": _next_safe_action(
            {**evidence, **latest_outcome}, blocked.get("job_id")
        ),
    }
    if reason_sha256 is not None:
        pack["reason_sha256"] = reason_sha256
    return pack


def transition_key(
    tracked: dict[str, Any], kind: str, job_id: str | None,
    evidence: dict[str, Any], job: dict[str, Any] | None = None,
) -> str:
    """Hash persisted identity only; never sample a clock, UUID or polling count.

    The persisted source WorkOrder version distinguishes a later block/decision/
    acceptance episode after recovery, including recovery without counter growth.
    """
    identity = {"plan_id": tracked["plan_id"], "work_order_id": tracked["work_order_id"], "kind": kind, "job_id": job_id}
    if kind != "started":
        identity["source_version"] = str(tracked.get("updated_at") or "")
        identity["job_version"] = str((job or {}).get("updated_at") or "")
        identity["transition"] = {key: evidence[key] for key in (
            "decision_source", "decision_key", "review_repair_request_id", "expected_commit",
            "produced_commit", "pr_number", "pr_head", "merge_commit", "reason", "reason_sha256",
            "repair_iterations", "verification_attempts", "model_calls", "test_runs",
        ) if key in evidence}
    encoded = json.dumps(identity, sort_keys=True, separators=(",", ":"))
    return f"wo:{kind}:" + hashlib.sha256(encoded.encode("utf-8")).hexdigest()
