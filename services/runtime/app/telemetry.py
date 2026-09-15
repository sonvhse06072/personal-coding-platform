from __future__ import annotations

from collections import defaultdict
from typing import Any


_RESOURCE_COUNTERS = {
    "max_model_calls": "model_calls",
    "max_tool_calls": "tool_calls",
    "max_iterations": "iteration",
    "max_repair_iterations": "repair_iterations",
    "max_test_runs": "test_runs",
    "max_wall_time_minutes": "elapsed_minutes",
}
_TERMINAL = {"completed", "failed", "cancelled"}


def _accepted_result(row: dict[str, Any]) -> dict[str, Any]:
    result = dict(row.get("result") or {})
    if result.get("status") == "accepted":
        return result
    nested = result.get("accepted_result")
    return dict(nested) if isinstance(nested, dict) else result


def _work_order(row: dict[str, Any]) -> dict[str, Any]:
    checkpoint = row.get("checkpoint") or {}
    value = checkpoint.get("work_order")
    return dict(value) if isinstance(value, dict) else {}


def _executor(row: dict[str, Any]) -> dict[str, Any]:
    route = row.get("route") or {}
    strategy = route.get("strategy") or {}
    checkpoint = row.get("checkpoint") or {}
    choice = checkpoint.get("executor_choice") or strategy.get("executor") or {}
    return dict(choice) if isinstance(choice, dict) else {}


def _estimated_resources(strategy: dict[str, Any]) -> dict[str, float]:
    adaptive = strategy.get("adaptive_budget") or {}
    dimensions = adaptive.get("dimensions") or {}
    result: dict[str, float] = {}
    for dimension in _RESOURCE_COUNTERS:
        envelope = dimensions.get(dimension) if isinstance(dimensions, dict) else None
        if isinstance(envelope, dict) and envelope.get("estimate") is not None:
            try:
                result[dimension] = float(envelope["estimate"])
            except (TypeError, ValueError):
                pass
    if result:
        return result

    budget = strategy.get("budget") or {}
    for dimension in _RESOURCE_COUNTERS:
        if dimension not in budget:
            continue
        try:
            result[dimension] = float(budget[dimension])
        except (TypeError, ValueError):
            continue
    return result


def _actual_resources(progress: dict[str, Any]) -> dict[str, float]:
    result: dict[str, float] = {}
    for dimension, counter in _RESOURCE_COUNTERS.items():
        try:
            result[dimension] = float(progress.get(counter, 0.0) or 0.0)
        except (TypeError, ValueError):
            result[dimension] = 0.0
    return result


def _verification_counts(result: dict[str, Any], progress: dict[str, Any]) -> dict[str, int]:
    verification = result.get("verification") or {}
    phases = verification.get("phases") or []
    targeted = 0
    full = 0
    for phase in phases:
        if not isinstance(phase, dict):
            continue
        name = str(phase.get("phase") or "")
        layer = str(phase.get("verification_layer") or "")
        if name == "targeted_tests" or layer == "intermediate":
            targeted += 1
        if name == "full_tests" or layer == "final":
            full += 1
    return {
        "targeted_runs": targeted,
        "full_runs": full,
        "verification_attempts": int(progress.get("verification_attempts", 0) or 0),
        "verification_retries": int(progress.get("verification_retry_attempts", 0) or 0),
    }


def _ci_pass(result: dict[str, Any]) -> bool | None:
    delivery = result.get("delivery") or {}
    if not isinstance(delivery, dict) or not delivery.get("enabled"):
        return None
    state = str(delivery.get("state") or "")
    if state in {"ci_success", "ci_none"}:
        return True
    if state == "ci_failure":
        return False
    return None


