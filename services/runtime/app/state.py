from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

from .config import models_doc


_QUOTA_FAILURES = {"quota_exhausted", "rate_limited"}
_ANTIGRAVITY_PROVIDER = "google_antigravity"
_FAILURE_CONTEXT_VERSION = 1
_SEMANTIC_FAILURE_SOURCES = {"reviewer", "pm_reassessment", "human_rejection"}


def set_failure_context(
    checkpoint: dict[str, Any],
    *,
    kind: str,
    source: str,
    message: str,
    diff_hash: str | None = None,
    decision_key_value: str | None = None,
) -> str:
    """Persist typed failure provenance alongside the legacy prompt text."""
    if kind not in {"semantic_repair", "route_transient"}:
        raise ValueError(f"Unsupported failure context kind: {kind}")
    normalized = str(message or "")[-30000:]
    checkpoint["last_failure"] = normalized or None
    if not normalized:
        checkpoint.pop("failure_context", None)
        return normalized
    context: dict[str, Any] = {
        "version": _FAILURE_CONTEXT_VERSION,
        "kind": kind,
        "source": str(source or "")[:80],
        "message": normalized,
    }
    if diff_hash:
        context["diff_hash"] = str(diff_hash)[:200]
    if decision_key_value:
        context["decision_key"] = str(decision_key_value)[:500]
    checkpoint["failure_context"] = context
    return normalized


def clear_failure_context(checkpoint: dict[str, Any]) -> None:
    checkpoint["last_failure"] = None
    checkpoint.pop("failure_context", None)


def _legacy_semantic_failure_context(checkpoint: dict[str, Any]) -> dict[str, Any] | None:
    message = str(checkpoint.get("last_failure") or "")
    if not message:
        return None
    if message.startswith("PCP_REVIEW_FINDINGS:"):
        pending = checkpoint.get("pending_review_findings")
        if isinstance(pending, dict) and pending.get("diff_hash"):
            return {
                "version": _FAILURE_CONTEXT_VERSION,
                "kind": "semantic_repair",
                "source": "reviewer",
                "message": message,
                "diff_hash": str(pending["diff_hash"])[:200],
            }
    if message.startswith("PCP_PM_REASSESSMENT:"):
        pm = checkpoint.get("last_pm_reassessment")
        if isinstance(pm, dict) and pm.get("diff_hash"):
            decision = dict(pm.get("decision") or {})
            if str(decision.get("action") or "") in {"request_repair", "request_developer_response"}:
                return {
                    "version": _FAILURE_CONTEXT_VERSION,
                    "kind": "semantic_repair",
                    "source": "pm_reassessment",
                    "message": message,
                    "diff_hash": str(pm["diff_hash"])[:200],
                }
    if message.startswith("PCP_HUMAN_DECISION_REJECTED:"):
        history = [
            dict(item)
            for item in (checkpoint.get("decision_history") or [])
            if isinstance(item, dict)
        ]
        rejected = next(
            (item for item in reversed(history) if item.get("action") == "reject" and item.get("key")),
            None,
        )
        if rejected:
            context = {
                "version": _FAILURE_CONTEXT_VERSION,
                "kind": "semantic_repair",
                "source": "human_rejection",
                "message": message,
                "decision_key": str(rejected["key"])[:500],
            }
            boundary = checkpoint.get("pending_pm_reassessment")
            if isinstance(boundary, dict) and boundary.get("diff_hash"):
                context["diff_hash"] = str(boundary["diff_hash"])[:200]
            return context
    return None


def _semantic_failure_context_is_current(
    checkpoint: dict[str, Any],
    context: dict[str, Any],
) -> bool:
    if context.get("kind") != "semantic_repair":
        return False
    source = str(context.get("source") or "")
    if source not in _SEMANTIC_FAILURE_SOURCES:
        return False
    message = str(context.get("message") or "")
    if not message or message != str(checkpoint.get("last_failure") or ""):
        return False

    diff_hash = str(context.get("diff_hash") or "")
    if source == "reviewer":
        pending = checkpoint.get("pending_review_findings")
        return bool(
            diff_hash
            and isinstance(pending, dict)
            and str(pending.get("diff_hash") or "") == diff_hash
        )
    if source == "pm_reassessment":
        pm = checkpoint.get("last_pm_reassessment")
        decision = dict((pm or {}).get("decision") or {}) if isinstance(pm, dict) else {}
        return bool(
            diff_hash
            and isinstance(pm, dict)
            and str(pm.get("diff_hash") or "") == diff_hash
            and str(decision.get("action") or "") in {"request_repair", "request_developer_response"}
        )
    if source == "human_rejection":
        key = str(context.get("decision_key") or "")
        history = [
            dict(item)
            for item in (checkpoint.get("decision_history") or [])
            if isinstance(item, dict)
        ]
        latest = next((item for item in reversed(history) if str(item.get("key") or "") == key), None)
        if not key or not latest or latest.get("action") != "reject":
            return False
        if diff_hash:
            boundary = checkpoint.get("pending_pm_reassessment")
            return bool(
                isinstance(boundary, dict)
                and str(boundary.get("diff_hash") or "") == diff_hash
            )
        return True
    return False



def _iso_timestamp(value: Any) -> str | None:
    if value is None:
        return None
    if hasattr(value, "isoformat"):
        try:
            return str(value.isoformat())
        except Exception:
            return None
    text = str(value).strip()
    return text or None


