from __future__ import annotations

import hashlib
from collections import Counter
from typing import Any


_PLATFORM_BLOCK_REASONS = {
    "pm_reassessment_failed",
    "pm_reassessment_invalid_protected_approval",
    "collaboration_failed",
    "repeated_deterministic_verification_failure",
    "evaluator_protocol_failure_without_fallback",
    "provider_failure_without_fallback",
}
_MIN_REPAIR_CHURN = 4
_MIN_VERIFICATION_RETRIES = 2
_MIN_PROVIDER_FAILOVERS = 2


def _work_order_id(row: dict[str, Any]) -> str:
    checkpoint = row.get("checkpoint") or {}
    work_order = checkpoint.get("work_order") or {}
    return str(work_order.get("id") or "legacy-task")


def _stable_candidate_id(row: dict[str, Any]) -> str:
    seed = ":".join(
        [
            str(row.get("project_id") or "unknown"),
            str(row.get("id") or "unknown"),
            _work_order_id(row),
        ]
    )
    digest = hashlib.sha256(seed.encode("utf-8", errors="replace")).hexdigest()[:20]
    return f"incident:{digest}"


def incident_learning_candidate(row: dict[str, Any]) -> dict[str, Any] | None:
    """Create at most one bounded deterministic incident candidate per job.

    Ordinary first failures deliberately produce no candidate. Signals describe
    reusable execution anomalies only; classification remains a PM checkpoint
    responsibility.
    """

    progress = dict(row.get("progress") or {})
    checkpoint = dict(row.get("checkpoint") or {})
    result = dict(row.get("result") or {})
    reason = str(result.get("reason") or "")
    signals: list[str] = []

    fingerprints = [
        str(item)
        for item in progress.get("failure_fingerprints") or []
        if str(item)
    ]
    if fingerprints and max(Counter(fingerprints).values()) >= 2:
        signals.append("repeated_failure_fingerprint")

    verification_retries = int(progress.get("verification_retry_attempts", 0) or 0)
    if verification_retries >= _MIN_VERIFICATION_RETRIES:
        signals.append("verification_retry_anomaly")

    repair_iterations = int(progress.get("repair_iterations", 0) or 0)
    if repair_iterations >= _MIN_REPAIR_CHURN:
        signals.append("repair_churn")

    provider_failovers = int(progress.get("provider_failovers", 0) or 0)
    model_failovers = int(progress.get("model_failovers", 0) or 0)
    if provider_failovers + model_failovers >= _MIN_PROVIDER_FAILOVERS:
        signals.append("routing_failover_churn")

    if reason in _PLATFORM_BLOCK_REASONS:
        signals.append(f"platform_block:{reason}")

    if checkpoint.get("source_advance_history"):
        signals.append("manual_source_recovery")

    if not signals:
        return None

    provider_failures = [
        item
        for item in progress.get("provider_failures") or []
        if isinstance(item, dict)
    ]
    return {
        "id": _stable_candidate_id(row),
        "state": "candidate",
        "classification_required": True,
        "project_id": str(row.get("project_id") or ""),
        "job_id": str(row.get("id") or ""),
        "work_order_id": _work_order_id(row),
        "signals": sorted(set(signals)),
        "observed": {
            "status": str(row.get("status") or "unknown"),
            "reason": reason or None,
            "repair_iterations": repair_iterations,
            "verification_retries": verification_retries,
            "test_runs": int(progress.get("test_runs", 0) or 0),
            "model_calls": int(progress.get("model_calls", 0) or 0),
            "tool_calls": int(progress.get("tool_calls", 0) or 0),
            "provider_failures": len(provider_failures),
            "provider_failovers": provider_failovers,
            "model_failovers": model_failovers,
        },
        "evidence_refs": [
            f"runtime:job:{row.get('id')}",
            f"work_order:{_work_order_id(row)}",
        ],
        "pm_contract": {
            "classify_once_at_meaningful_checkpoint": True,
            "allowed_classifications": [
                "ephemeral_task_failure",
                "project_runbook_lesson",
                "platform_operational_lesson",
                "verification_contract_change",
                "platform_defect",
                "governance_change_proposal",
            ],
            "raw_logs_embedded": False,
        },
    }


__all__ = ["incident_learning_candidate"]
