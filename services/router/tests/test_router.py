from __future__ import annotations

from app.config import clear_config_cache, get_config
from app.engine import RouterEngine
from app.schemas import ExecutionProgress, ReassessRequest, RoutingRequest


def make_engine() -> RouterEngine:
    clear_config_cache()
    return RouterEngine(get_config())


def base_request(**overrides):
    data = {
        "job_id": "job-1",
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
    }
    for key, value in overrides.items():
        data[key] = value
    return RoutingRequest(**data)


def complex_request(**overrides):
    data = {
        "task": {
            "title": "Debug cross-module external API synchronization",
            "task_type": "debugging",
            "semantic": {
                "ambiguity": 60,
                "architecture_impact": 45,
                "verification_difficulty": 65,
                "risk": 45,
                "context_requirement": 75,
                "novelty": 55,
                "reasoning_requirement": 85,
            },
        },
        "repo": {
            "estimated_files": 10,
            "affected_components": 4,
            "dependency_depth": 6,
            "tests_available": True,
            "existing_pattern": False,
            "external_api": True,
        },
    }
    data.update(overrides)
    return base_request(**data)


def test_fast_routes_to_low_cost_agent():
    result = make_engine().route(base_request())
    assert result.strategy.profile == "fast"
    assert result.strategy.executor.id in {"antigravity_free", "codex_luna", "codex_terra"}
    assert result.strategy.executor.id != "codex_sol"
    assert result.strategy.planner is None
    assert result.strategy.evaluator is None
    assert result.strategy.human_decision.required is False


def test_standard_is_autonomous_and_does_not_default_to_sol():
    req = base_request(
        task={
            "title": "Implement a normal multi-file feature",
            "task_type": "feature",
            "semantic": {
                "ambiguity": 35,
                "architecture_impact": 20,
                "verification_difficulty": 35,
                "risk": 20,
                "context_requirement": 45,
                "novelty": 35,
                "reasoning_requirement": 50,
            },
        },
        repo={
            "estimated_files": 6,
            "affected_components": 2,
            "dependency_depth": 3,
            "tests_available": True,
            "existing_pattern": True,
        },
    )
    result = make_engine().route(req)
    assert result.strategy.profile == "standard"
    assert result.strategy.executor.id in {"antigravity_free", "codex_luna", "codex_terra"}
    assert result.strategy.executor.id != "codex_sol"
    assert result.strategy.human_decision.required is False
    assert result.strategy.permissions["commit"] is True
    assert result.strategy.permissions["push_ai_branch"] is True


def test_codex_reasoning_effort_is_explicit_and_bounded_by_profile():
    eng = make_engine()
    fast = eng.route(base_request(provider_state={
        "provider:google_antigravity": {"healthy": False, "available": False}
    }))
    assert fast.strategy.executor.adapter == "codex_cli"
    assert fast.strategy.executor.reasoning_effort == "low"
    assert fast.strategy.reasoning_ceiling["executor"] == "low"

    complex_route = eng.route(complex_request(provider_state={
        "provider:google_antigravity": {"healthy": False, "available": False}
    }))
    assert complex_route.strategy.executor.adapter == "codex_cli"
    assert complex_route.strategy.executor.reasoning_effort == "medium"
    assert complex_route.strategy.reasoning_ceiling["executor"] == "high"
    assert complex_route.strategy.planner is not None
    assert complex_route.strategy.planner.reasoning_effort == "medium"
    assert complex_route.strategy.evaluator is not None
    assert complex_route.strategy.evaluator.reasoning_effort == "low"


def test_complex_gets_planner_and_independent_evaluator_without_claude():
    result = make_engine().route(complex_request())
    assert result.strategy.profile in {"complex", "critical"}
    assert result.strategy.planner is not None
    assert result.strategy.evaluator is not None
    assert result.strategy.evaluator.provider != result.strategy.executor.provider
    assert result.strategy.evaluator.id != "claude_sonnet"


def test_evaluator_provider_failure_has_degraded_but_eligible_fallback():
    eng = make_engine()
    initial = eng.route(complex_request())
    assert initial.strategy.evaluator is not None
    failed_provider = initial.strategy.evaluator.provider

    rerouted = eng.route(complex_request(provider_state={
        f"provider:{failed_provider}": {
            "healthy": False,
            "available": False,
            "error_rate": 1.0,
        }
    }))

    assert rerouted.strategy.evaluator is not None
    assert rerouted.strategy.evaluator.provider != failed_provider
    # With only two configured coding providers, losing the independent evaluator
    # may force a same-provider reviewer. That is preferable to blocking while
    # still preserving a separate evaluation turn and model policy.
    assert rerouted.strategy.evaluator.id in {"antigravity_free", "codex_terra"}


def test_reassess_raises_reasoning_before_changing_codex_model():
    eng = make_engine()
    route = eng.route(complex_request(provider_state={
        "provider:google_antigravity": {"healthy": False, "available": False}
    }))
    assert route.strategy.executor.id == "codex_terra"
    assert route.strategy.executor.reasoning_effort == "medium"

    result = eng.reassess(ReassessRequest(
        route=route,
        progress=ExecutionProgress(
            iteration=2,
            repair_iterations=1,
            agent_succeeded=False,
            last_agent_failure_kind="no_effect",
        ),
    ))

    assert result.action == "escalate"
    assert result.next_executor is not None
    assert result.next_executor.id == "codex_terra"
    assert result.next_executor.reasoning_effort == "high"
    assert "reasoning_effort_escalation" in result.signals


