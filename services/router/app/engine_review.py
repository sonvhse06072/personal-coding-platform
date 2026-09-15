from __future__ import annotations

from .schemas import (
    ProviderState,
    ReviewPolicy,
    RoutingRequest,
    RoutingResponse,
    StaffingRequest,
)
from .staffing_collaboration import RouterEngine as CollaborationRouterEngine


_SECURITY_FLAGS = {
    "security_sensitive",
    "security_boundary_change",
    "authentication_change",
    "authorization_change",
    "secret_management_change",
}


class RouterEngine(CollaborationRouterEngine):
    """Select review spend and reviewer independence from task risk.

    The logical role remains ``reviewer``. The Router may choose any eligible
    provider/model for that role; Runtime never asks an implementation agent to
    name a reviewer model directly.
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

    @staticmethod
    def _high_impact_review(request: RoutingRequest, result: RoutingResponse) -> bool:
        flags = set(request.task.flags)
        return bool(
            flags & _SECURITY_FLAGS
            or request.repo.security_sensitive
            or request.repo.authentication_change
            or request.repo.authorization_change
            or result.dimensions.architecture_impact >= 70
            or result.dimensions.risk >= 85
        )

    @staticmethod
    def _policy_for(request: RoutingRequest, result: RoutingResponse) -> ReviewPolicy:
        profile = result.strategy.profile
        if RouterEngine._high_impact_review(request, result):
            return ReviewPolicy(
                level="critical",
                required=True,
                independent=True,
                different_model_required=True,
                different_provider_required=True,
                reason="security/architecture/high-risk work requires cross-provider review when eligible",
            )
        if profile == "critical":
            return ReviewPolicy(
                level="critical",
                required=True,
                independent=True,
                different_model_required=True,
                different_provider_required=True,
                reason="critical profile requires cross-provider review when eligible",
            )
        if profile == "complex":
            return ReviewPolicy(
                level="strong",
                required=True,
                independent=True,
                different_model_required=True,
                reason="complex profile requires a stronger independent reviewer",
            )
        if profile == "standard":
            return ReviewPolicy(
                level="standard",
                required=True,
                independent=True,
                reason="standard profile requires bounded independent Task Contract/diff review",
            )
        return ReviewPolicy(
            level="lightweight",
            required=False,
            conditional_on_strong_evidence=True,
            independent=True,
            different_model_required=True,
            reason="routine work skips model review only when deterministic evidence is strong",
        )

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
        # jobs may skip the actual call later when full deterministic evidence is
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
