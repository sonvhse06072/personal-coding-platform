import pytest

from app.config import clear_config_cache, get_config
from app.schemas import ExecutionProgress, ReassessRequest, RoutingRequest
from app.staffing import RouterEngine


def make_engine() -> RouterEngine:
    clear_config_cache()
    return RouterEngine(get_config())


def request() -> RoutingRequest:
    return RoutingRequest(**{
        "job_id": "healthy-token-job",
        "project_id": "default",
        "repository": "repo",
        "source_commit": "abcd1234",
        "task": {
            "title": "Healthy verification-heavy change",
            "task_type": "implementation",
            "semantic": {
                "ambiguity": 55,
                "architecture_impact": 35,
                "verification_difficulty": 65,
                "risk": 40,
                "context_requirement": 65,
                "novelty": 35,
                "reasoning_requirement": 60,
            },
        },
        "repo": {
            "estimated_files": 8,
            "affected_components": 3,
            "dependency_depth": 3,
            "tests_available": True,
            "existing_pattern": True,
        },
    })


def test_token_profile_prior_is_not_a_stop_point():
    engine = make_engine()
    route = engine.route(request())
    adaptive = route.strategy.adaptive_budget
    assert adaptive is not None

    profile = engine.policy["profiles"][route.strategy.profile]
    input_prior = int(profile["max_input_tokens"])
    output_prior = int(profile["max_output_tokens"])

    assert "max_input_tokens" in adaptive.dimensions
    assert "max_output_tokens" in adaptive.dimensions
    assert route.strategy.budget.max_input_tokens == 8_000_000
    assert route.strategy.budget.max_output_tokens == 1_000_000
    assert adaptive.dimensions["max_input_tokens"].emergency_limit == 8_000_000
    assert adaptive.dimensions["max_output_tokens"].emergency_limit == 1_000_000

    result = engine.reassess(ReassessRequest(
        route=route,
        progress=ExecutionProgress(
            input_tokens=input_prior + 1,
            output_tokens=output_prior + 1,
            tests_passed=False,
            required_checks_passed=False,
            agent_succeeded=True,
        ),
    ))

    assert result.action != "stop"
    assert "hard_budget_guard" not in result.signals
    assert "hard_budget_overrun" not in result.signals


def test_dec_025c_input_usage_continues_inside_material_circuit_breaker():
    engine = make_engine()
    route = engine.route(request())
    route.strategy.budget_mode = "adaptive"

    result = engine.reassess(ReassessRequest(
        route=route,
        progress=ExecutionProgress(
            input_tokens=2_274_574,
            tests_passed=False,
            required_checks_passed=False,
            agent_succeeded=True,
        ),
    ))

    assert result.action != "stop"
    assert result.reason != "input-token budget exhausted"
    assert route.strategy.budget.max_input_tokens == 8_000_000


def test_adaptive_cumulative_input_token_high_water_is_non_blocking():
    engine = make_engine()
    route = engine.route(request())
    route.strategy.budget_mode = "adaptive"

    result = engine.reassess(ReassessRequest(
        route=route,
        progress=ExecutionProgress(
            input_tokens=8_072_466,
            tests_passed=False,
            required_checks_passed=False,
            agent_succeeded=True,
        ),
    ))

    assert result.action != "stop"
    assert result.reason != "input-token budget exhausted"
    assert "hard_budget_guard" not in result.signals
    assert "hard_budget_overrun" not in result.signals
    assert "budget_emergency_threshold_reached:max_input_tokens" in result.signals


def test_legacy_hard_cumulative_input_token_limit_still_fails_closed():
    engine = make_engine()
    route = engine.route(request())
    route.strategy.budget_mode = "legacy_hard"

    result = engine.reassess(ReassessRequest(
        route=route,
        progress=ExecutionProgress(
            input_tokens=route.strategy.budget.max_input_tokens,
            tests_passed=False,
            required_checks_passed=False,
            agent_succeeded=True,
        ),
    ))

    assert result.action == "stop"
    assert result.reason == "input-token budget exhausted"
    assert "hard_budget_guard" in result.signals


def test_adaptive_hard_cost_remains_fail_closed_above_token_high_water():
    engine = make_engine()
    route = engine.route(request())
    route.strategy.budget_mode = "adaptive"

    result = engine.reassess(ReassessRequest(
        route=route,
        progress=ExecutionProgress(
            input_tokens=8_072_466,
            cost_usd=route.strategy.budget.hard_cost_usd,
            tests_passed=False,
            required_checks_passed=False,
            agent_succeeded=True,
        ),
    ))

    assert result.action == "stop"
    assert result.reason == "hard cost budget exhausted"
    assert "hard_budget_guard" in result.signals


def test_repeated_failure_still_circuit_breaks_before_material_token_cap():
    engine = make_engine()
    route = engine.route(request())

    result = engine.reassess(ReassessRequest(
        route=route,
        progress=ExecutionProgress(
            input_tokens=2_274_574,
            failure_fingerprints=["same", "same", "same"],
            progress_markers=["same", "same", "same"],
            tests_passed=False,
            required_checks_passed=False,
            agent_succeeded=False,
            last_agent_failure_kind="deterministic_failure",
        ),
    ))

    assert result.action in {"escalate", "stop"}
    assert any(signal.startswith("repeated_failure:") for signal in result.signals)


def test_profile_prior_above_configured_hard_cap_fails_closed():
    engine = make_engine()
    engine.policy["adaptive_budget"]["dimensions"]["max_input_tokens"]["hard_max"] = 1

    with pytest.raises(RuntimeError, match="exceeds configured hard_max"):
        engine.route(request())
