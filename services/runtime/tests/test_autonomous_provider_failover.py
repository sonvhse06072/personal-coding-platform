from __future__ import annotations

import asyncio
from copy import deepcopy

from app.engine_telemetry import RuntimeEngine


class Router:
    def __init__(self, route: dict | None = None, error: Exception | None = None) -> None:
        self.route_value = deepcopy(route)
        self.error = error
        self.payloads: list[dict] = []

    async def route(self, payload: dict) -> dict:
        self.payloads.append(deepcopy(payload))
        if self.error is not None:
            raise self.error
        assert self.route_value is not None
        return deepcopy(self.route_value)


def engine(router: Router) -> RuntimeEngine:
    value = RuntimeEngine.__new__(RuntimeEngine)
    value.router = router
    return value


def choice(model_id: str, provider: str, *, quota_group: str | None = None) -> dict:
    value = {
        "id": model_id,
        "provider": provider,
        "adapter": "fake",
        "model": f"{provider}/{model_id}",
    }
    if quota_group:
        value["quota_group"] = quota_group
    return value


def strategy() -> dict:
    return {"budget": {"max_provider_failovers": 2}}


def test_executor_provider_failover_continues_past_profile_prior() -> None:
    current = choice("openrouter_qwen3_coder_free", "openrouter")
    fallback = choice("codex_terra", "openai")
    router = Router({"strategy": {"executor": fallback}})
    runtime = engine(router)
    provider_state: dict = {}
    progress = {"provider_failovers": 2}

    candidate, reroute = asyncio.run(runtime._provider_failover(
        route_payload={"job_id": "job-1", "provider_state": {}},
        provider_state=provider_state,
        current_choice=current,
        failure_kind="authentication",
        progress=progress,
        strategy=strategy(),
    ))

    assert candidate == fallback
    assert reroute == {"strategy": {"executor": fallback}}
    assert progress["provider_failovers"] == 3
    assert provider_state["provider:openrouter"]["available"] is False
    assert router.payloads[0]["provider_state"]["provider:openrouter"]["available"] is False


def test_evaluator_provider_failover_continues_past_profile_prior() -> None:
    current = choice("openrouter_qwen3_coder_free", "openrouter")
    fallback = choice("codex_terra", "openai")
    router = Router({"strategy": {"evaluator": fallback}})
    runtime = engine(router)
    provider_state: dict = {}
    progress = {"provider_failovers": 2}

    candidate, _ = asyncio.run(runtime._provider_failover(
        route_payload={"job_id": "job-review", "provider_state": {}},
        provider_state=provider_state,
        current_choice=current,
        failure_kind="authentication",
        progress=progress,
        strategy=strategy(),
        role="evaluator",
    ))

    assert candidate == fallback
    assert progress["provider_failovers"] == 3
    assert provider_state["provider:openrouter"]["available"] is False


def test_antigravity_quota_exhaustion_can_use_other_capacity_past_prior() -> None:
    current = choice(
        "antigravity_free",
        "google_antigravity",
        quota_group="antigravity_gemini",
    )
    fallback = choice(
        "antigravity_claude_sonnet",
        "google_antigravity",
        quota_group="antigravity_claude_gpt",
    )
    router = Router({"strategy": {"executor": fallback}})
    runtime = engine(router)
    provider_state: dict = {}
    progress = {"provider_failovers": 2}

    candidate, _ = asyncio.run(runtime._provider_failover(
        route_payload={"job_id": "job-quota", "provider_state": {}},
        provider_state=provider_state,
        current_choice=current,
        failure_kind="quota_exhausted",
        progress=progress,
        strategy=strategy(),
    ))

    assert candidate == fallback
    assert progress["provider_failovers"] == 3
    assert "provider:google_antigravity" not in provider_state
    assert provider_state["quota:model:antigravity_free"]["available"] is False


def test_no_eligible_route_still_fails_closed_without_incrementing_counter() -> None:
    current = choice("openrouter_qwen3_coder_free", "openrouter")
    router = Router(error=RuntimeError("No eligible model for role"))
    runtime = engine(router)
    provider_state: dict = {}
    progress = {"provider_failovers": 2}

    candidate, reroute = asyncio.run(runtime._provider_failover(
        route_payload={"job_id": "job-none", "provider_state": {}},
        provider_state=provider_state,
        current_choice=current,
        failure_kind="authentication",
        progress=progress,
        strategy=strategy(),
    ))

    assert candidate is None
    assert reroute is None
    assert progress["provider_failovers"] == 2
    assert provider_state["provider:openrouter"]["available"] is False


def test_contradictory_same_failed_choice_is_rejected_without_counting_failover() -> None:
    current = choice("openrouter_qwen3_coder_free", "openrouter")
    router = Router({"strategy": {"executor": current}})
    runtime = engine(router)
    provider_state: dict = {}
    progress = {"provider_failovers": 2}

    candidate, reroute = asyncio.run(runtime._provider_failover(
        route_payload={"job_id": "job-same", "provider_state": {}},
        provider_state=provider_state,
        current_choice=current,
        failure_kind="provider_unavailable",
        progress=progress,
        strategy=strategy(),
    ))

    assert candidate is None
    assert reroute == {"strategy": {"executor": current}}
    assert progress["provider_failovers"] == 2
    assert provider_state["provider:openrouter"]["available"] is False
