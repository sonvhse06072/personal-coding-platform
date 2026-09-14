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
    "developer_message": ("execution", "info", "Developer update"),
    "developer_command_started": ("execution", "info", "Command started"),
    "developer_command_completed": ("execution", "success", "Command completed"),
    "developer_file_activity": ("execution", "info", "Files changed"),
    "developer_error": ("execution", "error", "Developer error"),
    "developer_step": ("execution", "info", "Agent activity"),
    "runtime_activity": ("execution", "info", "Runtime activity"),
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
_SAFE_PHASES = {
    "queue", "routing", "planning", "execution", "verification", "evaluation",
    "reassessment", "delivery", "blocked", "completed", "failed", "interrupted",
    "human_gate", "provider",
}
_SAFE_LEVELS = {"info", "success", "warning", "error"}
_SAFE_DATA_KEYS = {
    "from_status",
    "to_status",
    "profile",
    "analysis_depth",
}
_SAFE_CHOICE_KEYS = {"id", "provider", "model", "reasoning_effort", "adapter"}
_DEVELOPER_EVENT_TYPES = {
    "developer_message",
    "developer_command_started",
    "developer_command_completed",
    "developer_file_activity",
    "developer_error",
    "developer_step",
}
_ACTIVITY_EVENT_TYPES = _DEVELOPER_EVENT_TYPES | {"runtime_activity"}
_ACTIVITY_TEXT_LIMITS = {
    "text": 2000,
    "command": 1000,
    "output": 3000,
    "status": 80,
    "role": 40,
    "model": 160,
    "adapter": 80,
    "provider": 80,
    "tool": 120,
    "kind": 80,
}


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


def _activity_data(source: dict[str, Any]) -> dict[str, Any]:
    data: dict[str, Any] = {}
    for key, limit in _ACTIVITY_TEXT_LIMITS.items():
        value = _bounded_text(source.get(key), limit)
        if value is not None:
            data[key] = value
    exit_code = source.get("exit_code")
    if isinstance(exit_code, int):
        data["exit_code"] = exit_code
    paths = source.get("paths")
    if isinstance(paths, list):
        safe_paths = [str(path)[:240] for path in paths[:12] if path is not None]
        if safe_paths:
            data["paths"] = safe_paths
    return data


def _developer_message(event_type: str, data: dict[str, Any], default: str) -> str:
    if event_type in {"developer_message", "developer_error"} and data.get("text"):
        return str(data["text"])
    if event_type == "developer_command_started":
        if data.get("command"):
            return f"$ {data['command']}"[:1200]
        if data.get("tool"):
            return f"{data['tool']} started"[:1200]
    if event_type == "developer_command_completed":
        if data.get("command"):
            code = data.get("exit_code")
            suffix = f" · exit {code}" if isinstance(code, int) else ""
            return f"$ {data['command']}{suffix}"[:1200]
        if data.get("tool"):
            return f"{data['tool']} · {data.get('status') or 'completed'}"[:1200]
    if event_type == "developer_file_activity" and data.get("paths"):
        return "Files changed: " + ", ".join(data["paths"][:6])
    if event_type == "developer_step":
        provider = data.get("provider")
        model = data.get("model")
        state = data.get("status")
        identity = " · ".join(str(item) for item in (provider, model) if item)
        detail = f"{identity} · {state}" if identity and state else identity or state
        return str(detail or default)[:1200]
    return default


def public_event(row: dict[str, Any]) -> dict[str, Any] | None:
    """Return the dashboard contract from fixed definitions and allow-listed data."""

    event_type = str(row.get("event_type") or "")
    if event_type not in _EVENT_DEFINITIONS:
        return None
    phase, level, message = _definition(event_type)
    source = row.get("data") if isinstance(row.get("data"), dict) else {}
    data: dict[str, Any] = {}
    if event_type in _ACTIVITY_EVENT_TYPES:
        data = _activity_data(source)
        if event_type in _DEVELOPER_EVENT_TYPES:
            message = _developer_message(event_type, data, message)
            if event_type == "developer_command_completed":
                code = data.get("exit_code")
                status = str(data.get("status") or "").lower()
                if (isinstance(code, int) and code != 0) or status in {"failed", "error"}:
                    level = "error"
        else:
            row_phase = str(row.get("phase") or "")
            row_level = str(row.get("level") or "")
            row_message = _bounded_text(row.get("message"), 2000)
            if row_phase in _SAFE_PHASES:
                phase = row_phase
            if row_level in _SAFE_LEVELS:
                level = row_level
            if row_message:
                message = row_message
    else:
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
