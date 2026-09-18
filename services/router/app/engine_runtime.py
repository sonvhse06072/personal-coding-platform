from __future__ import annotations

from collections import Counter

from .engine import RouterEngine as BaseRouterEngine
from .schemas import HumanDecision, ReassessRequest, ReassessResponse, RoutingRequest


class RouterEngine(BaseRouterEngine):
    """Router engine with completion-aware budget reassessment.

    Adaptive routes distinguish material resource ceilings from work-shape
    telemetry. Model/tool/test/iteration/repair/failover counters may cross their
    high-water marks while execution remains healthy; anti-loop, scope, provider
    eligibility and protected-decision signals still control abnormal work.
    Legacy-hard routes retain historical strict counter semantics. Token volume,
    wall time and hard cost remain material circuit breakers for every route.
    """

    def reassess(self, request: ReassessRequest) -> ReassessResponse:
        route = request.route
        progress = request.progress
        budget = route.strategy.budget
        anti = route.strategy.anti_loop
        adaptive_work_shape = route.strategy.budget_mode == "adaptive"
        signals: list[str] = []

        remaining = {
            "model_calls": max(0, budget.max_model_calls - progress.model_calls),
            "input_tokens": max(0, budget.max_input_tokens - progress.input_tokens),
            "output_tokens": max(0, budget.max_output_tokens - progress.output_tokens),
            "tool_calls": max(0, budget.max_tool_calls - progress.tool_calls),
            "iterations": max(0, budget.max_iterations - progress.iteration),
            "repair_iterations": max(0, budget.max_repair_iterations - progress.repair_iterations),
            "escalations": max(0, budget.max_escalations - progress.escalations),
            "provider_failovers": max(0, budget.max_provider_failovers - progress.provider_failovers),
            "model_failovers": max(0, budget.max_model_failovers - progress.model_failovers),
            "test_runs": max(0, budget.max_test_runs - progress.test_runs),
            "wall_time_minutes": max(0.0, budget.max_wall_time_minutes - progress.elapsed_minutes),
            "cost_usd": round(max(0.0, budget.hard_cost_usd - progress.cost_usd), 4),
            "changed_files": max(0, budget.max_changed_files - progress.changed_files),
        }

        # Material resource overruns remain unconditional stops. Adaptive
        # work-shape counters are telemetry and anti-loop inputs; legacy-hard
        # routes preserve the historical strict ceilings.
        overruns = [
            (progress.input_tokens > budget.max_input_tokens, "input-token budget exceeded"),
            (progress.output_tokens > budget.max_output_tokens, "output-token budget exceeded"),
            (progress.elapsed_minutes > budget.max_wall_time_minutes, "wall-time budget exceeded"),
            (progress.cost_usd > budget.hard_cost_usd, "hard cost budget exceeded"),
        ]
        if not adaptive_work_shape:
            overruns.extend([
                (progress.model_calls > budget.max_model_calls, "model-call budget exceeded"),
                (progress.tool_calls > budget.max_tool_calls, "tool-call budget exceeded"),
                (progress.iteration > budget.max_iterations, "iteration budget exceeded"),
                (progress.repair_iterations > budget.max_repair_iterations, "repair budget exceeded"),
                (progress.model_failovers > budget.max_model_failovers, "model-failover budget exceeded"),
                (progress.test_runs > budget.max_test_runs, "test-run budget exceeded"),
            ])
        for hit, reason in overruns:
            if hit:
                return ReassessResponse(
                    action="stop",
                    reason=reason,
                    current_profile=route.strategy.profile,
                    remaining=remaining,
                    signals=["hard_budget_overrun"],
                )

        # A discovered decision boundary has priority over automatic completion.
        # Human approval is a policy condition, not a routine code review.
        if progress.important_decision_flags:
            human = HumanDecision(
                required=True,
                triggers=progress.important_decision_flags,
                reason="Execution discovered an important decision boundary.",
            )
            return ReassessResponse(
                action="human_decision",
                reason="Human decision required; routine implementation review is not requested",
                current_profile=route.strategy.profile,
                human_decision=human,
                remaining=remaining,
                signals=["decision_boundary"],
            )

        material_required = "material_change" in route.strategy.definition_of_done.get("required", [])
        material_ok = (not material_required) or progress.material_change_present
        if progress.required_checks_passed and progress.tests_passed and progress.agent_succeeded and material_ok:
            return ReassessResponse(
                action="complete",
                reason="Definition-of-done checks passed",
                current_profile=route.strategy.profile,
                remaining=remaining,
                signals=["done"],
            )

        # Once DoD is incomplete, material ceilings still prevent another turn.
        # Adaptive work-shape thresholds do not; they remain visible in remaining
        # telemetry and adaptive-budget signals.
        exhausted = [
            (progress.input_tokens >= budget.max_input_tokens, "input-token budget exhausted"),
            (progress.output_tokens >= budget.max_output_tokens, "output-token budget exhausted"),
            (progress.elapsed_minutes >= budget.max_wall_time_minutes, "wall-time budget exhausted"),
            (progress.cost_usd >= budget.hard_cost_usd, "hard cost budget exhausted"),
        ]
        if not adaptive_work_shape:
            exhausted.extend([
                (progress.model_calls >= budget.max_model_calls, "model-call budget exhausted"),
                (progress.tool_calls >= budget.max_tool_calls, "tool-call budget exhausted"),
                (progress.iteration >= budget.max_iterations, "iteration budget exhausted"),
                (progress.repair_iterations >= budget.max_repair_iterations, "repair budget exhausted"),
                (progress.test_runs >= budget.max_test_runs, "test-run budget exhausted"),
            ])
        for hit, reason in exhausted:
            if hit:
                return ReassessResponse(
                    action="stop",
                    reason=reason,
                    current_profile=route.strategy.profile,
                    remaining=remaining,
                    signals=["hard_budget_guard"],
                )

        if progress.required_checks_passed and progress.tests_passed and material_required and not progress.material_change_present:
            signals.append("material_change_missing")
        if not progress.agent_succeeded and progress.last_agent_failure_kind:
            signals.append(f"agent_failure:{progress.last_agent_failure_kind}")

        if progress.changed_files > budget.max_changed_files or progress.unexpected_scope:
            signals.append("scope_expansion")

        repeat_limit = int(anti.get("same_failure_fingerprint_limit", 2))
        repeated, fingerprint = self._repeated_failure(progress, repeat_limit)
        if repeated:
            signals.append(f"repeated_failure:{fingerprint}")

        oscillation = self._oscillation(progress, int(anti.get("diff_oscillation_limit", 2)))
        if oscillation:
            signals.append("diff_oscillation")

        no_progress_limit = int(anti.get("no_progress_iterations", 2))
        if len(progress.progress_markers) >= no_progress_limit + 1:
            tail = progress.progress_markers[-(no_progress_limit + 1):]
            if len(set(tail)) == 1:
                signals.append("no_progress")

        if progress.cost_usd >= budget.soft_cost_usd:
            signals.append("soft_cost_budget")

        should_escalate = bool(signals) or progress.repair_iterations >= max(1, budget.max_repair_iterations - 1)
        if should_escalate and progress.escalations < budget.max_escalations:
            current = route.strategy.executor
            model = self.models.get(current.id, {})
            tier_order = ["utility", "balanced", "strong", "premium", "frontier"]
            current_tier = model.get("tier", "balanced")
            current_index = tier_order.index(current_tier) if current_tier in tier_order else 1
            next_min = min(len(tier_order) - 1, current_index + 1)

            pseudo = RoutingRequest(
                job_id=route.job_id,
                project_id=route.project_id,
                repository="reassessment",
                source_commit=route.source_commit,
                task={"title": "Reassessed execution", "semantic": {
                    "ambiguity": route.dimensions.ambiguity,
                    "architecture_impact": route.dimensions.architecture_impact,
                    "verification_difficulty": route.dimensions.verification_difficulty,
                    "risk": route.dimensions.risk,
                    "context_requirement": route.dimensions.context_requirement,
                    "novelty": route.dimensions.novelty,
                    "reasoning_requirement": route.dimensions.reasoning_requirement,
                }},
                repo={"estimated_files": max(1, progress.changed_files)},
                provider_state=request.provider_state,
            )
            profile_cfg = self.policy["profiles"][route.strategy.profile]
            try:
                next_executor, _ = self.select_model(
                    role="executor",
                    role_names=profile_cfg.get("executor_roles", ["executor"]),
                    preferred_ids=profile_cfg.get("preferred_executor_ids", []),
                    request=pseudo,
                    dimensions=route.dimensions,
                    profile=route.strategy.profile,
                    minimum_tier_index=next_min,
                )
                if next_executor.id != current.id:
                    return ReassessResponse(
                        action="escalate",
                        reason="Progress guard or soft budget indicates current strategy should escalate",
                        current_profile=route.strategy.profile,
                        next_executor=next_executor,
                        remaining=remaining,
                        signals=signals,
                    )
            except RuntimeError:
                pass

        if repeated or oscillation or "no_progress" in signals or "scope_expansion" in signals:
            return ReassessResponse(
                action="stop",
                reason=(
                    "Circuit breaker: abnormal execution signal without a valid escalation path"
                ),
                current_profile=route.strategy.profile,
                remaining=remaining,
                signals=signals,
            )

        return ReassessResponse(
            action="continue",
            reason=(
                "No material circuit-break or anomaly detected; adaptive work-shape counters are telemetry"
                if adaptive_work_shape
                else "Within budget and no circuit-break condition detected"
            ),
            current_profile=route.strategy.profile,
            remaining=remaining,
            signals=signals,
        )
