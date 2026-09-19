from app.config import clear_config_cache, get_config
from app.engine_budget import RouterEngine
from app.schemas import ExecutionProgress, ReassessRequest, RoutingRequest


def make_engine() -> RouterEngine:
    clear_config_cache()
    return RouterEngine(get_config())


def base_request() -> RoutingRequest:
    return RoutingRequest(**{
        "job_id": "job-final-budget",
        "project_id": "default",
        "repository": "repo",
        "source_commit": "abcd1234",
        "task": {
            "title": "Small bounded code change",
            "task_type": "bugfix",
            "semantic": {
                "ambiguity": 10,
                "architecture_impact": 5,
                "verification_difficulty": 10,
                "risk": 5,
                "context_requirement": 10,
                "novelty": 5,
                "reasoning_requirement": 15,
            },
        },
        "repo": {
            "estimated_files": 1,
            "affected_components": 1,
            "dependency_depth": 1,
            "tests_available": True,
            "existing_pattern": True,
        },
    })


def green_progress(**updates) -> ExecutionProgress:
    values = {
        "tests_passed": True,
        "required_checks_passed": True,
        "agent_succeeded": True,
    }
    values.update(updates)
    return ExecutionProgress(**values)


def test_success_on_final_model_call_is_accepted():
    engine = make_engine()
    route = engine.route(base_request())
    result = engine.reassess(ReassessRequest(
        route=route,
        progress=green_progress(model_calls=route.strategy.budget.max_model_calls),
    ))
    assert result.action == "complete"


def test_true_model_call_overrun_stops_even_when_checks_are_green():
    engine = make_engine()
    route = engine.route(base_request())
    result = engine.reassess(ReassessRequest(
        route=route,
        progress=green_progress(model_calls=route.strategy.budget.max_model_calls + 1),
    ))
    assert result.action == "stop"
    assert "exceeded" in result.reason


def test_completed_indivisible_call_accepts_input_token_overrun():
    engine = make_engine()
    route = engine.route(base_request())
    result = engine.reassess(ReassessRequest(
        route=route,
        progress=green_progress(input_tokens=route.strategy.budget.max_input_tokens + 270_184),
    ))
    assert result.action == "complete"
    assert "post_call_token_overrun:input_tokens" in result.signals


def test_completed_indivisible_call_accepts_output_token_overrun():
    engine = make_engine()
    route = engine.route(base_request())
    result = engine.reassess(ReassessRequest(
        route=route,
        progress=green_progress(output_tokens=route.strategy.budget.max_output_tokens + 172),
    ))
    assert result.action == "complete"
    assert "post_call_token_overrun:output_tokens" in result.signals


def test_token_overrun_still_stops_when_definition_of_done_is_incomplete():
    engine = make_engine()
    route = engine.route(base_request())
    result = engine.reassess(ReassessRequest(
        route=route,
        progress=ExecutionProgress(
            input_tokens=route.strategy.budget.max_input_tokens + 1,
            tests_passed=False,
            required_checks_passed=False,
            agent_succeeded=True,
        ),
    ))
    assert result.action == "stop"
    assert "input-token budget exceeded" in result.reason


def test_token_overrun_does_not_mask_other_hard_overrun():
    engine = make_engine()
    route = engine.route(base_request())
    result = engine.reassess(ReassessRequest(
        route=route,
        progress=green_progress(
            input_tokens=route.strategy.budget.max_input_tokens + 1,
            model_calls=route.strategy.budget.max_model_calls + 1,
        ),
    ))
    assert result.action == "stop"


def test_dynamic_human_decision_precedes_automatic_completion():
    engine = make_engine()
    route = engine.route(base_request())
    result = engine.reassess(ReassessRequest(
        route=route,
        progress=green_progress(important_decision_flags=["architecture_choice"]),
    ))
    assert result.action == "human_decision"
    assert result.human_decision is not None
    assert "architecture_choice" in result.human_decision.triggers


def test_dynamic_human_decision_still_precedes_completion_with_token_overrun():
    engine = make_engine()
    route = engine.route(base_request())
    result = engine.reassess(ReassessRequest(
        route=route,
        progress=green_progress(
            input_tokens=route.strategy.budget.max_input_tokens + 1,
            important_decision_flags=["architecture_choice"],
        ),
    ))
    assert result.action == "human_decision"

def test_provider_failover_prior_overrun_does_not_stop_healthy_incomplete_work():
    engine = make_engine()
    route = engine.route(base_request())
    result = engine.reassess(ReassessRequest(
        route=route,
        progress=ExecutionProgress(
            provider_failovers=route.strategy.budget.max_provider_failovers + 3,
            agent_succeeded=True,
            material_change_present=True,
            tests_passed=False,
            required_checks_passed=False,
        ),
    ))

    assert result.action == "continue"
    assert result.remaining["provider_failovers"] == 0


def test_provider_failover_prior_overrun_does_not_block_completed_work():
    engine = make_engine()
    route = engine.route(base_request())
    result = engine.reassess(ReassessRequest(
        route=route,
        progress=green_progress(
            provider_failovers=route.strategy.budget.max_provider_failovers + 3,
            material_change_present=True,
        ),
    ))

    assert result.action == "complete"
    assert result.remaining["provider_failovers"] == 0

def test_adaptive_work_shape_overruns_do_not_stop_healthy_incomplete_work():
    engine = make_engine()
    route = engine.route(base_request())
    route.strategy.budget_mode = "adaptive"
    budget = route.strategy.budget

    result = engine.reassess(ReassessRequest(
        route=route,
        progress=ExecutionProgress(
            model_calls=budget.max_model_calls + 5,
            tool_calls=budget.max_tool_calls + 20,
            iteration=budget.max_iterations + 3,
            repair_iterations=budget.max_repair_iterations + 2,
            test_runs=budget.max_test_runs + 4,
            model_failovers=budget.max_model_failovers + 2,
            agent_succeeded=True,
            material_change_present=True,
            tests_passed=False,
            required_checks_passed=False,
        ),
    ))

    assert result.action in {"continue", "escalate"}
    assert "hard_budget_guard" not in result.signals
    assert "hard_budget_overrun" not in result.signals


def test_adaptive_material_input_ceiling_still_stops_incomplete_work():
    engine = make_engine()
    route = engine.route(base_request())
    route.strategy.budget_mode = "adaptive"

    result = engine.reassess(ReassessRequest(
        route=route,
        progress=ExecutionProgress(
            input_tokens=route.strategy.budget.max_input_tokens,
            agent_succeeded=True,
            material_change_present=True,
            tests_passed=False,
            required_checks_passed=False,
        ),
    ))

    assert result.action == "stop"
    assert result.reason == "input-token budget exhausted"
    assert "hard_budget_guard" in result.signals


def test_adaptive_work_shape_overrun_does_not_mask_scope_expansion():
    engine = make_engine()
    route = engine.route(base_request())
    route.strategy.budget_mode = "adaptive"
    budget = route.strategy.budget

    result = engine.reassess(ReassessRequest(
        route=route,
        progress=ExecutionProgress(
            model_calls=budget.max_model_calls + 2,
            iteration=budget.max_iterations + 1,
            repair_iterations=budget.max_repair_iterations + 1,
            changed_files=budget.max_changed_files + 1,
            unexpected_scope=True,
            agent_succeeded=True,
            material_change_present=True,
            tests_passed=False,
            required_checks_passed=False,
        ),
    ))

    assert "scope_expansion" in result.signals
    assert result.action in {"escalate", "stop"}
    assert "hard_budget_guard" not in result.signals
    assert "hard_budget_overrun" not in result.signals

