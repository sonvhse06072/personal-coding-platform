from __future__ import annotations

from copy import deepcopy
from typing import Any

from .config import routing_policy_doc
from .storage import now


EPOCH_KEY = "review_repair_churn_epoch"
GATE_KEY = "review_repair_churn_gate"
HISTORY_KEY = "review_repair_churn_history"
INITIALIZED_KEY = "review_repair_churn_initialized"
DECISION_SOURCE = "review_repair_churn"
RESULT_REASON = "repair_churn_circuit_breaker"
_TAIL_LIMIT = 8


class ReviewRepairChurnPaused(RuntimeError):
    """Internal control flow after the durable Human Owner gate is persisted."""


class ReviewRepairChurnIntegrityError(RuntimeError):
    """Durable churn metadata cannot safely authorize execution or migration."""


def configured_limits() -> dict[str, int]:
    anti_loop = dict(routing_policy_doc().get("anti_loop") or {})
    raw = {
        "repair_cycles": anti_loop.get("review_repair_max_repair_cycles"),
        "verification_cycles": anti_loop.get(
            "review_repair_max_verification_cycles"
        ),
    }
    limits: dict[str, int] = {}
    for name, value in raw.items():
        try:
            normalized = int(value)
        except (TypeError, ValueError) as exc:
            raise RuntimeError(
                f"Routing policy is missing a valid review-repair churn limit: {name}"
            ) from exc
        if normalized <= 0:
            raise RuntimeError(
                f"Routing policy review-repair churn limit must be positive: {name}"
            )
        limits[name] = normalized
    return limits


def counter_snapshot(progress: dict[str, Any]) -> dict[str, int]:
    return {
        "repair_iterations": max(0, int(progress.get("repair_iterations", 0) or 0)),
        "verification_attempts": max(
            0, int(progress.get("verification_attempts", 0) or 0)
        ),
    }


def new_epoch(
    request_id: str,
    progress: dict[str, Any],
    *,
    started_at: str | None = None,
    legacy_baseline_migrated: bool,
) -> dict[str, Any]:
    normalized_request_id = str(request_id or "").strip()
    if not normalized_request_id:
        raise RuntimeError("Review-repair churn epoch requires an exact request id")
    return {
        "request_id": normalized_request_id,
        "generation": 0,
        "baseline": counter_snapshot(progress),
        "limits": configured_limits(),
        "started_at": started_at or now().isoformat(),
        "legacy_baseline_migrated": bool(legacy_baseline_migrated),
        "baseline_origin": (
            "legacy_first_resume" if legacy_baseline_migrated else "request_time"
        ),
    }


def active_record(checkpoint: dict[str, Any]) -> dict[str, Any] | None:
    for key in ("pending_review_repair", "active_review_repair"):
        candidate = checkpoint.get(key)
        if isinstance(candidate, dict) and str(candidate.get("request_id") or ""):
            return candidate
    return None


