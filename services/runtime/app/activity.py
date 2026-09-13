from __future__ import annotations

from typing import Any


_EVENT_DEFINITIONS: dict[str, tuple[str, str, str]] = {
    "job_registered": ("queue", "info", "Job registered"),
    "job_queued": ("queue", "info", "Job queued"),
    "job_resumed": ("queue", "info", "Job resumed"),
    "route_selected": ("routing", "info", "Route selected"),
    "routing_started": ("routing", "info", "Routing started"),
    "planner_started": ("planning", "info", "Planner started"),
    "executor_started": ("execution", "info", "Executor started"),
    "verification_started": ("verification", "info", "Verification started"),
    "evaluator_started": ("evaluation", "info", "Independent review started"),
    "delivery_started": ("delivery", "info", "Delivery started"),
    "waiting_human": ("human_gate", "warning", "Waiting for human decision"),
    "job_blocked": ("blocked", "error", "Job blocked"),
    "job_completed": ("completed", "success", "Job completed"),
    "job_failed": ("failed", "error", "Job failed"),
    "job_cancelled": ("cancelled", "warning", "Job cancelled"),
    "job_interrupted": ("interrupted", "warning", "Job interrupted"),
}

_STATUS_EVENT_TYPES = {
    "queued": "job_queued",
    "routing": "routing_started",
    "planning": "planner_started",
    "executing": "executor_started",
    "verifying": "verification_started",
    "evaluating": "evaluator_started",
    "delivering": "delivery_started",
    "waiting_human": "waiting_human",
    "blocked": "job_blocked",
    "completed": "job_completed",
    "failed": "job_failed",
    "cancelled": "job_cancelled",
    "interrupted": "job_interrupted",
}

_PAUSED = {"blocked", "interrupted", "waiting_human"}
_SAFE_STATUSES = set(_STATUS_EVENT_TYPES) | {"unknown"}
_SAFE_DATA_KEYS = {
    "from_status",
    "to_status",
    "profile",
    "analysis_depth",
}
_SAFE_CHOICE_KEYS = {"id", "provider", "model", "reasoning_effort"}


def _bounded_text(value: Any, limit: int = 160) -> str | None:
    if value is None:
        return None
    return str(value)[:limit]


def _definition(event_type: str) -> tuple[str, str, str]:
    return _EVENT_DEFINITIONS[event_type]


def _event(event_type: str, data: dict[str, Any] | None = None) -> dict[str, Any]:
    phase, level, message = _definition(event_type)
    return {
        "event_type": event_type,
        "phase": phase,
        "level": level,
        "message": message,
        "data": data or {},
    }


def job_registered_event() -> dict[str, Any]:
    return _event("job_registered")


def status_transition_event(previous_status: Any, next_status: Any) -> dict[str, Any] | None:
    previous = _bounded_text(previous_status, 40) or "unknown"
    current = _bounded_text(next_status, 40) or "unknown"
    if previous not in _SAFE_STATUSES:
        previous = "unknown"
    if previous == current or current not in _STATUS_EVENT_TYPES:
        return None
    event_type = "job_resumed" if current == "queued" and previous in _PAUSED else _STATUS_EVENT_TYPES[current]
    return _event(event_type, {"from_status": previous, "to_status": current})


def _safe_choice(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, dict) or not value:
        return None
    choice = {
        key: _bounded_text(value.get(key))
        for key in _SAFE_CHOICE_KEYS
        if value.get(key) is not None
    }
    return choice or None


def route_selected_event(route: Any) -> dict[str, Any] | None:
    if not isinstance(route, dict) or not route:
        return None
    strategy = route.get("strategy")
    if not isinstance(strategy, dict):
        return None
    data: dict[str, Any] = {}
    profile = _bounded_text(strategy.get("profile"), 40)
    if profile:
        data["profile"] = profile
    analysis_depth = strategy.get("analysis_depth")
    if isinstance(analysis_depth, int):
        data["analysis_depth"] = analysis_depth
    for role in ("planner", "executor", "evaluator"):
        choice = _safe_choice(strategy.get(role))
        if choice:
            data[role] = choice
    return _event("route_selected", data)


def public_event(row: dict[str, Any]) -> dict[str, Any] | None:
    """Return the dashboard contract from fixed definitions and allow-listed data."""

    event_type = str(row.get("event_type") or "")
    if event_type not in _EVENT_DEFINITIONS:
        return None
    phase, level, message = _definition(event_type)
    source = row.get("data") if isinstance(row.get("data"), dict) else {}
    data: dict[str, Any] = {}
    for key in _SAFE_DATA_KEYS:
        value = source.get(key)
        if key == "analysis_depth":
            if isinstance(value, int):
                data[key] = value
        else:
            bounded = _bounded_text(value)
            if key in {"from_status", "to_status"} and bounded not in _SAFE_STATUSES:
                continue
            if bounded is not None:
                data[key] = bounded
    for role in ("planner", "executor", "evaluator"):
        choice = _safe_choice(source.get(role))
        if choice:
            data[role] = choice
    created_at = row.get("created_at")
    timestamp = created_at.isoformat() if hasattr(created_at, "isoformat") else str(created_at or "")
    return {
        "seq": int(row.get("id") or 0),
        "timestamp": timestamp,
        "job_id": _bounded_text(row.get("job_id"), 64),
        "phase": phase,
        "level": level,
        "event": event_type,
        "message": message,
        "data": data,
    }
