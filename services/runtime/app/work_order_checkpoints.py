"""Bounded lifecycle evidence and identities; no execution or mutation authority."""
from __future__ import annotations

import hashlib
import json
import uuid
from typing import Any


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
    verification = _object(result.get("verification")) or _object(epoch.get("latest_verification_summary"))
    summary: dict[str, Any] = {}
    if type(verification.get("passed")) is bool:
        summary["passed"] = verification["passed"]
    phases = verification.get("phases")
    if isinstance(phases, list):
        summary["phases"] = [
            {"phase": _text(item.get("phase"), 80), "passed": item["passed"]}
            for item in phases[:16] if isinstance(item, dict)
            and _text(item.get("phase"), 80) and type(item.get("passed")) is bool
        ]
    if summary:
        evidence["verification"] = summary
    review = _object(result.get("review")) or _object(checkpoint.get("last_review_report"))
    pm = _object(result.get("pm_evidence"))
    for key, value in (("review_verdict", review.get("verdict")), ("pm_outcome", pm.get("outcome"))):
        if isinstance(value, str) and value in {"pass", "fail", "accepted", "repair", "blocked", "needs_human_decision", "not_required"}:
            evidence[key] = value
    pm_decision = _object(_object(checkpoint.get("last_pm_reassessment")).get("decision"))
    action = pm_decision.get("action")
    if isinstance(action, str) and action in {"approve_continue", "repair", "human_decision", "request_explanation"}:
        evidence["pm_action"] = action
    return evidence


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
