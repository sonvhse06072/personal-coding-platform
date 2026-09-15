from __future__ import annotations

import math

from .engine_budget import RouterEngine as BudgetRouterEngine
from .schemas import (
    AdaptiveBudgetDimension,
    AdaptiveBudgetGrant,
    AdaptiveBudgetPolicy,
    ReassessRequest,
    ReassessResponse,
    RoutingRequest,
    RoutingResponse,
)


_ELASTIC_COUNTERS = {
    "max_model_calls": "model_calls",
    "max_tool_calls": "tool_calls",
    "max_iterations": "iteration",
    "max_repair_iterations": "repair_iterations",
    "max_test_runs": "test_runs",
    "max_wall_time_minutes": "elapsed_minutes",
}


class RouterEngine(BudgetRouterEngine):
    """Task-specific estimates plus bounded healthy-progress headroom.

    New routes start at a task-specific working target rather than at the
    emergency ceiling. Runtime may ask reassessment for additional headroom when
    a current/projected operation reaches that working limit. The Router first
    evaluates the same progress against the emergency envelope, so existing
    human-decision, scope and anti-loop signals remain authoritative. Only a
    healthy ``continue``/``escalate`` result can carry an automatic grant.

    Legacy persisted routes omit ``adaptive_budget`` and retain historical hard
    max_* semantics exactly.
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
        default_grant_ratio = float(cfg.get("grant_increment_ratio", 0.25))
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
            grant_increment = float(
                spec.get("grant_increment", max(1, math.ceil(baseline * default_grant_ratio)))
            )

            # Current Budget fields are integral, including wall-time minutes.
            estimate = float(int(estimate))
            working_target = float(int(working_target))
            emergency_limit = float(int(emergency_limit))
            grant_increment = float(max(1, int(math.ceil(grant_increment))))

            # The effective route starts at the working target. Emergency capacity
            # remains metadata until Runtime receives a healthy bounded grant.
            setattr(budget, dimension, int(working_target))
            dimensions[dimension] = AdaptiveBudgetDimension(
                estimate=estimate,
                working_target=working_target,
                emergency_limit=emergency_limit,
                grant_increment=grant_increment,
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
            "Adaptive personal-scale budget enabled: estimate is advisory, working target is initially effective, and emergency ceiling requires healthy-progress grants."
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

    @staticmethod
    def _emergency_probe(request: ReassessRequest) -> ReassessRequest:
        probe = request.model_copy(deep=True)
        adaptive = probe.route.strategy.adaptive_budget
        if adaptive is None or not adaptive.enabled:
            return probe
        for dimension, envelope in adaptive.dimensions.items():
            if hasattr(probe.route.strategy.budget, dimension):
                setattr(probe.route.strategy.budget, dimension, int(envelope.emergency_limit))
        probe.requested_headroom = {}
        return probe

    @staticmethod
    def _grant_proposals(
        request: ReassessRequest,
    ) -> tuple[list[AdaptiveBudgetGrant], list[str]]:
        adaptive = request.route.strategy.adaptive_budget
        if adaptive is None or not adaptive.enabled:
            return [], []

        grants: list[AdaptiveBudgetGrant] = []
        blocked: list[str] = []
        budget = request.route.strategy.budget

        for dimension, envelope in adaptive.dimensions.items():
            counter = _ELASTIC_COUNTERS.get(dimension)
            if not counter or not hasattr(budget, dimension):
                continue
            used = float(getattr(request.progress, counter, 0.0))
            current = float(getattr(budget, dimension))
            emergency = float(envelope.emergency_limit)
            requested = max(0.0, float(request.requested_headroom.get(dimension, 0.0)))
            projected = used + requested

            needs_grant = projected > current if requested > 0 else used >= current
            if not needs_grant:
                continue
            if used >= emergency or projected > emergency or current >= emergency:
                blocked.append(dimension)
                continue

            target = max(current + float(envelope.grant_increment), projected)
            new_limit = min(emergency, float(math.ceil(target)))
            if new_limit <= current:
                blocked.append(dimension)
                continue

            grants.append(AdaptiveBudgetGrant(
                dimension=dimension,
                previous_limit=current,
                new_limit=new_limit,
                emergency_limit=emergency,
                used=used,
                projected=projected,
            ))

        return grants, blocked

    def reassess(self, request: ReassessRequest) -> ReassessResponse:
        adaptive = request.route.strategy.adaptive_budget
        if adaptive is None or not adaptive.enabled:
            return super().reassess(request)

        # Evaluate health against the emergency envelope so the current working
        # target does not preempt the more meaningful anti-loop/decision guards.
        result = super().reassess(self._emergency_probe(request))
        signals = list(result.signals)
        for signal in self._adaptive_signals(request):
            if signal not in signals:
                signals.append(signal)

        # Completion, protected human decisions and real circuit breakers always
        # win over convenience headroom.
        if result.action in {"complete", "human_decision", "stop"}:
            return result.model_copy(update={"signals": signals})

        grants, blocked = self._grant_proposals(request)
        if blocked:
            dimension = blocked[0]
            return ReassessResponse(
                action="stop",
                reason=f"adaptive emergency budget ceiling would be exceeded: {dimension}",
                current_profile=request.route.strategy.profile,
                remaining=result.remaining,
                signals=signals + [f"emergency_budget_guard:{item}" for item in blocked],
            )

        for grant in grants:
            signals.append(f"adaptive_budget_grant:{grant.dimension}")

        return result.model_copy(update={
            "signals": signals,
            "adaptive_budget_grants": grants,
        })
