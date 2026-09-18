from app.config import clear_config_cache, get_config
from app.schemas import ExecutionProgress, ExecutionStrategy, ReassessRequest, RoutingRequest
from app.staffing import RouterEngine


def make_engine() -> RouterEngine:
    clear_config_cache()
    return RouterEngine(get_config())


def request(*, pressure: int = 45) -> RoutingRequest:
    return RoutingRequest(**{
        "job_id": "adaptive-budget-job",
        "project_id": "default",
        "repository": "repo",
        "source_commit": "abcd1234",
        "task": {
            "title": "Verification-heavy bounded change",
            "task_type": "bugfix",
            "semantic": {
                "ambiguity": pressure,
                "architecture_impact": 20,
                "verification_difficulty": pressure,
                "risk": 25,
                "context_requirement": pressure,
                "novelty": 25,
                "reasoning_requirement": pressure,
            },
        },
        "repo": {
            "estimated_files": 4,
            "affected_components": 2,
            "dependency_depth": 2,
            "tests_available": True,
            "existing_pattern": True,
        },
    })


def test_new_routes_expose_estimate_working_target_and_emergency_ceiling():
    engine = make_engine()
    route = engine.route(request())
    adaptive = route.strategy.adaptive_budget
    assert adaptive is not None
    assert adaptive.enabled is True

    profile_cfg = engine.policy["profiles"][route.strategy.profile]
    for dimension in (
        "max_model_calls",
        "max_tool_calls",
        "max_iterations",
        "max_repair_iterations",
        "max_test_runs",
        "max_wall_time_minutes",
    ):
        envelope = adaptive.dimensions[dimension]
        assert envelope.estimate <= envelope.working_target <= envelope.emergency_limit
        assert envelope.working_target >= float(profile_cfg[dimension])
        # The emergency value is a stable high-water threshold. Effective
        # WorkOrder budget_mode decides whether that dimension is a material stop
        # or adaptive work-shape telemetry.
        assert float(getattr(route.strategy.budget, dimension)) == envelope.emergency_limit


def test_task_pressure_increases_effort_pressure_and_estimated_capacity():
    engine = make_engine()
    low = engine.route(request(pressure=10))
    high = engine.route(request(pressure=90))
    low_budget = low.strategy.adaptive_budget
    high_budget = high.strategy.adaptive_budget
    assert low_budget is not None and high_budget is not None
    assert high_budget.effort_pressure > low_budget.effort_pressure
    # Higher semantic pressure may legitimately cross a profile boundary; the
    # adaptive estimate should still increase rather than relying on one fixed
    # profile-shaped ceiling.
    assert (
        high_budget.dimensions["max_test_runs"].estimate
        > low_budget.dimensions["max_test_runs"].estimate
    )


def test_effective_adaptive_work_shape_emergency_threshold_is_non_blocking():
    engine = make_engine()
    route = engine.route(request())
    route.strategy.budget_mode = "adaptive"
    adaptive = route.strategy.adaptive_budget
    assert adaptive is not None
    repair = adaptive.dimensions["max_repair_iterations"]

    within_headroom = engine.reassess(ReassessRequest(
        route=route,
        progress=ExecutionProgress(
            repair_iterations=int(repair.working_target),
            tests_passed=False,
            required_checks_passed=False,
            agent_succeeded=True,
        ),
    ))
    assert within_headroom.action != "stop"
    assert "budget_headroom_active:max_repair_iterations" in within_headroom.signals

    emergency = engine.reassess(ReassessRequest(
        route=route,
        progress=ExecutionProgress(
            repair_iterations=int(repair.emergency_limit),
            tests_passed=False,
            required_checks_passed=False,
            agent_succeeded=True,
        ),
    ))
    assert emergency.action != "stop"
    assert "budget_emergency_threshold_reached:max_repair_iterations" in emergency.signals
    assert "hard_budget_guard" not in emergency.signals


def test_non_blocking_budget_signals_do_not_force_reasoning_escalation():
    engine = make_engine()
    route = engine.route(request())
    adaptive = route.strategy.adaptive_budget
    assert adaptive is not None
    repair = adaptive.dimensions["max_repair_iterations"]

    result = engine.reassess(ReassessRequest(
        route=route,
        progress=ExecutionProgress(
            repair_iterations=int(repair.working_target),
            tests_passed=False,
            required_checks_passed=False,
            agent_succeeded=True,
        ),
    ))
    assert "budget_headroom_active:max_repair_iterations" in result.signals
    assert "reasoning_effort_escalation" not in result.signals


def test_legacy_strategy_without_adaptive_metadata_keeps_hard_profile_limit():
    engine = make_engine()
    route = engine.route(request())
    payload = route.strategy.model_dump(mode="json")
    payload.pop("adaptive_budget", None)
    baseline = engine.policy["profiles"][route.strategy.profile]
    payload["budget"]["max_repair_iterations"] = baseline["max_repair_iterations"]
    legacy = ExecutionStrategy(**payload)
    route.strategy = legacy

    result = engine.reassess(ReassessRequest(
        route=route,
        progress=ExecutionProgress(
            repair_iterations=baseline["max_repair_iterations"],
            tests_passed=False,
            required_checks_passed=False,
            agent_succeeded=True,
        ),
    ))
    assert result.action == "stop"
    assert result.reason == "repair budget exhausted"
    assert legacy.adaptive_budget is None


def test_abnormal_repeated_failure_is_not_hidden_by_budget_headroom():
    engine = make_engine()
    route = engine.route(request())
    adaptive = route.strategy.adaptive_budget
    assert adaptive is not None
    repair = adaptive.dimensions["max_repair_iterations"]

    result = engine.reassess(ReassessRequest(
        route=route,
        progress=ExecutionProgress(
            repair_iterations=int(repair.working_target),
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
