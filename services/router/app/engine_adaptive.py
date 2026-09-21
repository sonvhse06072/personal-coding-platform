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
    "max_input_tokens": "input_tokens",
    "max_output_tokens": "output_tokens",
    "max_tool_calls": "tool_calls",
    "max_iterations": "iteration",
    "max_repair_iterations": "repair_iterations",
    "max_test_runs": "test_runs",
    "max_wall_time_minutes": "elapsed_minutes",
}


class RouterEngine(BudgetRouterEngine):
    """Attach task-specific estimates and pre-authorized healthy-progress headroom.

    Profile values are planning priors, not routine stop points. Router derives an
    estimate and working target from task pressure while the effective max_* fields
    are high-water telemetry thresholds. Cumulative input/output token totals,
    calls/iterations/repairs/tests/tools and total wall time remain telemetry and
    reassessment inputs on effective adaptive WorkOrders. Hard monetary cost,
    provider quota/context enforcement and independent anomaly/protected-decision
    signals remain fail-closed.

    Historical telemetry may adjust estimates only after the configured minimum
    sample size. It can never expand the configured emergency hard caps.

    Legacy persisted routes omit ``adaptive_budget`` and keep historical hard-stop
    semantics until the explicit compatibility recovery proves a fresh adaptive
    route healthy.
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

    def _calibration_multipliers(self, request: RoutingRequest) -> dict[str, float]:
        observed = request.calibration
        if observed is None:
            return {}
        cfg = dict(self.policy.get("telemetry_calibration") or {})
        policy_minimum = int(cfg.get("minimum_sample_size", 5))
        required = max(policy_minimum, int(observed.minimum_sample_size))
        if int(observed.sample_size) < required:
            return {}
        lower = float(cfg.get("multiplier_min", 0.75))
        upper = float(cfg.get("multiplier_max", 1.75))
        if upper < lower:
            lower, upper = upper, lower
        result: dict[str, float] = {}
        for dimension, raw in observed.resource_multipliers.items():
            if dimension not in _ELASTIC_COUNTERS:
                continue
            try:
                value = float(raw)
            except (TypeError, ValueError):
                continue
            if value <= 0:
                continue
            result[dimension] = max(lower, min(upper, value))
        return result

    def _adaptive_policy(
        self,
        route: RoutingResponse,
        request: RoutingRequest,
    ) -> AdaptiveBudgetPolicy | None:
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
        estimate_ratio = min_ratio + (max_ratio - min_ratio) * pressure
        calibration = self._calibration_multipliers(request)

        budget = route.strategy.budget.model_copy(deep=True)
        dimensions: dict[str, AdaptiveBudgetDimension] = {}

        for dimension, spec_value in dimensions_cfg.items():
            if dimension not in _ELASTIC_COUNTERS or not hasattr(budget, dimension):
                continue
            spec = dict(spec_value or {})
            baseline = float(getattr(budget, dimension))
            hard_cap = float(spec.get("hard_max", baseline))
            if baseline > hard_cap:
                raise RuntimeError(
                    f"Adaptive budget profile prior {dimension}={baseline:g} exceeds configured hard_max={hard_cap:g}"
                )
            minimum = float(spec.get("minimum", 1.0))
            historical_multiplier = float(calibration.get(dimension, 1.0))

            estimate = min(
                hard_cap,
                max(minimum, math.ceil(baseline * estimate_ratio * historical_multiplier)),
            )
            working_target = min(
                hard_cap,
                max(baseline, math.ceil(estimate * working_ratio)),
            )

            # Keep a stable high-water threshold for telemetry/calibration.
            # Effective adaptive WorkOrder policy decides whether the dimension
            # is a material stop or a non-blocking work-shape counter.
            emergency_limit = hard_cap

            # Budget fields are integral, including wall-time minutes.
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
        multipliers = self._calibration_multipliers(request)
        adaptive = self._adaptive_policy(result, request)
        if adaptive is None:
            return result
        result.strategy.adaptive_budget = adaptive
        reasons = list(result.strategy.reasons) + [
            "Healthy-progress budget policy enabled: profile/default and work-shape emergency thresholds are non-blocking on effective adaptive WorkOrders; material resource ceilings remain circuit breakers."
        ]
        if multipliers and request.calibration is not None:
            reasons.append(
                f"Observed project/task/role calibration applied from {request.calibration.sample_size} comparable terminal jobs; material circuit breakers remain authoritative."
            )
        result.strategy.reasons = reasons
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
            if used >= envelope.emergency_limit:
                signals.append(f"budget_emergency_threshold_reached:{dimension}")
            elif used >= envelope.working_target:
                signals.append(f"budget_headroom_active:{dimension}")
            elif used >= envelope.estimate:
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