def test_auth_change_is_critical_and_human_decision():
    req = base_request(
        task={
            "title": "Change authentication session semantics",
            "task_type": "security",
            "flags": ["security_boundary_change"],
        },
        repo={
            "estimated_files": 4,
            "affected_components": 2,
            "dependency_depth": 3,
            "authentication_change": True,
            "security_sensitive": True,
        },
    )
    result = make_engine().route(req)
    assert result.strategy.profile == "critical"
    assert result.strategy.executor.id == "codex_sol"
    assert result.strategy.executor.reasoning_effort == "high"
    assert result.strategy.planner is not None
    assert result.strategy.planner.id == "codex_sol"
    assert result.strategy.planner.reasoning_effort == "high"
    assert result.strategy.evaluator is not None
    assert result.strategy.evaluator.provider != "openai"
    assert result.strategy.human_decision.required is True
    assert "security_boundary_change" in result.strategy.human_decision.triggers


def test_optional_paid_agents_are_fail_closed_until_roles_are_enabled():
    result = make_engine().route(base_request())
    for model_id in {"deepseek_flash", "groq_oss_120b", "frontier_codex"}:
        assert model_id in result.rejected_candidates
        assert any("missing required role" in reason for reason in result.rejected_candidates[model_id])


def test_private_project_rejects_training_provider():
    result = make_engine().route(base_request())
    assert "openrouter_free" in result.rejected_candidates
    assert any("train" in reason for reason in result.rejected_candidates["openrouter_free"])


def test_reassess_completes_on_definition_of_done():
    eng = make_engine()
    route = eng.route(base_request())
    result = eng.reassess(
        ReassessRequest(
            route=route,
            progress=ExecutionProgress(tests_passed=True, required_checks_passed=True, agent_succeeded=True),
        )
    )
    assert result.action == "complete"


def test_reassess_hard_budget_stops():
    eng = make_engine()
    route = eng.route(base_request())
    progress = ExecutionProgress(model_calls=route.strategy.budget.max_model_calls)
    result = eng.reassess(ReassessRequest(route=route, progress=progress))
    assert result.action == "stop"
    assert "budget" in result.reason


def test_repeated_failure_escalates_or_stops_but_never_loops():
    eng = make_engine()
    req = base_request(
        task={
            "title": "Normal bug",
            "semantic": {
                "ambiguity": 35,
                "architecture_impact": 20,
                "verification_difficulty": 35,
                "risk": 20,
                "context_requirement": 45,
                "novelty": 35,
                "reasoning_requirement": 50,
            },
        },
        repo={
            "estimated_files": 6,
            "affected_components": 2,
            "dependency_depth": 3,
            "tests_available": True,
        },
    )
    route = eng.route(req)
    progress = ExecutionProgress(
        iteration=3,
        repair_iterations=1,
        failure_fingerprints=["same", "same", "same"],
    )
    result = eng.reassess(ReassessRequest(route=route, progress=progress))
    assert result.action in {"escalate", "stop"}


def test_reassess_token_budget_stops():
    eng = make_engine()
    route = eng.route(base_request())
    progress = ExecutionProgress(
        input_tokens=route.strategy.budget.max_input_tokens,
        output_tokens=0,
    )
    result = eng.reassess(ReassessRequest(route=route, progress=progress))
    assert result.action == "stop"
    assert "input-token budget" in result.reason


def test_material_change_task_cannot_complete_with_empty_diff():
    eng = make_engine()
    req = base_request(task={
        "title": "Add a regression test",
        "task_type": "test",
        "flags": ["material_change_required"],
        "semantic": {
            "ambiguity": 10, "architecture_impact": 5, "verification_difficulty": 10,
            "risk": 5, "context_requirement": 10, "novelty": 5, "reasoning_requirement": 15,
        },
    })
    route = eng.route(req)
    assert "material_change" in route.strategy.definition_of_done["required"]
    result = eng.reassess(ReassessRequest(
        route=route,
        progress=ExecutionProgress(
            tests_passed=True, required_checks_passed=True, agent_succeeded=True,
            material_change_present=False, changed_files=0,
        ),
    ))
    assert result.action != "complete"
    assert any("material_change_missing" in signal for signal in result.signals)


def test_provider_level_unavailable_excludes_same_provider_models():
    eng = make_engine()
    req = base_request(provider_state={
        "provider:openai": {"healthy": False, "available": False, "quota_pressure": 1.0}
    })
    result = eng.route(req)
    assert result.strategy.executor.provider != "openai"
    assert "codex_luna" in result.rejected_candidates
    assert "codex_terra" in result.rejected_candidates
    assert "codex_sol" in result.rejected_candidates
    assert "frontier_codex" in result.rejected_candidates


def test_model_level_unavailable_reroutes_without_disabling_provider():
    eng = make_engine()
    initial = eng.route(base_request())
    model_id = initial.strategy.executor.id
    provider = initial.strategy.executor.provider
    req = base_request(provider_state={model_id: {"healthy": False, "available": False}})
    rerouted = eng.route(req)
    assert rerouted.strategy.executor.id != model_id
    assert model_id in rerouted.rejected_candidates
    assert any('unavailable' in reason for reason in rerouted.rejected_candidates[model_id])
    assert provider
