from __future__ import annotations

from typing import Any

from .engine_adaptive import RouterEngine as BudgetRouterEngine
from .model_capabilities import (
    ReasoningCapability,
    next_supported_effort,
    reasoning_capability,
)
from .schemas import (
    DimensionScores,
    ProviderState,
    ReassessRequest,
    ReassessResponse,
    RoutingRequest,
    RoutingResponse,
    StaffingRequest,
    StaffingResponse,
)


_STAFF_REASONING_BY_PROFILE = {
    "fast": "low",
    "standard": "low",
    "complex": "medium",
    "critical": "high",
}
_COLLABORATION_CAPABILITY_WEIGHTS = {
    "consultant": {
        "reasoning": 0.34,
        "planning": 0.24,
        "repo_exploration": 0.22,
        "review": 0.12,
        "structured_output": 0.08,
    },
    "test_engineer": {
        "debugging": 0.28,
        "review": 0.24,
        "reasoning": 0.20,
        "repo_exploration": 0.16,
        "structured_output": 0.12,
    },
    "debugger": {
        "debugging": 0.36,
        "reasoning": 0.28,
        "repo_exploration": 0.20,
        "review": 0.10,
        "structured_output": 0.06,
    },
    "security_specialist": {
        "review": 0.32,
        "reasoning": 0.30,
        "debugging": 0.14,
        "repo_exploration": 0.12,
        "structured_output": 0.12,
    },
    "reviewer": {
        "review": 0.38,
        "reasoning": 0.28,
        "debugging": 0.14,
        "repo_exploration": 0.10,
        "structured_output": 0.10,
    },
}


