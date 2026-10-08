"""Redacted, model-call-free reviewer-capacity diagnostics for PCP #562.

A probe uses one authenticated Router *staffing* request, never an adapter or
coding/reviewer model invocation. It cannot alter job, quota allowance, review
attestations or the PM merge gate. Live observations and registry capability
are reported separately.
"""
from __future__ import annotations

import asyncio
from typing import Any

from .config import models_doc
from .model_capabilities import validate_model_choice
from .pm_late_review import _no_eligible_reviewer, registered_review_capacity
from .quota_runtime import quota_coordinator


_UNAVAILABLE = {
    "healthy": False,
    "available": False,
    "quota_pressure": 1.0,
    "error_rate": 1.0,
    "latency_ms": 0,
}


def _marker(markers: Any, key: str) -> str:
    """Return a bounded state code, never raw failure text or quota metadata."""
    value = markers.get(key) if isinstance(markers, dict) else None
    if not isinstance(value, dict):
        return "unknown"
    if value.get("available") is False:
        return "unavailable"
    if value.get("healthy") is False:
        return "unhealthy"
    pressure = value.get("quota_pressure")
    if (
        type(pressure) in (int, float)
        and float(pressure) >= 1.0
    ):
        return "quota_exhausted_or_reserved"
    if value.get("available") is True or value.get("healthy") is True:
        return "not_explicitly_blocked"
    return "unknown"


def _quota_collector(view: dict[str, Any]) -> dict[str, Any]:
    for row in view.get("collectors") or []:
        if not isinstance(row, dict) or row.get("source") != "antigravity_quota":
            continue
        state = str(row.get("status") or "")
        return {
            "status": state if state in {"ok", "no_data", "error"} else "unknown",
            # Collection success is distinct from fresh quota data. Never
            # publish error text, plan metadata or provider token information.
            "has_successful_collection": bool(row.get("last_success_at")),
        }
    return {"status": "missing", "has_successful_collection": False}


def _candidate_markers(
    *,
    registry_ids: list[str],
    persisted_state: dict[str, Any],
    quota_state: dict[str, Any],
) -> list[dict[str, str]]:
    registry = models_doc().get("models") or {}
    rows: list[dict[str, str]] = []
    for model_id in registry_ids[:12]:
        model = registry.get(model_id)
        if not isinstance(model, dict):
            continue
        provider = str(model.get("provider") or "")
        quota_group = str(model.get("quota_group") or "")
        rows.append({
            "model_id": model_id,
            "provider": provider,
            "quota_group": quota_group or "unregistered",
            "job_provider": _marker(persisted_state, f"provider:{provider}"),
            "job_model": _marker(persisted_state, model_id),
            "job_model_quota": _marker(persisted_state, f"quota:model:{model_id}"),
            "job_group_quota": (
                _marker(persisted_state, f"quota:{quota_group}")
                if quota_group else "unknown"
            ),
            "fresh_model_quota": _marker(quota_state, f"quota:model:{model_id}"),
            "fresh_group_quota": (
                _marker(quota_state, f"quota:{quota_group}")
                if quota_group else "unknown"
            ),
        })
    return rows


async def probe_reviewer_capacity(
    *,
    job: dict[str, Any],
    router: Any,
    quota_view: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """At most one read-only staffing request; never infer model-call success."""
    registered = registered_review_capacity(job)
    if registered.get("status") != "registry_evaluated":
        return {
            "status": "provenance_unverifiable",
            "staffing_checked": False,
            "reason": registered.get("reason") or "writer_identity_unverifiable",
        }
    writers = list(registered.get("writer_providers") or [])
    candidates = list(registered.get("cross_provider_registered_model_ids") or [])[:12]
    if not writers or not candidates:
        return {
            "status": "no_registered_cross_provider_candidate",
            "staffing_checked": False,
            "registered_model_ids": candidates,
        }

    if quota_view is None:
        quota_view = quota_coordinator.view()
    if not isinstance(quota_view, dict):
        quota_view = {}
    persisted = dict((job.get("checkpoint") or {}).get("provider_state") or {})
    quota_state = quota_view.get("provider_state") or {}
    result: dict[str, Any] = {
        "status": "not_checked",
        "staffing_checked": False,
        "staffing_is_model_invocation": False,
        "evidence_type": "router_staffing_and_quota_snapshot",
        "quota_is_model_availability_proof": False,
        "antigravity_collector": _quota_collector(quota_view),
        "cross_provider_models": _candidate_markers(
            registry_ids=candidates,
            persisted_state=persisted,
            quota_state=quota_state,
        ),
    }

    state = dict(persisted)
    for writer in writers:
        state[f"provider:{writer}"] = dict(_UNAVAILABLE)
    job_id = str(job.get("id") or "")
    project_id = str(job.get("project_id") or "")
    request_id = "capacity-inspect:" + job_id[:64]
    try:
        # This consults current Router eligibility/quota rules. It cannot
        # consume reviewer model tokens or make any merge decision.
        response = await asyncio.wait_for(
            router.staff({
                "request_id": request_id,
                "project_id": project_id,
                "role": "reviewer",
                "profile": "critical",
                "semantic": dict((job.get("task") or {}).get("semantic") or {}),
                "provider_state": state,
            }),
            timeout=45,
        )
    except Exception as exc:
        result["staffing_checked"] = True
        result["status"] = (
            "no_eligible_cross_provider_now"
            if _no_eligible_reviewer(exc)
            else "staffing_unverifiable"
        )
        # Runtime/HTTP errors are intentionally never projected to GitHub.
        return result

    choice = response.get("choice") if isinstance(response, dict) else None
    choice = dict(choice) if isinstance(choice, dict) else {}
    model_id = str(choice.get("id") or "")
    registry = (models_doc().get("models") or {}).get(model_id)
    try:
        validate_model_choice(choice)
    except (RuntimeError, ValueError):
        registry = None
    if (
        not isinstance(registry, dict)
        or response.get("role") != "reviewer"
        or response.get("request_id") != request_id
        or model_id not in candidates
        or choice.get("provider") in writers
        or choice.get("provider") != registry.get("provider")
        or choice.get("adapter") != registry.get("adapter")
    ):
        result["status"] = "staffing_unverifiable"
        result["staffing_checked"] = True
        return result

    result["status"] = "eligible_cross_provider_at_probe"
    result["staffing_checked"] = True
    result["staffed_model_id"] = model_id
    result["staffed_provider"] = str(choice["provider"])
    # A staffed model might still fail when invoked; this is NOT a review PASS.
    return result
