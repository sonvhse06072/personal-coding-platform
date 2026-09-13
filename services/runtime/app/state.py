from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any


def merge_progress(defaults: dict[str, Any], existing: dict[str, Any] | None) -> dict[str, Any]:
    progress = deepcopy(defaults)
    if existing:
        progress.update(deepcopy(existing))
    return progress


def decision_key(decision: dict[str, Any] | None) -> str:
    if not decision:
        return ""
    triggers = sorted(str(item) for item in (decision.get("triggers") or []) if str(item))
    if triggers:
        return "|".join(triggers)
    reason = str(decision.get("reason") or "").strip()
    return reason[:500]


def checkpoint_from_row(row: dict[str, Any]) -> dict[str, Any]:
    """Load the durable checkpoint and migrate the pre-v1.0.11 bootstrap shape."""
    checkpoint = deepcopy(row.get("checkpoint") or {})
    legacy = row.get("repo_analysis") or {}
    # Before checkpoints existed, the first queued row temporarily stored hints
    # and provider state in repo_analysis. Preserve compatibility with such jobs.
    if isinstance(legacy, dict) and "estimated_files" not in legacy:
        checkpoint.setdefault("hints", deepcopy(legacy.get("hints") or {}))
        checkpoint.setdefault("provider_state", deepcopy(legacy.get("provider_state") or {}))
    checkpoint.setdefault("hints", {})
    checkpoint.setdefault("provider_state", {})
    checkpoint.setdefault("route_history", [])
    checkpoint.setdefault("approved_decisions", [])
    return checkpoint


def clear_transient_provider_failures(checkpoint: dict[str, Any]) -> dict[str, Any]:
    """Clear provider-pool health failures after explicit operator intervention.

    Model-scoped failures such as `no_effect` remain excluded; only provider-level
    resource/auth/quota health is reset. Job budget counters are never reset.
    """
    updated = deepcopy(checkpoint)
    state = dict(updated.get("provider_state") or {})
    updated["provider_state"] = {
        key: value for key, value in state.items() if not str(key).startswith("provider:")
    }
    return updated


def clear_routing_choices_for_resume(checkpoint: dict[str, Any]) -> dict[str, Any]:
    """Drop only stale route-derived choices before an explicit reroute.

    WorkOrder/baseline snapshots, plan text, progress counters, approved decisions
    and route history remain durable. The prior block result remains on the job
    until the resumed run records its next terminal result.
    """
    updated = deepcopy(checkpoint)
    for key in ("planner_choice", "executor_choice", "evaluator_choice", "last_failure"):
        updated.pop(key, None)
    return updated


def existing_repo_analysis(row: dict[str, Any]) -> dict[str, Any] | None:
    value = row.get("repo_analysis")
    if not isinstance(value, dict) or "estimated_files" not in value:
        return None
    return deepcopy(value)


def validate_workspace(root: Path, job_id: str, workspace: str | Path) -> Path:
    root = root.resolve()
    path = Path(workspace).resolve()
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise RuntimeError("Persisted workspace is outside CODING_WORKSPACES_ROOT") from exc
    if path.parent != root or path.name != job_id:
        raise RuntimeError("Persisted workspace does not match the job id")
    if not path.is_dir() or not (path / ".git").is_dir():
        raise RuntimeError("Persisted workspace is missing or is not a self-contained Git clone")
    return path