def validate_epoch(
    checkpoint: dict[str, Any],
    *,
    require_active: bool = True,
) -> dict[str, Any] | None:
    record = active_record(checkpoint)
    epoch = checkpoint.get(EPOCH_KEY)
    if record is None:
        if require_active and any(
            key in checkpoint for key in (EPOCH_KEY, GATE_KEY, INITIALIZED_KEY)
        ):
            raise ReviewRepairChurnIntegrityError(
                "Review-repair churn epoch exists without an active review-repair request"
            )
        return None
    request_id = str(record.get("request_id") or "")
    pending = checkpoint.get("pending_decision")
    churn_pending = isinstance(pending, dict) and (
        pending.get("source") == DECISION_SOURCE
        or str(pending.get("key") or "").startswith(f"{DECISION_SOURCE}:")
    )
    history = checkpoint.get(HISTORY_KEY, [])
    if not isinstance(history, list):
        raise ReviewRepairChurnIntegrityError("Review-repair churn history is malformed")
    prior_request = any(
        isinstance(item, dict) and item.get("request_id") == request_id
        for item in history
    )
    decisions = checkpoint.get("decision_history") or []
    if not isinstance(decisions, list):
        raise ReviewRepairChurnIntegrityError("Review-repair churn decision history is malformed")
    prior_request = prior_request or any(
        isinstance(item, dict)
        and (
            (item.get("source") == DECISION_SOURCE and item.get("request_id") == request_id)
            or str(item.get("key") or "").startswith(
                f"{DECISION_SOURCE}:{request_id}:generation:"
            )
        )
        for item in decisions
    )
    if EPOCH_KEY not in checkpoint:
        if GATE_KEY in checkpoint or churn_pending or INITIALIZED_KEY in checkpoint or prior_request:
            raise ReviewRepairChurnIntegrityError(
                "Review-repair churn epoch is missing after prior initialization"
            )
        return None
    if not isinstance(epoch, dict):
        raise ReviewRepairChurnIntegrityError("Review-repair churn epoch is malformed")
    if epoch.get("request_id") != request_id:
        raise ReviewRepairChurnIntegrityError(
            "Review-repair churn epoch does not match the active request id"
        )
    try:
        baseline = epoch["baseline"]
        limits = epoch["limits"]
        if not isinstance(baseline, dict) or not isinstance(limits, dict):
            raise TypeError()
        values = [
            epoch["generation"],
            baseline["repair_iterations"],
            baseline["verification_attempts"],
            limits["repair_cycles"],
            limits["verification_cycles"],
        ]
    except (KeyError, TypeError) as exc:
        raise ReviewRepairChurnIntegrityError("Review-repair churn epoch is malformed") from exc
    if (
        any(type(value) is not int for value in values)
        or any(value < 0 for value in values[:3])
        or any(value <= 0 for value in values[3:])
    ):
        raise ReviewRepairChurnIntegrityError("Review-repair churn epoch contains invalid counters or limits")
    if (
        not isinstance(epoch.get("started_at"), str)
        or not epoch["started_at"].strip()
        or type(epoch.get("legacy_baseline_migrated")) is not bool
        or epoch.get("baseline_origin") not in (
            "request_time", "legacy_first_resume", "human_authorized_window"
        )
    ):
        raise ReviewRepairChurnIntegrityError("Review-repair churn initialization metadata is malformed")
    if INITIALIZED_KEY in checkpoint and checkpoint[INITIALIZED_KEY] != {"request_id": request_id}:
        raise ReviewRepairChurnIntegrityError("Review-repair churn initialization identity is inconsistent")
    expected_key = decision_identity(request_id, epoch["generation"])
    if GATE_KEY in checkpoint:
        gate = checkpoint[GATE_KEY]
        if (
            not isinstance(gate, dict)
            or gate.get("request_id") != request_id
            or type(gate.get("generation")) is not int
            or gate["generation"] != epoch["generation"]
            or gate.get("decision_key") != expected_key
            or gate.get("baseline") != baseline
            or gate.get("limits") != limits
        ):
            raise ReviewRepairChurnIntegrityError("Review-repair churn gate identity is incomplete or inconsistent")
    if churn_pending and (
        GATE_KEY not in checkpoint
        or pending.get("source") != DECISION_SOURCE
        or pending.get("request_id") != request_id
        or type(pending.get("generation")) is not int
        or pending["generation"] != epoch["generation"]
        or pending.get("key") != expected_key
    ):
        raise ReviewRepairChurnIntegrityError("Review-repair churn pending decision identity is inconsistent")
    return epoch


def ensure_legacy_epoch(
    checkpoint: dict[str, Any],
    progress: dict[str, Any],
) -> bool:
    existing = validate_epoch(checkpoint)
    record = active_record(checkpoint)
    if record is None:
        return False
    if existing is not None:
        return False
    checkpoint[EPOCH_KEY] = new_epoch(
        str(record["request_id"]),
        progress,
        legacy_baseline_migrated=True,
    )
    checkpoint[INITIALIZED_KEY] = {"request_id": str(record["request_id"])}
    return True


def decision_identity(request_id: str, generation: int) -> str:
    return f"review_repair_churn:{request_id}:generation:{int(generation)}"


def integrity_evidence(checkpoint: dict[str, Any], error: Exception) -> dict[str, Any]:
    """Report bounded identities, keeping original malformed metadata untouched."""
    payload: dict[str, Any] = {"integrity_error": str(error)[:500]}
    for key in ("pending_review_repair", "active_review_repair", EPOCH_KEY, GATE_KEY, INITIALIZED_KEY, "pending_decision"):
        value = checkpoint.get(key)
        summary = {"present": key in checkpoint, "type": type(value).__name__}
        if isinstance(value, dict):
            summary.update({
                field: str(value[field])[:160]
                for field in ("request_id", "generation", "key", "decision_key")
                if field in value
            })
        payload[key] = summary
    return payload


def bounded_verification_summary(verification: dict[str, Any]) -> dict[str, Any]:
    phases: list[dict[str, Any]] = []
    for item in verification.get("phases") or []:
        if not isinstance(item, dict):
            continue
        phases.append(
            {
                "phase": str(item.get("phase") or "")[:120],
                "passed": bool(item.get("passed", False)),
                "verification_layer": str(
                    item.get("verification_layer") or ""
                )[:40],
            }
        )
        if len(phases) >= _TAIL_LIMIT:
            break
    return {
        "passed": bool(verification.get("passed", False)),
        "tests_passed": bool(verification.get("tests_passed", False)),
        "verification_mode": str(verification.get("verification_mode") or "")[:80],
        "verification_attempt": int(
            verification.get("verification_attempt", 0) or 0
        ),
        "phases": phases,
        "failure_text": str(verification.get("failure_text") or "")[-4000:],
    }


