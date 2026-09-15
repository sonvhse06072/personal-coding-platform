from app.config import clear_config_cache, get_config
from app.schemas import RoutingRequest
from app.staffing import RouterEngine


OPENROUTER = "openrouter_qwen3_coder_free"


def engine() -> RouterEngine:
    clear_config_cache()
    return RouterEngine(get_config())


def standard_request(**overrides) -> RoutingRequest:
    data = {
        "job_id": "openrouter-standard",
        "project_id": "default",
        "repository": "repo",
        "source_commit": "abcd1234",
        "task": {
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
        "repo": {
            "estimated_files": 6,
            "affected_components": 2,
            "dependency_depth": 3,
            "tests_available": True,
            "existing_pattern": True,
        },
    }
    data.update(overrides)
    return RoutingRequest(**data)


def test_healthy_standard_route_prefers_openrouter():
    result = engine().route(standard_request())

    assert result.strategy.profile == "standard"
    assert result.strategy.executor.id == OPENROUTER
    assert result.strategy.executor.provider == "openrouter"
    assert result.strategy.executor.adapter == "opencode"


def test_standard_route_falls_back_when_openrouter_provider_is_unavailable():
    result = engine().route(standard_request(provider_state={
        "provider:openrouter": {
            "healthy": False,
            "available": False,
            "error_rate": 1.0,
        }
    }))

    assert result.strategy.profile == "standard"
    assert result.strategy.executor.id != OPENROUTER
    assert result.strategy.executor.provider != "openrouter"
    assert "provider/model unavailable" in result.rejected_candidates[OPENROUTER]


def test_standard_route_falls_back_when_openrouter_model_is_unhealthy():
    result = engine().route(standard_request(provider_state={
        OPENROUTER: {
            "healthy": False,
            "available": False,
            "error_rate": 1.0,
        }
    }))

    assert result.strategy.profile == "standard"
    assert result.strategy.executor.id != OPENROUTER
    assert OPENROUTER in result.rejected_candidates


def test_training_disallowed_privacy_policy_rejects_openrouter():
    result = engine().route(standard_request(privacy={
        "private_code": True,
        "allow_training_provider": False,
        "require_zero_retention": False,
    }))

    assert result.strategy.profile == "standard"
    assert result.strategy.executor.id != OPENROUTER
    assert "provider may train on data" in result.rejected_candidates[OPENROUTER]


def test_openrouter_quota_pressure_can_yield_to_healthy_fallback():
    result = engine().route(standard_request(provider_state={
        "quota:openrouter_free": {
            "healthy": True,
            "available": True,
            "quota_pressure": 1.0,
        }
    }))

    assert result.strategy.profile == "standard"
    assert result.strategy.executor.id != OPENROUTER


def test_critical_security_route_does_not_use_openrouter():
    request = standard_request(
        task={
            "title": "Change authentication session semantics",
            "task_type": "security",
            "flags": ["security_boundary_change"],
            "semantic": {
                "ambiguity": 40,
                "architecture_impact": 80,
                "verification_difficulty": 70,
                "risk": 90,
                "context_requirement": 70,
                "novelty": 50,
                "reasoning_requirement": 90,
            },
        },
        repo={
            "estimated_files": 4,
            "affected_components": 2,
            "dependency_depth": 3,
            "tests_available": True,
            "security_sensitive": True,
            "authentication_change": True,
        },
    )

    result = engine().route(request)

    assert result.strategy.profile == "critical"
    assert result.strategy.executor.id != OPENROUTER
    assert result.strategy.planner is not None
    assert result.strategy.planner.id != OPENROUTER
