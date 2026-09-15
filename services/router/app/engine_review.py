from __future__ import annotations

from typing import Any

from .schemas import (
    ProviderState,
    ReviewPolicy,
    RoutingRequest,
    RoutingResponse,
    StaffingRequest,
)
from .staffing_collaboration import RouterEngine as CollaborationRouterEngine


class RouterEngine(CollaborationRouterEngine):
    """Select review spend and reviewer independence from calibratable policy.

    The logical role remains ``reviewer``. The Router may choose any eligible
    provider/model for that role; Runtime never asks an implementation agent to
    name a reviewer model directly. Review levels/thresholds live in
    routing-policy.yml so PM calibration does not require code changes.
    """

    @staticmethod
    def _unavailable_state() -> ProviderState:
        return ProviderState(
            healthy=False,
            available=False,
            quota_pressure=1.0,
            error_rate=1.0,
            latency_ms=0,
        )

    def _review_config(self) -> dict[str, Any]:
        config = self.policy.get("review_policy") or {}
        if not isinstance(config, dict):
            raise RuntimeError("routing review_policy must be an object")
        profiles = config.get("profiles") or {}
        high_impact = config.get("high_impact") or {}
        if not isinstance(profiles, dict) or not isinstance(high_impact, dict):
            raise RuntimeError("routing review_policy profiles/high_impact must be objects")
        return config

    def _high_impact_review(self, request: RoutingRequest, result: RoutingResponse) -> bool:
        config = self._review_config().get("high_impact") or {}
        flags = {str(item) for item in config.get("flags", []) if str(item).strip()}
        architecture_min = int(config.get("architecture_impact_min", 101))
        risk_min = int(config.get("risk_min", 101))
        return bool(
            set(request.task.flags) & flags
            or request.repo.security_sensitive
            or request.repo.authentication_change
            or request.repo.authorization_change
            or result.dimensions.architecture_impact >= architecture_min
            or result.dimensions.risk >= risk_min
        )

    def _policy_for(self, request: RoutingRequest, result: RoutingResponse) -> ReviewPolicy:
        config = self._review_config()
        if self._high_impact_review(request, result):
            raw = (config.get("high_impact") or {}).get("policy") or {}
        else:
            raw = (config.get("profiles") or {}).get(result.strategy.profile) or {}
        if not isinstance(raw, dict) or not raw:
            raise RuntimeError(
                f"No review policy configured for profile {result.strategy.profile!r}"
            )
        return ReviewPolicy.model_validate(raw)

    def _staff_reviewer(
        self,
        request: RoutingRequest,
        result: RoutingResponse,
        *,
        exclude_model: bool,
        exclude_provider: bool,
    ):
        state = {key: value.model_copy(deep=True) for key, value in request.provider_state.items()}
        executor = result.strategy.executor
        if exclude_model:
            state[executor.id] = self._unavailable_state()
            state[f"quota:model:{executor.id}"] = self._unavailable_state()
        if exclude_provider:
            state[f"provider:{executor.provider}"] = self._unavailable_state()
        staffed = self.staff(
            StaffingRequest(
                request_id=f"review:{request.job_id}",
                project_id=request.project_id,
                role="reviewer",
                profile=result.strategy.profile,
                semantic=request.task.semantic,
                provider_state=state,
            )
        )
        return staffed.choice

    def route(self, request: RoutingRequest) -> RoutingResponse:
        result = super().route(request)
        policy = self._policy_for(request, result)

        # Always prepare a reviewer for policy levels that might need one. Fast
        # jobs may skip the actual call later when deterministic evidence is
        # strong, so staffing here does not itself spend provider tokens.
        evaluator = result.strategy.evaluator
        independence_satisfied = True
        if policy.different_provider_required:
            try:
                evaluator = self._staff_reviewer(
                    request,
                    result,
                    exclude_model=True,
                    exclude_provider=True,
                )
            except RuntimeError:
                # "when eligible capacity exists": if no cross-provider reviewer
                # is currently eligible, preserve a bounded same-provider review
                # rather than turning provider scarcity into a false policy claim.
                independence_satisfied = False
                try:
                    evaluator = self._staff_reviewer(
                        request,
                        result,
                        exclude_model=True,
                        exclude_provider=False,
                    )
                except RuntimeError:
                    evaluator = evaluator or self._staff_reviewer(
                        request,
                        result,
                        exclude_model=False,
                        exclude_provider=False,
                    )
        elif policy.different_model_required:
            try:
                evaluator = self._staff_reviewer(
                    request,
                    result,
                    exclude_model=True,
                    exclude_provider=False,
                )
            except RuntimeError:
                independence_satisfied = False
                evaluator = evaluator or self._staff_reviewer(
                    request,
                    result,
                    exclude_model=False,
                    exclude_provider=False,
                )
        else:
            evaluator = evaluator or self._staff_reviewer(
                request,
                result,
                exclude_model=False,
                exclude_provider=False,
            )

        policy.independence_satisfied = independence_satisfied
        result.strategy.evaluator = evaluator
        result.strategy.review_policy = policy
        reason = f"review={policy.level}:{policy.reason}"
        if not independence_satisfied:
            reason += ":preferred independence unavailable"
        if reason not in result.strategy.reasons:
            result.strategy.reasons.append(reason)
        return result


__all__ = ["RouterEngine"]
