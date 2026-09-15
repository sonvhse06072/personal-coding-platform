from __future__ import annotations

from app.config import clear_config_cache, get_config
from app.engine_review import RouterEngine
from app.schemas import RoutingRequest


def make_engine() -> RouterEngine:
    clear_config_cache()
    return RouterEngine(get_config())


def request(*, sample_size: int | None = None, multiplier: float = 1.0) -> RoutingRequest:
    calibration = None
    if sample_size is not None:
        calibration = {
            "sample_size": sample_size,
            "minimum_sample_size": 5,
            "resource_multipliers": {"max_model_calls": multiplier},
            "source": "project_task_role_history",
        }
    return RoutingRequest(
        job_id=f"job-{sample_size}",
        project_id="default",
        repository="repo",
        source_commit="abcd1234",
        task={
            "title": "Small bounded change",
            "task_type": "test",
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
        repo={
            "estimated_files": 1,
            "affected_components": 1,
            "dependency_depth": 1,
            "tests_available": True,
            "existing_pattern": True,
        },
        calibration=calibration,
    )


def estimate(route) -> float:
    assert route.strategy.adaptive_budget is not None
    return route.strategy.adaptive_budget.dimensions["max_model_calls"].estimate


def test_sparse_history_falls_back_to_existing_policy_estimate() -> None:
    engine = make_engine()
    baseline = engine.route(request())
    sparse = engine.route(request(sample_size=4, multiplier=1.75))

    assert estimate(sparse) == estimate(baseline)
    assert not any("Observed project/task/role calibration applied" in reason for reason in sparse.strategy.reasons)


def test_meaningful_history_adjusts_estimate_but_not_emergency_hard_cap() -> None:
    engine = make_engine()
    baseline = engine.route(request())
    calibrated = engine.route(request(sample_size=5, multiplier=1.75))

    assert estimate(calibrated) > estimate(baseline)
    assert any("Observed project/task/role calibration applied from 5 comparable terminal jobs" in reason for reason in calibrated.strategy.reasons)
    assert calibrated.strategy.budget.max_model_calls <= 40
    adaptive = calibrated.strategy.adaptive_budget
    assert adaptive is not None
    envelope = adaptive.dimensions["max_model_calls"]
    assert envelope.estimate <= envelope.working_target <= envelope.emergency_limit <= 40


def test_calibration_multiplier_is_clamped_by_router_policy() -> None:
    engine = make_engine()
    huge = engine.route(request(sample_size=20, multiplier=99.0))
    bounded = engine.route(request(sample_size=20, multiplier=1.75))

    assert estimate(huge) == estimate(bounded)