def task_telemetry_snapshot(row: dict[str, Any]) -> dict[str, Any]:
    """Build one compact durable measurement from the current job row."""
    status = str(row.get("status") or "unknown")
    task = dict(row.get("task") or {})
    work_order = _work_order(row)
    route = dict(row.get("route") or {})
    strategy = dict(route.get("strategy") or {})
    progress = dict(row.get("progress") or {})
    result = _accepted_result(row)
    executor = _executor(row)
    estimated = _estimated_resources(strategy)
    actual = _actual_resources(progress)
    accepted = status == "completed" and result.get("status") in {None, "accepted"}
    first_pass = bool(
        accepted
        and int(progress.get("repair_iterations", 0) or 0) == 0
        and int(progress.get("verification_retry_attempts", 0) or 0) == 0
        and int(progress.get("ci_failures", 0) or 0) == 0
        and int(progress.get("iteration", 0) or 0) <= 1
    )
    provider_failures = [
        item for item in (progress.get("provider_failures") or []) if isinstance(item, dict)
    ]
    quota_failures = sum(
        1 for item in provider_failures if str(item.get("kind") or "") in {"quota_exhausted", "rate_limited"}
    )
    exceeded_without_success = any(
        actual.get(key, 0.0) >= estimate
        for key, estimate in estimated.items()
        if estimate > 0
    ) and not accepted
    adaptive = strategy.get("adaptive_budget") or {}

    return {
        "job_id": str(row.get("id") or ""),
        "project_id": str(row.get("project_id") or ""),
        "task_type": str(task.get("task_type") or "unknown"),
        "role": str(work_order.get("requested_role") or "developer"),
        "profile": str(strategy.get("profile") or "unknown"),
        "provider": str(executor.get("provider") or "unknown"),
        "model_id": str(executor.get("id") or "unknown"),
        "status": status,
        "terminal": status in _TERMINAL,
        "task_outcome": (
            "accepted" if accepted else "failed" if status == "failed" else "cancelled" if status == "cancelled" else "blocked"
        ),
        "first_pass_success": first_pass,
        "repair_count": int(progress.get("repair_iterations", 0) or 0),
        "verification": _verification_counts(result, progress),
        "ci_pass": _ci_pass(result),
        "review": {
            "runs": int(progress.get("review_runs", 0) or 0),
            "findings": int(progress.get("review_findings", 0) or 0),
            "findings_actioned": int(progress.get("review_findings_actioned", 0) or 0),
            "useful_finding_yield": float(progress.get("review_useful_finding_yield", 0.0) or 0.0),
            "input_tokens": int(progress.get("review_input_tokens", 0) or 0),
            "output_tokens": int(progress.get("review_output_tokens", 0) or 0),
            "cost_usd": float(progress.get("review_cost_usd", 0.0) or 0.0),
        },
        "resources": {
            "estimate_source": "adaptive" if bool(adaptive.get("enabled")) else "legacy_profile_ceiling",
            "estimated": estimated,
            "actual": actual,
            "model_calls": int(progress.get("model_calls", 0) or 0),
            "input_tokens": int(progress.get("input_tokens", 0) or 0),
            "output_tokens": int(progress.get("output_tokens", 0) or 0),
            "tool_calls": int(progress.get("tool_calls", 0) or 0),
            "test_runs": int(progress.get("test_runs", 0) or 0),
            "wall_time_minutes": float(progress.get("elapsed_minutes", 0.0) or 0.0),
            "cost_usd": float(progress.get("cost_usd", 0.0) or 0.0),
            "budget_without_useful_outcome": exceeded_without_success,
        },
        "provider_failures": len(provider_failures),
        "quota_failures": quota_failures,
        "delivery_retries": int(progress.get("delivery_retry_attempts", 0) or 0),
        "infrastructure_retries": int(progress.get("infrastructure_retry_attempts", 0) or 0),
    }


def classify_attention_event(kind: str, row: dict[str, Any]) -> dict[str, Any]:
    """Classify owner attention as protected-decision or routine operations."""
    normalized = str(kind).strip().lower()
    if normalized == "human_decision":
        return {"category": "decision_boundary", "avoidable": False}
    if normalized == "budget_extension":
        strategy = ((row.get("route") or {}).get("strategy") or {})
        adaptive = strategy.get("adaptive_budget") or {}
        return {
            "category": "routine_operational",
            "avoidable": not bool(adaptive.get("enabled", False)),
        }
    return {"category": "routine_operational", "avoidable": False}


def classify_budget_attention(row: dict[str, Any]) -> dict[str, Any]:
    return classify_attention_event("budget_extension", row)


def aggregate_calibration(
    snapshots: list[dict[str, Any]],
    *,
    minimum_sample_size: int = 5,
) -> dict[str, Any]:
    """Return deliberately simple historical calibration evidence."""
    terminal = [item for item in snapshots if item.get("terminal")]
    total = len(terminal)
    resource_ratios: dict[str, list[float]] = defaultdict(list)
    model_stats: dict[str, dict[str, Any]] = {}

    for item in terminal:
        resources = item.get("resources") or {}
        estimated = resources.get("estimated") or {}
        actual = resources.get("actual") or {}
        for dimension in _RESOURCE_COUNTERS:
            try:
                estimate = float(estimated.get(dimension, 0.0) or 0.0)
                used = float(actual.get(dimension, 0.0) or 0.0)
            except (TypeError, ValueError):
                continue
            if estimate > 0:
                resource_ratios[dimension].append(used / estimate)

        model_id = str(item.get("model_id") or "")
        if model_id and model_id != "unknown":
            stats = model_stats.setdefault(model_id, {"sample_size": 0, "accepted": 0})
            stats["sample_size"] += 1
            stats["accepted"] += int(item.get("task_outcome") == "accepted")

    sufficient = total >= int(minimum_sample_size)
    multipliers: dict[str, float] = {}
    if sufficient:
        for dimension, values in resource_ratios.items():
            if not values:
                continue
            multipliers[dimension] = round(max(0.75, min(1.75, sum(values) / len(values))), 4)

    model_success: dict[str, dict[str, Any]] = {}
    for model_id, stats in model_stats.items():
        sample_size = int(stats["sample_size"])
        if sample_size < int(minimum_sample_size):
            continue
        model_success[model_id] = {
            "sample_size": sample_size,
            "success_rate": round(float(stats["accepted"]) / sample_size, 4),
        }

    accepted = sum(1 for item in terminal if item.get("task_outcome") == "accepted")
    first_pass = sum(1 for item in terminal if item.get("first_pass_success"))
    return {
        "sample_size": total,
        "minimum_sample_size": int(minimum_sample_size),
        "sufficient_sample": sufficient,
        "resource_multipliers": multipliers,
        "model_success": model_success,
        "observed_success_rate": round(accepted / total, 4) if total else None,
        "first_pass_success_rate": round(first_pass / total, 4) if total else None,
        "fallback": None if sufficient else "policy_defaults",
    }


__all__ = [
    "aggregate_calibration",
    "classify_attention_event",
    "classify_budget_attention",
    "task_telemetry_snapshot",
]
