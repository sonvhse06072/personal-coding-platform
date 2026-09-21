from __future__ import annotations

from .engine_runtime import RouterEngine as RuntimeRouterEngine
from .schemas import ReassessRequest, ReassessResponse


class RouterEngine(RuntimeRouterEngine):
    """Legacy completion-aware wrapper for indivisible provider token usage.

    Effective adaptive jobs treat cumulative input/output token totals as durable
    telemetry, so their normal reassessment path owns completion/anomaly decisions.
    Legacy-hard jobs retain historical token ceilings; for those jobs a successful
    indivisible provider call may still cross the ceiling after satisfying DoD.
    """

    def reassess(self, request: ReassessRequest) -> ReassessResponse:
        if request.route.strategy.budget_mode == "adaptive":
            return super().reassess(request)

        budget = request.route.strategy.budget
        progress = request.progress
        token_overruns: list[str] = []
        if progress.input_tokens > budget.max_input_tokens:
            token_overruns.append("input_tokens")
        if progress.output_tokens > budget.max_output_tokens:
            token_overruns.append("output_tokens")

        if not token_overruns:
            return super().reassess(request)

        # Re-run the established policy with only post-call token counters clamped
        # to their ceilings. Every other budget, decision, scope and DoD condition
        # is evaluated unchanged by RuntimeRouterEngine.
        clamped = progress.model_copy(update={
            "input_tokens": min(progress.input_tokens, budget.max_input_tokens),
            "output_tokens": min(progress.output_tokens, budget.max_output_tokens),
        })
        probe = super().reassess(ReassessRequest(
            route=request.route,
            progress=clamped,
            provider_state=request.provider_state,
        ))

        signals = list(probe.signals)
        signals.extend(f"post_call_token_overrun:{name}" for name in token_overruns)

        if probe.action == "human_decision":
            # Human policy gates are allowed to resolve without another provider
            # call, so keep their priority over automatic completion/stop.
            return probe.model_copy(update={"signals": signals})

        if probe.action != "complete":
            # DoD is incomplete or another hard budget is violated. Preserve the
            # original counters so the normal policy remains fail-closed and no
            # additional provider work can start.
            return super().reassess(request)

        return ReassessResponse(
            action="complete",
            reason="Definition-of-done checks passed; post-call token overrun recorded and no further model work allowed",
            current_profile=request.route.strategy.profile,
            remaining=probe.remaining,
            signals=signals,
        )
