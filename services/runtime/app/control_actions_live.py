from __future__ import annotations

from typing import Any

from .control_actions import (
    ControlActionService as BaseControlActionService,
    _BUDGET_EXTENSION_SPECS,
    _BUDGET_FAILURE_MAP,
)


_BUDGET_BLOCK_REASONS = {
    "planner_budget_exhausted",
    "preflight_budget_exhausted",
    "execution_budget_exhausted",
}
_WALL_TIME_RECOVERY_THRESHOLD_MINUTES = 1.0


class ControlActionService(BaseControlActionService):
    """Control actions with live budget-dimension recovery validation.

    Durable ``last_failure`` is useful historical context, but an owner action
    must be authorized from the current effective budget and current durable
    progress. This prevents an older model-call failure from producing (or
    executing) a model-call extension after the job has already received that
    extension and is now constrained by wall time instead.
    """

    @staticmethod
    def _numeric(value: Any) -> float | None:
        if isinstance(value, bool):
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    @classmethod
    def _live_budget_dimension(cls, job: dict[str, Any], last_failure: str) -> str | None:
        route = dict(job.get("route") or {})
        strategy = dict(route.get("strategy") or {})
        budget = dict(strategy.get("budget") or {})
        progress = dict(job.get("progress") or {})
        hint = _BUDGET_FAILURE_MAP.get(str(last_failure or ""))

        exhausted: list[str] = []
        for dimension, spec in _BUDGET_EXTENSION_SPECS.items():
            if dimension not in budget:
                continue
            used = cls._numeric(progress.get(spec["counter"], 0))
            limit = cls._numeric(budget.get(dimension))
            if used is None or limit is None:
                continue
            if used >= limit:
                exhausted.append(dimension)

        if len(exhausted) == 1:
            return exhausted[0]
        if len(exhausted) > 1:
            # Historical failure may disambiguate only when live counters confirm
            # that the hinted dimension is also currently exhausted. Otherwise
            # multiple exhausted dimensions are intentionally fail-closed.
            return hint if hint in exhausted else None

        # Wall time needs usable headroom for another model/tool invocation. A
        # blocked job with <=1 minute left is effectively unrunnable even when
        # persisted elapsed time has not crossed the exact numeric ceiling yet.
        wall_spec = _BUDGET_EXTENSION_SPECS["max_wall_time_minutes"]
        wall_used = cls._numeric(progress.get(wall_spec["counter"], 0))
        wall_limit = cls._numeric(budget.get("max_wall_time_minutes"))
        if wall_used is not None and wall_limit is not None:
            remaining = wall_limit - wall_used
            if 0 <= remaining <= _WALL_TIME_RECOVERY_THRESHOLD_MINUTES:
                return "max_wall_time_minutes"

        # A stale historical hint alone is never sufficient authorization.
        return None

    def blocked_advisory(self, work_order: dict[str, Any], job: dict[str, Any] | None) -> dict[str, Any]:
        advisory = super().blocked_advisory(work_order, job)
        current_job = dict(job or {})
        result = dict(current_job.get("result") or {})
        reason = str(result.get("reason") or "")
        if reason not in _BUDGET_BLOCK_REASONS:
            return advisory

        last_failure = str(result.get("last_failure") or "")
        dimension = self._live_budget_dimension(current_job, last_failure)

        # Never leave a budget button selected solely from stale last_failure.
        advisory["action_specs"] = [
            item
            for item in advisory.get("action_specs") or []
            if str(item.get("action_type") or "") != "budget_extend"
        ]

        if dimension is None:
            advisory["cause"] = (
                "Runtime reported budget exhaustion, but current live counters do not identify "
                "one safe extension dimension. Historical failure text is not sufficient authorization."
            )
            advisory["recommended"] = (
                "Keep the WorkOrder blocked and inspect the current Runtime budget state before extending anything."
            )
            return advisory

        spec = _BUDGET_EXTENSION_SPECS[dimension]
        metric = self._budget_metric(current_job, dimension)
        if metric and not any(
            isinstance(item, dict) and item.get("key") == dimension
            for item in advisory.get("metrics") or []
        ):
            advisory.setdefault("metrics", []).insert(0, metric)

        advisory["cause"] = (
            f"Live Runtime counters identify {spec['label']} as the current exhausted or effectively exhausted budget dimension."
        )
        advisory["recommended"] = (
            f"Approve a bounded +{spec['increment']} extension only if the existing WorkOrder still needs more work."
        )
        advisory.setdefault("action_specs", []).insert(
            0,
            {
                "action_type": "budget_extend",
                "label": f"➕ +{spec['increment']} {spec['label']}",
                "payload": {"dimension": dimension, "increment": spec["increment"]},
            },
        )
        return advisory

    def _apply_budget_extension(self, action: dict[str, Any]) -> dict[str, Any]:
        job_id = str(action.get("job_id") or "")
        if not job_id:
            raise RuntimeError("Budget extension requires a Runtime job")
        job = self.storage.get(job_id)
        if not job:
            raise RuntimeError("Unknown job")

        result = dict(job.get("result") or {})
        reason = str(result.get("reason") or "")
        if reason not in _BUDGET_BLOCK_REASONS:
            raise RuntimeError("Budget extension no longer matches a budget-exhausted Runtime state")

        payload = dict(action.get("payload") or {})
        requested = str(payload.get("dimension") or "")
        current = self._live_budget_dimension(job, str(result.get("last_failure") or ""))
        if not current or current != requested:
            raise RuntimeError("Budget extension is stale or does not match the current live exhausted dimension")

        return super()._apply_budget_extension(action)


__all__ = ["ControlActionService"]
