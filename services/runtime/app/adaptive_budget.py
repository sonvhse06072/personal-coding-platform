from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .developer_stream import runtime_activity_event


_COUNTERS = {
    "max_model_calls": "model_calls",
    "max_tool_calls": "tool_calls",
    "max_iterations": "iteration",
    "max_repair_iterations": "repair_iterations",
    "max_test_runs": "test_runs",
    "max_wall_time_minutes": "elapsed_minutes",
}


def adaptive_enabled(route: dict[str, Any] | None) -> bool:
    strategy = dict((route or {}).get("strategy") or {})
    adaptive = dict(strategy.get("adaptive_budget") or {})
    return bool(adaptive.get("enabled", False)) and bool(adaptive.get("dimensions"))


def _number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def apply_adaptive_budget_grants(
    engine: Any,
    *,
    job_id: str,
    route: dict[str, Any],
    progress: dict[str, Any],
    checkpoint: dict[str, Any],
    reassess: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    """Validate and durably apply Router-proposed same-job headroom grants.

    Router suggestions are treated as untrusted input at the Runtime boundary.
    A grant is accepted only when it exactly matches the current effective limit,
    live counter and persisted adaptive emergency ceiling. Invalid/stale grants
    are ignored fail-closed and never widen execution authority.
    """

    if not adaptive_enabled(route) or not isinstance(reassess, dict):
        return []

    proposals = reassess.get("adaptive_budget_grants")
    if not isinstance(proposals, list) or not proposals:
        return []

    strategy = route.get("strategy") or {}
    budget = strategy.get("budget") or {}
    adaptive = strategy.get("adaptive_budget") or {}
    dimensions = adaptive.get("dimensions") or {}
    accepted: list[dict[str, Any]] = []

    for raw in proposals:
        if not isinstance(raw, dict):
            continue
        dimension = str(raw.get("dimension") or "")
        counter = _COUNTERS.get(dimension)
        envelope = dimensions.get(dimension)
        if not counter or not isinstance(envelope, dict) or dimension not in budget:
            continue

        current = _number(budget.get(dimension))
        previous = _number(raw.get("previous_limit"))
        new_limit = _number(raw.get("new_limit"))
        response_emergency = _number(raw.get("emergency_limit"))
        route_emergency = _number(envelope.get("emergency_limit"))
        response_used = _number(raw.get("used"))
        live_used = _number(progress.get(counter, 0))
        projected = _number(raw.get("projected"))
        if None in {
            current,
            previous,
            new_limit,
            response_emergency,
            route_emergency,
            response_used,
            live_used,
            projected,
        }:
            continue
        assert current is not None
        assert previous is not None
        assert new_limit is not None
        assert response_emergency is not None
        assert route_emergency is not None
        assert response_used is not None
        assert live_used is not None
        assert projected is not None

        if abs(current - previous) > 1e-6:
            continue
        if abs(response_emergency - route_emergency) > 1e-6:
            continue
        if abs(response_used - live_used) > 1e-6:
            continue
        if new_limit <= current or new_limit > route_emergency:
            continue
        if projected > route_emergency:
            continue

        normalized = new_limit if dimension == "max_wall_time_minutes" else int(new_limit)
        budget[dimension] = normalized
        record = {
            "dimension": dimension,
            "previous_limit": previous,
            "new_limit": new_limit,
            "emergency_limit": route_emergency,
            "used": live_used,
            "projected": projected,
            "granted_at": datetime.now(timezone.utc).isoformat(),
            "source": "router_healthy_progress",
        }
        accepted.append(record)

    if not accepted:
        return []

    strategy["budget"] = budget
    route["strategy"] = strategy
    history = list(checkpoint.get("adaptive_budget_grants") or [])
    history.extend(accepted)
    checkpoint["adaptive_budget_grants"] = history[-50:]
    engine.storage.update(
        job_id,
        route=route,
        progress=progress,
        checkpoint=checkpoint,
    )

    row = engine.storage.get(job_id) or {}
    workspace = Path(str(row.get("workspace") or "."))
    for grant in accepted:
        engine.storage.append_event(
            job_id,
            runtime_activity_event(
                kind="adaptive_budget_headroom",
                message=(
                    f"Healthy-progress headroom granted: {grant['dimension']} "
                    f"{grant['previous_limit']:g}->{grant['new_limit']:g} "
                    f"(emergency {grant['emergency_limit']:g})"
                ),
                phase="reassessment",
                level="info",
                status=str(grant["dimension"]),
                output={
                    "used": grant["used"],
                    "projected": grant["projected"],
                    "previous_limit": grant["previous_limit"],
                    "new_limit": grant["new_limit"],
                    "emergency_limit": grant["emergency_limit"],
                },
                workspace=workspace,
            ),
        )
    return accepted


async def ensure_adaptive_budget_capacity(
    engine: Any,
    *,
    job_id: str,
    route: dict[str, Any],
    progress: dict[str, Any],
    checkpoint: dict[str, Any],
    provider_state: dict[str, Any],
    requested_headroom: dict[str, float] | None = None,
) -> dict[str, Any] | None:
    """Ask Router for bounded headroom and apply any valid grant durably."""

    if not adaptive_enabled(route):
        return None
    reassess = await engine.router.reassess({
        "route": route,
        "progress": progress,
        "provider_state": provider_state,
        "requested_headroom": requested_headroom or {},
    })
    apply_adaptive_budget_grants(
        engine,
        job_id=job_id,
        route=route,
        progress=progress,
        checkpoint=checkpoint,
        reassess=reassess,
    )
    return reassess


__all__ = [
    "adaptive_enabled",
    "apply_adaptive_budget_grants",
    "ensure_adaptive_budget_capacity",
]
