from __future__ import annotations

from collections import defaultdict
from typing import Any

from .incident_learning import incident_learning_candidate


_RESOURCE_COUNTERS = {
    "max_model_calls": "model_calls",
    "max_tool_calls": "tool_calls",
    "max_iterations": "iteration",
    "max_repair_iterations": "repair_iterations",
    "max_test_runs": "test_runs",
    "max_wall_time_minutes": "elapsed_minutes",
}
_TERMINAL = {"completed", "failed", "cancelled"}
_CALIBRATION_TERMINAL = {"completed", "failed"}


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
    """Build one compact durable measurement from the current job row.

    ``terminal`` describes lifecycle state. ``calibration_eligible`` is stricter:
    dry-runs and user-cancelled jobs remain observable but never become historical
    staffing/budget training evidence.
    """
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
    dry_run = bool(row.get("dry_run", False) or result.get("dry_run", False))
    accepted = (
        status == "completed"
        and not dry_run
        and result.get("status") in {None, "accepted"}
    )
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
    terminal = status in _TERMINAL
    calibration_eligible = status in _CALIBRATION_TERMINAL and not dry_run

    if dry_run:
        task_outcome = "dry_run"
    elif accepted:
        task_outcome = "accepted"
    elif status == "failed":
        task_outcome = "failed"
    elif status == "cancelled":
        task_outcome = "cancelled"
    else:
        task_outcome = "blocked"

    incident = incident_learning_candidate(row)

    return {
        "job_id": str(row.get("id") or ""),
        "project_id": str(row.get("project_id") or ""),
        "task_type": str(task.get("task_type") or "unknown"),
        "role": str(work_order.get("requested_role") or "developer"),
        "profile": str(strategy.get("profile") or "unknown"),
        "provider": str(executor.get("provider") or "unknown"),
        "model_id": str(executor.get("id") or "unknown"),
        "status": status,
        "terminal": terminal,
        "calibration_eligible": calibration_eligible,
        "dry_run": dry_run,
        "task_outcome": task_outcome,
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
        "incident_learning": {
            "candidate": incident,
            "candidate_count": 1 if incident else 0,
        },
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
    """Return deliberately simple historical calibration evidence.

    Only calibration-eligible completed/failed jobs count. Resource multipliers
    use modern adaptive estimates only; legacy fixed ceilings are intentionally
    excluded so historical hard-stop policy cannot masquerade as an estimate.
    """
    eligible = [
        item for item in snapshots
        if item.get("calibration_eligible", item.get("terminal", False))
    ]
    total = len(eligible)
    resource_ratios: dict[str, list[float]] = defaultdict(list)
    model_stats: dict[str, dict[str, Any]] = {}

    for item in eligible:
        resources = item.get("resources") or {}
        estimated = resources.get("estimated") or {}
        actual = resources.get("actual") or {}
        if resources.get("estimate_source") == "adaptive":
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
            if len(values) < int(minimum_sample_size):
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

    accepted = sum(1 for item in eligible if item.get("task_outcome") == "accepted")
    first_pass = sum(1 for item in eligible if item.get("first_pass_success"))
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


def aggregate_telemetry_summary(
    snapshots: list[dict[str, Any]],
    *,
    attention: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Aggregate operational KPIs without fitting a statistical model."""
    rows = list(snapshots)
    eligible = [item for item in rows if item.get("calibration_eligible", False)]
    accepted = [item for item in eligible if item.get("task_outcome") == "accepted"]
    ci_observed = [item for item in rows if item.get("ci_pass") is not None]
    review_findings = sum(int((item.get("review") or {}).get("findings", 0) or 0) for item in rows)
    review_actioned = sum(
        int((item.get("review") or {}).get("findings_actioned", 0) or 0) for item in rows
    )
    resource_totals = {
        "model_calls": 0.0,
        "input_tokens": 0.0,
        "output_tokens": 0.0,
        "tool_calls": 0.0,
        "test_runs": 0.0,
        "wall_time_minutes": 0.0,
        "cost_usd": 0.0,
    }
    provider_model: dict[str, dict[str, Any]] = {}
    budget_without_outcome = 0
    targeted_runs = 0
    full_runs = 0
    verification_retries = 0
    provider_failures = 0
    quota_failures = 0

    for item in rows:
        verification = item.get("verification") or {}
        targeted_runs += int(verification.get("targeted_runs", 0) or 0)
        full_runs += int(verification.get("full_runs", 0) or 0)
        verification_retries += int(verification.get("verification_retries", 0) or 0)
        provider_failures += int(item.get("provider_failures", 0) or 0)
        quota_failures += int(item.get("quota_failures", 0) or 0)
        resources = item.get("resources") or {}
        budget_without_outcome += int(bool(resources.get("budget_without_useful_outcome")))
        for key in resource_totals:
            try:
                resource_totals[key] += float(resources.get(key, 0.0) or 0.0)
            except (TypeError, ValueError):
                pass

        provider = str(item.get("provider") or "unknown")
        model_id = str(item.get("model_id") or "unknown")
        key = f"{provider}:{model_id}"
        bucket = provider_model.setdefault(
            key,
            {"provider": provider, "model_id": model_id, "tasks": 0, "accepted": 0},
        )
        bucket["tasks"] += 1
        bucket["accepted"] += int(item.get("task_outcome") == "accepted")

    task_count = len(rows)
    eligible_count = len(eligible)
    first_pass_count = sum(int(bool(item.get("first_pass_success"))) for item in eligible)
    repair_total = sum(int(item.get("repair_count", 0) or 0) for item in eligible)
    model_breakdown = []
    for bucket in provider_model.values():
        tasks = int(bucket["tasks"])
        model_breakdown.append(
            {
                **bucket,
                "success_rate": round(int(bucket["accepted"]) / tasks, 4) if tasks else None,
            }
        )
    model_breakdown.sort(key=lambda item: (-int(item["tasks"]), item["provider"], item["model_id"]))

    return {
        "task_count": task_count,
        "calibration_eligible_tasks": eligible_count,
        "accepted_tasks": len(accepted),
        "observed_success_rate": round(len(accepted) / eligible_count, 4) if eligible_count else None,
        "first_pass_success_rate": round(first_pass_count / eligible_count, 4) if eligible_count else None,
        "average_repair_count": round(repair_total / eligible_count, 4) if eligible_count else None,
        "verification": {
            "targeted_runs": targeted_runs,
            "full_runs": full_runs,
            "retries": verification_retries,
        },
        "ci": {
            "observed_tasks": len(ci_observed),
            "pass_rate": (
                round(sum(int(bool(item.get("ci_pass"))) for item in ci_observed) / len(ci_observed), 4)
                if ci_observed else None
            ),
        },
        "review": {
            "findings": review_findings,
            "findings_actioned": review_actioned,
            "useful_finding_yield": round(review_actioned / review_findings, 4) if review_findings else None,
        },
        "resources": {
            key: round(value, 4) for key, value in resource_totals.items()
        },
        "provider_failures": provider_failures,
        "quota_failures": quota_failures,
        "budget_without_useful_outcome_tasks": budget_without_outcome,
        "provider_model_breakdown": model_breakdown,
        "human_attention": dict(attention or {}),
    }


__all__ = [
    "aggregate_calibration",
    "aggregate_telemetry_summary",
    "classify_attention_event",
    "classify_budget_attention",
    "task_telemetry_snapshot",
]
