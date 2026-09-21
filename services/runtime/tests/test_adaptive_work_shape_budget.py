from __future__ import annotations

import asyncio
import time
from copy import deepcopy

from app.engine_core import RuntimeEngineCore


def strategy(*, mode: str) -> dict:
    return {
        "budget_mode": mode,
        "budget": {
            "max_model_calls": 40,
            "max_input_tokens": 8_000_000,
            "max_output_tokens": 1_000_000,
            "max_tool_calls": 400,
            "max_iterations": 24,
            "max_repair_iterations": 12,
            "max_test_runs": 40,
            "max_wall_time_minutes": 180,
            "max_model_failovers": 2,
            "hard_cost_usd": 5.0,
        },
    }


def progress() -> dict:
    return {
        "model_calls": 40,
        "input_tokens": 3_931_952,
        "output_tokens": 236_484,
        "tool_calls": 401,
        "test_runs": 41,
        "repair_iterations": 12,
        "iteration": 24,
        "elapsed_minutes": 150.0,
        "cost_usd": 0.0,
        "model_failovers": 2,
    }


def test_adaptive_work_shape_counters_do_not_block_next_model_turn() -> None:
    reason = RuntimeEngineCore._pre_model_budget_reason(
        progress(),
        strategy= strategy(mode="adaptive"),
        include_iteration=True,
    )

    assert reason is None


def test_legacy_hard_work_shape_counters_remain_strict() -> None:
    reason = RuntimeEngineCore._pre_model_budget_reason(
        progress(),
        strategy=strategy(mode="legacy_hard"),
        include_iteration=True,
    )

    assert reason == "model-call budget exhausted"


def test_adaptive_cumulative_token_high_water_does_not_block_next_turn() -> None:
    state = progress()
    state["input_tokens"] = 8_072_466
    state["output_tokens"] = 1_050_000

    reason = RuntimeEngineCore._pre_model_budget_reason(
        state,
        strategy=strategy(mode="adaptive"),
        include_iteration=True,
    )

    assert reason is None


def test_legacy_hard_cumulative_token_ceiling_remains_strict() -> None:
    state = progress()
    state.update({
        "model_calls": 1,
        "input_tokens": 8_000_000,
        "output_tokens": 100,
        "tool_calls": 1,
        "test_runs": 1,
        "repair_iterations": 1,
        "iteration": 1,
        "elapsed_minutes": 10.0,
    })

    reason = RuntimeEngineCore._pre_model_budget_reason(
        state,
        strategy=strategy(mode="legacy_hard"),
        include_iteration=True,
    )

    assert reason == "input-token budget exhausted"


def test_adaptive_hard_cost_still_blocks_above_token_high_water() -> None:
    state = progress()
    state["input_tokens"] = 8_072_466
    state["cost_usd"] = 5.0

    reason = RuntimeEngineCore._pre_model_budget_reason(
        state,
        strategy=strategy(mode="adaptive"),
        include_iteration=True,
    )

    assert reason == "hard cost budget exhausted"


def test_adaptive_total_wall_time_is_non_blocking() -> None:
    state = progress()
    state["elapsed_minutes"] = 180.084

    reason = RuntimeEngineCore._pre_model_budget_reason(
        state,
        strategy=strategy(mode="adaptive"),
        include_iteration=True,
    )

    assert reason is None
    assert RuntimeEngineCore._remaining_seconds(
        strategy(mode="adaptive"),
        time.monotonic() - (181 * 60),
        2400,
    ) == 2400


def test_legacy_hard_total_wall_time_remains_strict() -> None:
    state = progress()
    state.update({
        "model_calls": 1,
        "tool_calls": 1,
        "test_runs": 1,
        "repair_iterations": 1,
        "iteration": 1,
        "elapsed_minutes": 180.0,
    })

    reason = RuntimeEngineCore._pre_model_budget_reason(
        state,
        strategy=strategy(mode="legacy_hard"),
        include_iteration=True,
    )

    assert reason == "wall-time budget exhausted"

    try:
        RuntimeEngineCore._remaining_seconds(
            strategy(mode="legacy_hard"),
            time.monotonic() - (181 * 60),
            2400,
        )
    except RuntimeError as exc:
        assert "wall-time budget exhausted" in str(exc)
    else:
        raise AssertionError("legacy-hard wall-time exhaustion must remain strict")


class Router:
    def __init__(self, route: dict) -> None:
        self.route_value = deepcopy(route)
        self.payloads: list[dict] = []

    async def route(self, payload: dict) -> dict:
        self.payloads.append(deepcopy(payload))
        return deepcopy(self.route_value)


def runtime(router: Router) -> RuntimeEngineCore:
    engine = RuntimeEngineCore.__new__(RuntimeEngineCore)
    engine.router = router
    return engine


def test_adaptive_model_failover_can_cross_profile_prior() -> None:
    fallback = {
        "id": "codex_sol",
        "provider": "openai",
        "adapter": "codex_cli",
        "model": "gpt-5.6-sol",
    }
    router = Router({"strategy": {"executor": fallback}})
    engine = runtime(router)
    provider_state: dict = {}
    state = {"model_failovers": 2}

    choice, reroute = asyncio.run(
        engine._model_failover(
            route_payload={"job_id": "job-1", "provider_state": {}},
            provider_state=provider_state,
            current_choice={
                "id": "codex_terra",
                "provider": "openai",
                "adapter": "codex_cli",
                "model": "gpt-5.6-terra",
            },
            progress=state,
            strategy=strategy(mode="adaptive"),
            reason="no_effect",
        )
    )

    assert choice == fallback
    assert reroute == {"strategy": {"executor": fallback}}
    assert state["model_failovers"] == 3
    assert provider_state["codex_terra"]["available"] is False


def test_legacy_model_failover_prior_remains_strict() -> None:
    fallback = {
        "id": "codex_sol",
        "provider": "openai",
        "adapter": "codex_cli",
        "model": "gpt-5.6-sol",
    }
    router = Router({"strategy": {"executor": fallback}})
    engine = runtime(router)
    provider_state: dict = {}
    state = {"model_failovers": 2}

    choice, reroute = asyncio.run(
        engine._model_failover(
            route_payload={"job_id": "job-legacy", "provider_state": {}},
            provider_state=provider_state,
            current_choice={
                "id": "codex_terra",
                "provider": "openai",
                "adapter": "codex_cli",
                "model": "gpt-5.6-terra",
            },
            progress=state,
            strategy=strategy(mode="legacy_hard"),
            reason="no_effect",
        )
    )

    assert choice is None
    assert reroute is None
    assert state["model_failovers"] == 2
    assert provider_state == {}
    assert router.payloads == []
