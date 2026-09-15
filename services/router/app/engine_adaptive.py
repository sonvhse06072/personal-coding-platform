from __future__ import annotations

import math

from .engine_budget import RouterEngine as BudgetRouterEngine
from .schemas import (
    AdaptiveBudgetDimension,
    AdaptiveBudgetPolicy,
    ReassessRequest,
    ReassessResponse,
    RoutingRequest,
    RoutingResponse,
)


_ELASTIC_COUNTERS = {
    "max_model_calls": "model_calls",
    "max_iterations": "iteration",
    "max_repair_iterations": "repair_iterations",
    "max_test_runs": "test_runs",
    "max_wall_time_minutes": "elapsed_minutes",
}


class RouterEngine(BudgetRouterEngine):
    """Attach task-specific adaptive execution envelopes to newly routed work.

    Legacy persisted routes omit ``adaptive_budget`` and keep the historical
    max_* hard-stop semantics. New routes preserve non-blocking estimate/working
    metadata while configured max_* fields become deterministic emergency
    ceilings, so existing Runtime pre-call guards continue to fail closed.
    """

    @staticmethod
    def _effort_pressure(route: RoutingResponse) -> float:
        d = route.dimensions
        weighted = (
            d.scope * 0.18
            + d.ambiguity * 0.12
            + d.verification_difficulty * 0.22
            + d.risk * 0.10
            + d.context_requirement * 0.14
            + d.novelty * 0.08
            + d.reasoning_requirement * 0.16
        )
        return max(0.0, min(1.0, weighted / 100.0))

    def _adaptive_policy(self, route: RoutingResponse) -> AdaptiveBudgetPolicy | None:
        cfg = dict(self.policy.get("adaptive_budget") or {})
        if not bool(cfg.get("enabled", False)):
            return None

        dimensions_cfg = dict(cfg.get("dimensions") or {})
        if not dimensions_cfg:
            return None

        pressure = self._effort_pressure(route)
        min_ratio = float(cfg.get("estimate_min_ratio", 0.65))
        max_ratio = float(cfg.get("estimate_max_ratio", 1.35))
        working_ratio = float(cfg.get("working_headroom_ratio", 1.25))
        emergency_ratio = float(cfg.get("emergency_multiplier", 1.5))
        estimate_ratio = min_ratio + (max_ratio - min_ratio) * pressure

        budget = route.strategy.budget.model_copy(deep=True)
        dimensions: dict[str, AdaptiveBudgetDimension] = {}

        for dimension, spec_value in dimensions_cfg.items():
            if dimension not in _ELASTIC_COUNTERS or not hasattr(budget, dimension):
                continue
            spec = dict(spec_value or {})
            baseline = float(getattr(budget, dimension))
            hard_cap = max(baseline, float(spec.get("hard_max", baseline)))
            minimum = float(spec.get("minimum", 1.0))

            estimate = max(minimum, math.ceil(baseline * estimate_ratio))
            working_target = min(
                hard_cap,
                max(baseline, math.ceil(estimate * working_ratio)),
            )
            emergency_limit = min(
                hard_cap,
                max(working_target, math.ceil(working_target * emergency_ratio)),
            )

            # Current Budget fields are integral, including wall-time minutes.
            estimate = float(int(estimate))
            working_target = float(int(working_target))
            emergency_limit = float(int(emergency_limit))

            setattr(budget, dimension, int(emergency_limit))
            dimensions[dimension] = AdaptiveBudgetDimension(
                estimate=estimate,
                working_target=working_target,
                emergency_limit=emergency_limit,
            )

        if not dimensions:
            return None

        route.strategy.budget = budget
        return AdaptiveBudgetPolicy(
            enabled=True,
            effort_pressure=round(pressure, 4),
            dimensions=dimensions,
        )

    def route(self, request: RoutingRequest) -> RoutingResponse:
        result = super().route(request)
        adaptive = self._adaptive_policy(result)
        if adaptive is None:
            return result
        result.strategy.adaptive_budget = adaptive
        result.strategy.reasons = list(result.strategy.reasons) + [
            "Adaptive personal-scale budget enabled: estimates and working targets are non-blocking; configured max_* values are emergency ceilings."
        ]
        return result

    @staticmethod
    def _adaptive_signals(request: ReassessRequest) -> list[str]:
        adaptive = request.route.strategy.adaptive_budget
        if adaptive is None or not adaptive.enabled:
            return []

        signals: list[str] = []
        for dimension, envelope in adaptive.dimensions.items():
            counter = _ELASTIC_COUNTERS.get(dimension)
            if not counter:
                continue
            used = float(getattr(request.progress, counter, 0.0))
            if used >= envelope.working_target and used < envelope.emergency_limit:
                signals.append(f"budget_headroom_active:{dimension}")
            elif used >= envelope.estimate and used < envelope.working_target:
                signals.append(f"budget_estimate_exceeded:{dimension}")
        return signals

    def reassess(self, request: ReassessRequest) -> ReassessResponse:
        result = super().reassess(request)
        extra = self._adaptive_signals(request)
        if not extra:
            return result
        signals = list(result.signals)
        for signal in extra:
            if signal not in signals:
                signals.append(signal)
        return result.model_copy(update={"signals": signals})