def quota_failure_state_key(choice: dict[str, Any]) -> str:
    """Return the narrow durable quota key for one failed routed choice."""
    model_id = str(choice.get("id") or "").strip()
    provider = str(choice.get("provider") or "").strip()
    quota_group = str(choice.get("quota_group") or "").strip()

    # Antigravity's direct model failure is not proof that its whole shared
    # family is exhausted; authoritative telemetry may separately mark a group.
    if provider == _ANTIGRAVITY_PROVIDER and model_id:
        return f"quota:model:{model_id}"
    if quota_group:
        return f"quota:{quota_group}"
    if model_id:
        return f"quota:model:{model_id}"
    return f"provider:{provider}"


def provider_failure_state_key(choice: dict[str, Any], kind: str) -> str:
    if str(kind or "") in _QUOTA_FAILURES:
        return quota_failure_state_key(choice)
    return f"provider:{str(choice.get('provider') or '').strip()}"


def migrate_legacy_provider_quota_failure(
    checkpoint: dict[str, Any],
    progress: dict[str, Any] | None,
    *,
    failed_at: Any = None,
) -> dict[str, Any]:
    """Narrow proven pre-fix provider-wide quota markers without clearing them.

    Only the latest observed failure for a provider is considered. A later
    authentication/config/provider failure therefore prevents quota migration.
    """
    updated = deepcopy(checkpoint)
    state = dict(updated.get("provider_state") or {})
    failures = [
        dict(item)
        for item in ((progress or {}).get("provider_failures") or [])
        if isinstance(item, dict)
    ]
    if not failures:
        return updated

    models = models_doc().get("models", {}) or {}
    by_provider: dict[str, dict[str, Any]] = {}
    for item in reversed(failures):
        provider = str(item.get("provider") or "").strip()
        if provider and provider not in by_provider:
            by_provider[provider] = item

    changed = False
    for provider, failure in by_provider.items():
        provider_key = f"provider:{provider}"
        marker = state.get(provider_key)
        if not isinstance(marker, dict):
            continue
        kind = str(failure.get("kind") or "")
        if kind not in _QUOTA_FAILURES:
            continue
        model_id = str(failure.get("model") or "").strip()
        if not model_id:
            continue
        cfg = dict(models.get(model_id) or {})
        choice = {
            "id": model_id,
            "provider": provider,
            "quota_group": cfg.get("quota_group"),
        }
        quota_key = quota_failure_state_key(choice)
        quota_marker = dict(state.get(quota_key) or {})
        quota_marker.update(deepcopy(marker))
        quota_marker.update({
            "healthy": False,
            "available": False,
            "quota_pressure": 1.0,
            "error_rate": 1.0,
            "failure_kind": kind,
        })
        failure_time = _iso_timestamp(failed_at)
        if failure_time and not quota_marker.get("failed_at"):
            quota_marker["failed_at"] = failure_time
        state[quota_key] = quota_marker
        state.pop(provider_key, None)
        changed = True

    if changed:
        updated["provider_state"] = state
    return updated

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
    if not isinstance(checkpoint.get("failure_context"), dict):
        migrated = _legacy_semantic_failure_context(checkpoint)
        if migrated:
            checkpoint["failure_context"] = migrated
    return checkpoint


def clear_transient_provider_failures(checkpoint: dict[str, Any]) -> dict[str, Any]:
    """Clear provider/quota health after explicit operator recovery assertion.

    Direct deterministic model failures such as `no_effect` remain excluded.
    Provider and quota state are transient external resource state, so an explicit
    reset/credential-repair assertion may clear those markers without resetting
    Runtime usage counters, workspace or diff.
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
    """Backward-compatible wrapper for the generic provider quota migration."""
    return migrate_legacy_provider_quota_failure(checkpoint, progress)


def clear_routing_choices_for_resume(checkpoint: dict[str, Any]) -> dict[str, Any]:
    """Drop only stale route-derived choices before an explicit reroute.

    WorkOrder/baseline snapshots, plan text, progress counters, approved decisions
    and route history remain durable. The prior block result remains on the job
    until the resumed run records its next terminal result.
    """
    updated = deepcopy(checkpoint)
    for key in ("planner_choice", "executor_choice", "evaluator_choice"):
        updated.pop(key, None)
    context = dict(updated.get("failure_context") or {})
    if _semantic_failure_context_is_current(updated, context):
        updated["last_failure"] = str(context["message"])
    else:
        updated.pop("last_failure", None)
        updated.pop("failure_context", None)
    return updated


def existing_repo_analysis(row: dict[str, Any]) -> dict[str, Any] | None:
    value = row.get("repo_analysis")
    if not isinstance(value, dict) or "estimated_files" not in value:
        return None
    return deepcopy(value)


def validate_workspace(
    root: Path,
    job_id: str,
    workspace: str | Path,
    *,
    workspace_mode: str = "isolated_clone",
    project_path: str | Path | None = None,
) -> Path:
    path = Path(workspace).resolve()
    if workspace_mode == "direct":
        if project_path is None:
            raise RuntimeError("Direct workspace validation requires the configured project path")
        configured = Path(project_path).resolve()
        if path != configured:
            raise RuntimeError("Persisted direct workspace does not match the configured project path")
        if not path.is_dir() or not (path / ".git").exists():
            raise RuntimeError("Persisted direct workspace is missing or is not a Git repository")
        return path
    if workspace_mode != "isolated_clone":
        raise RuntimeError(f"Unsupported persisted workspace mode: {workspace_mode}")

    root = root.resolve()
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise RuntimeError("Persisted workspace is outside CODING_WORKSPACES_ROOT") from exc
    if path.parent != root or path.name != job_id:
        raise RuntimeError("Persisted workspace does not match the job id")
    if not path.is_dir() or not (path / ".git").is_dir():
        raise RuntimeError("Persisted workspace is missing or is not a self-contained Git clone")
    return path
