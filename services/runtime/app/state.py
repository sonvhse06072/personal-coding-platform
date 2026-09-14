from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any


_ANTIGRAVITY_LEGACY_QUOTA_GROUPS = {
    "antigravity_free": "antigravity_gemini",
}
_ANTIGRAVITY_QUOTA_FAILURES = {"quota_exhausted", "rate_limited"}


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
    if isinstance(legacy, dict) and "estimated_files" not in legacy:
        checkpoint.setdefault("hints", deepcopy(legacy.get("hints") or {}))
        checkpoint.setdefault("provider_state", deepcopy(legacy.get("provider_state") or {}))
    checkpoint.setdefault("hints", {})
    checkpoint.setdefault("provider_state", {})
    checkpoint.setdefault("route_history", [])
    checkpoint.setdefault("approved_decisions", [])
    return checkpoint


def clear_transient_provider_failures(checkpoint: dict[str, Any]) -> dict[str, Any]:
    """Clear provider/quota health after explicit operator recovery assertion.

    Direct model-scoped failures such as `no_effect` remain excluded. Provider
    health and quota-bucket health are transient external resource state, so an
    explicit quota reset/credential repair may clear those markers without ever
    resetting Runtime job usage counters.
    """
    updated = deepcopy(checkpoint)
    state = dict(updated.get("provider_state") or {})
    updated["provider_state"] = {
        key: value
        for key, value in state.items()
        if not str(key).startswith(("provider:", "quota:"))
    }
    return updated


def migrate_legacy_antigravity_quota_failure(
    checkpoint: dict[str, Any],
    progress: dict[str, Any] | None,
) -> dict[str, Any]:
    """Narrow old provider-wide Antigravity quota state to its quota bucket.

    Runtime versions before model-aware Antigravity routing marked quota
    exhaustion as `provider:google_antigravity` unavailable. During a preserved
    same-job reroute, narrow only a proven quota/rate-limit marker so other
    Antigravity quota groups remain eligible. Auth/bridge/provider failures remain
    provider-wide and are deliberately not migrated.
    """
    updated = deepcopy(checkpoint)
    state = dict(updated.get("provider_state") or {})
    provider_key = "provider:google_antigravity"
    provider_marker = state.get(provider_key)
    if not isinstance(provider_marker, dict):
        return updated

    failures = list((progress or {}).get("provider_failures") or [])
    failure: dict[str, Any] | None = None
    for item in reversed(failures):
        if not isinstance(item, dict):
            continue
        if str(item.get("provider") or "") != "google_antigravity":
            continue
        if str(item.get("kind") or "") not in _ANTIGRAVITY_QUOTA_FAILURES:
            continue
        failure = item
        break
    if failure is None:
        return updated

    model_id = str(failure.get("model") or "").strip()
    if not model_id:
        return updated
    quota_group = _ANTIGRAVITY_LEGACY_QUOTA_GROUPS.get(model_id, model_id)
    quota_key = f"quota:{quota_group}"
    quota_marker = dict(state.get(quota_key) or {})
    quota_marker.update(deepcopy(provider_marker))
    quota_marker.update({"healthy": False, "available": False, "quota_pressure": 1.0})
    state[quota_key] = quota_marker
    state.pop(provider_key, None)
    updated["provider_state"] = state
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