class RouterEngine(BudgetRouterEngine):
    """Router extension for staffing, quota state and explicit reasoning effort."""

    def _capability_match(
        self,
        model: dict[str, Any],
        role: str,
        dimensions: DimensionScores,
        profile: str,
    ) -> float:
        if role == "product_manager":
            required = {
                "planning": 0.30,
                "reasoning": 0.30,
                "structured_output": 0.22,
                "review": 0.10,
                "repo_exploration": 0.08,
            }
        else:
            required = _COLLABORATION_CAPABILITY_WEIGHTS.get(role)
            if required is None:
                return super()._capability_match(model, role, dimensions, profile)

        cap = model.get("capabilities", {})
        score = sum((float(cap.get(name, 0)) / 10.0) * weight for name, weight in required.items())
        difficulty = (
            dimensions.reasoning_requirement
            + dimensions.context_requirement
            + dimensions.ambiguity
            + dimensions.architecture_impact
        ) / 400.0
        if profile in {"complex", "critical"}:
            score *= 0.90 + 0.10 * min(1.0, score / max(0.45, difficulty))
        return max(0.0, min(1.0, score))

    @staticmethod
    def _combine_state(primary: ProviderState, quota: ProviderState) -> ProviderState:
        return ProviderState(
            healthy=primary.healthy and quota.healthy,
            quota_pressure=max(primary.quota_pressure, quota.quota_pressure),
            error_rate=max(primary.error_rate, quota.error_rate),
            latency_ms=max(primary.latency_ms, quota.latency_ms),
            predicted_success=(
                primary.predicted_success
                if primary.predicted_success is not None
                else quota.predicted_success
            ),
            available=primary.available and quota.available,
        )

    def _quota_aware_request(self, request: RoutingRequest) -> RoutingRequest:
        """Project model- and group-quota health onto model scoring.

        `quota:model:<id>` is created from a concrete model quota/rate-limit
        failure. `quota:<group>` is reserved for authoritative shared-bucket
        evidence. Base Router still combines this model view with
        `provider:<name>` health afterwards.
        """
        updated = request.model_copy(deep=True)
        state = dict(updated.provider_state)
        for model_id, model in self.models.items():
            combined = state.get(model_id, ProviderState())
            model_quota = state.get(f"quota:model:{model_id}")
            if model_quota is not None:
                combined = self._combine_state(combined, model_quota)
            quota_group = str(model.get("quota_group") or "").strip()
            group_quota = state.get(f"quota:{quota_group}") if quota_group else None
            if group_quota is not None:
                combined = self._combine_state(combined, group_quota)
            if model_quota is not None or group_quota is not None:
                state[model_id] = combined
        updated.provider_state = state
        return updated

    def select_model(self, **kwargs):
        request = kwargs.get("request")
        if isinstance(request, RoutingRequest):
            kwargs["request"] = self._quota_aware_request(request)
        choice, rejected = super().select_model(**kwargs)
        model = self.models.get(choice.id, {})
        choice.quota_group = str(model.get("quota_group") or "") or None
        return choice, rejected

    @staticmethod
    def _staffing_dimensions(request: StaffingRequest) -> DimensionScores:
        semantic = request.semantic
        return DimensionScores(
            scope=10,
            dependency_depth=10,
            ambiguity=semantic.ambiguity,
            architecture_impact=semantic.architecture_impact,
            verification_difficulty=semantic.verification_difficulty,
            risk=semantic.risk,
            context_requirement=semantic.context_requirement,
            novelty=semantic.novelty,
            reasoning_requirement=semantic.reasoning_requirement,
        )

    def _reasoning_capability(self, choice: Any) -> ReasoningCapability:
        if choice is None:
            return ReasoningCapability(False, ())
        model = self.models.get(choice.id)
        if not isinstance(model, dict):
            raise RuntimeError(f"Unknown PCP model id in model choice: {choice.id!r}")
        if choice.adapter != model.get("adapter") or choice.model != str(model.get("model")):
            raise RuntimeError(
                f"Model choice metadata does not match registry for {choice.id!r}"
            )
        try:
            return reasoning_capability(choice.id, model)
        except ValueError as exc:
            raise RuntimeError(str(exc)) from exc

    def _validate_reasoning_choice(self, choice: Any) -> ReasoningCapability:
        capability = self._reasoning_capability(choice)
        if choice is None or choice.reasoning_effort is None:
            return capability
        if choice.reasoning_effort not in capability.allowed_efforts:
            raise RuntimeError(
                f"Reasoning effort {choice.reasoning_effort!r} is unsupported "
                f"for PCP model {choice.id!r}"
            )
        return capability

    def _apply_reasoning(self, choice: Any, effort: str | None) -> None:
        capability = self._reasoning_capability(choice)
        if choice is None or not capability.supports_explicit_effort:
            return
        if effort is None:
            return
        if effort not in capability.allowed_efforts:
            raise RuntimeError(
                f"Configured reasoning effort {effort!r} is unsupported "
                f"for PCP model {choice.id!r}"
            )
        choice.reasoning_effort = effort
        marker = f"reasoning_effort={effort}"
        if marker not in choice.reasons:
            choice.reasons.append(marker)

    def _next_reasoning_choice(self, choice: Any, ceiling: str | None) -> Any | None:
        capability = self._validate_reasoning_choice(choice)
        if not capability.supports_explicit_effort:
            return None
        current = choice.reasoning_effort
        if current is None or ceiling is None:
            return None
        next_effort = next_supported_effort(capability, current, ceiling)
        if next_effort is None:
            return None
        value = choice.model_copy(deep=True)
        value.reasoning_effort = next_effort
        value.reasons = list(value.reasons) + [f"reasoning escalation {current}->{next_effort}"]
        return value

    def route(self, request: RoutingRequest) -> RoutingResponse:
        result = super().route(request)
        profile_cfg = self.policy["profiles"][result.strategy.profile]
        efforts = dict(profile_cfg.get("reasoning_effort") or {})
        self._apply_reasoning(result.strategy.planner, efforts.get("planner"))
        self._apply_reasoning(result.strategy.executor, efforts.get("executor"))
        self._apply_reasoning(result.strategy.evaluator, efforts.get("evaluator"))
        result.strategy.reasoning_ceiling = dict(profile_cfg.get("reasoning_ceiling") or {})
        return result

    def reassess(self, request: ReassessRequest) -> ReassessResponse:
        self._validate_reasoning_choice(request.route.strategy.executor)
        result = super().reassess(request)
        profile_cfg = self.policy["profiles"][request.route.strategy.profile]
        efforts = dict(profile_cfg.get("reasoning_effort") or {})
        if result.next_executor is not None and result.next_executor.reasoning_effort is None:
            self._apply_reasoning(result.next_executor, efforts.get("executor"))

        if request.progress.escalations >= request.route.strategy.budget.max_escalations:
            return result

        current = request.route.strategy.executor
        ceiling = request.route.strategy.reasoning_ceiling.get("executor")
        boosted = self._next_reasoning_choice(current, ceiling)
        should_replace_model_escalation = result.action == "escalate" and result.next_executor is not None
        actionable_signals = [
            signal
            for signal in result.signals
            if not signal.startswith(("budget_estimate_exceeded:", "budget_headroom_active:"))
        ]
        should_use_signal_escalation = result.action == "continue" and bool(actionable_signals)
        if boosted is not None and (should_replace_model_escalation or should_use_signal_escalation):
            return ReassessResponse(
                action="escalate",
                reason=f"Increase agent reasoning effort {current.reasoning_effort}->{boosted.reasoning_effort} before changing model",
                current_profile=request.route.strategy.profile,
                next_executor=boosted,
                remaining=result.remaining,
                signals=list(result.signals) + ["reasoning_effort_escalation"],
            )
        return result

    def staff(self, request: StaffingRequest) -> StaffingResponse:
        role_cfg = (self.policy.get("staffing_roles", {}) or {}).get(request.role)
        if not isinstance(role_cfg, dict):
            raise RuntimeError(f"Unknown or unconfigured logical role: {request.role}")

        allowed_profiles = list(role_cfg.get("allowed_profiles", []))
        if allowed_profiles and request.profile not in allowed_profiles:
            raise RuntimeError(
                f"Profile {request.profile!r} is not allowed for logical role {request.role!r}"
            )

        dimensions = self._staffing_dimensions(request)
        pseudo = RoutingRequest(
            job_id=request.request_id,
            project_id=request.project_id,
            repository="logical-role-staffing",
            source_commit="staffing",
            task={
                "title": f"Staff logical role {request.role}",
                "task_type": request.role,
                "semantic": request.semantic.model_dump(mode="json"),
            },
            repo={
                "estimated_files": 1,
                "affected_components": 1,
                "dependency_depth": 1,
                "tests_available": True,
                "existing_pattern": True,
            },
            provider_state=request.provider_state,
        )
        choice, rejected = self.select_model(
            role=request.role,
            role_names=list(role_cfg.get("model_roles", [request.role])),
            preferred_ids=list(role_cfg.get("preferred_ids", [])),
            request=pseudo,
            dimensions=dimensions,
            profile=request.profile,
            exclude_model_ids=set(request.exclude_model_ids),
        )
        self._apply_reasoning(choice, _STAFF_REASONING_BY_PROFILE.get(request.profile))
        return StaffingResponse(
            request_id=request.request_id,
            project_id=request.project_id,
            role=request.role,
            profile=request.profile,
            choice=choice,
            rejected_candidates=rejected,
            policy_version=int(self.policy.get("version", 1)),
            registry_version=int(self.models_doc.get("version", 1)),
        )