def bounded_review_summary(review: dict[str, Any]) -> dict[str, Any]:
    findings: list[dict[str, Any]] = []
    for item in review.get("findings") or []:
        if not isinstance(item, dict):
            continue
        findings.append(
            {
                "id": str(item.get("id") or "")[:120],
                "severity": str(item.get("severity") or "")[:40],
                "category": str(item.get("category") or "")[:80],
                "message": str(item.get("message") or "")[:1000],
            }
        )
        if len(findings) >= _TAIL_LIMIT:
            break
    return {
        "verdict": str(review.get("verdict") or "")[:40],
        "summary": str(review.get("summary") or "")[:4000],
        "finding_count": max(0, int(review.get("finding_count", 0) or 0)),
        "findings": findings,
    }


def record_observation(
    checkpoint: dict[str, Any],
    *,
    diff_hash: str | None = None,
    verification: dict[str, Any] | None = None,
    review: dict[str, Any] | None = None,
) -> None:
    epoch = validate_epoch(checkpoint, require_active=False)
    if epoch is None:
        return
    if diff_hash:
        epoch["latest_diff_hash"] = str(diff_hash)[:200]
    if isinstance(verification, dict):
        epoch["latest_verification_summary"] = bounded_verification_summary(
            verification
        )
    if isinstance(review, dict):
        epoch["latest_review_summary"] = bounded_review_summary(review)
    checkpoint[EPOCH_KEY] = epoch


def evidence(
    checkpoint: dict[str, Any],
    progress: dict[str, Any],
) -> tuple[bool, dict[str, Any]]:
    epoch = validate_epoch(checkpoint)
    if epoch is None:
        return False, {}
    if GATE_KEY in checkpoint:
        # A persisted stop is latched, even if a stale progress snapshot falls
        # below the tripped counters. Preserve the original evidence until the
        # exact decision opens the next generation or delivery archives it.
        return True, deepcopy(checkpoint[GATE_KEY])
    baseline = {
        "repair_iterations": int(epoch["baseline"]["repair_iterations"]),
        "verification_attempts": int(
            epoch["baseline"]["verification_attempts"]
        ),
    }
    current = counter_snapshot(progress)
    regression = any(current[name] < baseline[name] for name in baseline)
    delta = {
        name: max(0, current[name] - baseline[name]) for name in baseline
    }
    limits = {
        "repair_cycles": int(epoch["limits"]["repair_cycles"]),
        "verification_cycles": int(epoch["limits"]["verification_cycles"]),
    }
    reached = {
        "repair_cycles": delta["repair_iterations"] >= limits["repair_cycles"],
        "verification_cycles": (
            delta["verification_attempts"] >= limits["verification_cycles"]
        ),
        "counter_regression": regression,
    }
    request_id = str(epoch["request_id"])
    generation = int(epoch["generation"])
    payload = {
        "request_id": request_id,
        "generation": generation,
        "decision_key": decision_identity(request_id, generation),
        "baseline": baseline,
        "current": current,
        "delta": delta,
        "limits": limits,
        "reached": reached,
        "latest_diff_hash": str(
            epoch.get("latest_diff_hash")
            or ((progress.get("diff_hashes") or [""])[-1])
            or ""
        )[:200],
        "failure_fingerprint_tail": [
            str(item)[:200]
            for item in (progress.get("failure_fingerprints") or [])[-_TAIL_LIMIT:]
        ],
        "progress_marker_tail": [
            str(item)[:300]
            for item in (progress.get("progress_markers") or [])[-_TAIL_LIMIT:]
        ],
        "latest_review_summary": deepcopy(epoch.get("latest_review_summary")),
        "latest_verification_summary": deepcopy(
            epoch.get("latest_verification_summary")
        ),
    }
    return any(reached.values()), payload


def archive_epoch(checkpoint: dict[str, Any], request_id: str, **updates: Any) -> None:
    epoch = checkpoint.get(EPOCH_KEY)
    if not isinstance(epoch, dict):
        return
    if str(epoch.get("request_id") or "") != str(request_id or ""):
        raise RuntimeError(
            "Cannot archive a review-repair churn epoch for a different request"
        )
    archived = deepcopy(epoch)
    archived.update(deepcopy(updates))
    history = [
        deepcopy(item)
        for item in (checkpoint.get(HISTORY_KEY) or [])
        if isinstance(item, dict)
    ]
    history.append(archived)
    checkpoint[HISTORY_KEY] = history[-20:]
    checkpoint.pop(EPOCH_KEY, None)
    checkpoint.pop(GATE_KEY, None)
    checkpoint.pop(INITIALIZED_KEY, None)
