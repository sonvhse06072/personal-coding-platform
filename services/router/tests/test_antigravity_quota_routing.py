from __future__ import annotations

import pytest

from app.config import clear_config_cache, get_config
from app.schemas import ProviderState, RoutingRequest
from app.staffing import RouterEngine


def make_engine() -> RouterEngine:
    clear_config_cache()
    return RouterEngine(get_config())


def standard_request(provider_state=None) -> RoutingRequest:
    return RoutingRequest(
        job_id="job-antigravity",
        project_id="default",
        repository="repo",
        source_commit="abcd1234",
        task={
            "title": "Implement a normal bounded feature",
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
        provider_state=provider_state or {},
    )


def unavailable() -> ProviderState:
    return ProviderState(healthy=False, available=False, error_rate=1.0)


def test_registry_exposes_explicit_antigravity_models_and_quota_groups():
    cfg = get_config()["models"]
    models = cfg["models"]

    assert cfg["version"] == 8
    assert models["antigravity_free"]["model"] == "gemini-3.8-flash-medium"
    assert models["antigravity_flash_high"]["model"] == "gemini-3.8-flash-high"
    assert models["antigravity_gemini_pro"]["model"] == "gemini-3.1-pro-high"
    assert models["antigravity_claude_sonnet"]["model"] == "claude-sonnet-4-6"
    assert models["antigravity_free"]["quota_group"] == "antigravity_gemini"
    assert models["antigravity_gemini_pro"]["quota_group"] == "antigravity_gemini"
    assert models["antigravity_claude_sonnet"]["quota_group"] == "antigravity_claude_gpt"


def test_standard_route_applies_reasoning_effort_to_antigravity():
    request = standard_request(
        {
            "provider:openai": unavailable(),
            "provider:openrouter": unavailable(),
        }
    )

    result = make_engine().route(request)

    assert result.strategy.profile == "standard"
    assert result.strategy.executor.provider == "google_antigravity"
    assert result.strategy.executor.id == "antigravity_free"
    assert result.strategy.executor.model == "gemini-3.8-flash-medium"
    assert result.strategy.executor.quota_group == "antigravity_gemini"
    assert result.strategy.executor.reasoning_effort == "low"


def test_gemini_quota_exhaustion_can_fall_through_to_sonnet_bucket():
    request = standard_request(
        {
            "provider:openai": unavailable(),
            "provider:openrouter": unavailable(),
            "quota:antigravity_gemini": unavailable(),
        }
    )
    engine = make_engine()
    dimensions = engine.compute_dimensions(request)

    choice, rejected = engine.select_model(
        role="executor",
        role_names=["executor"],
        preferred_ids=["antigravity_free", "antigravity_claude_sonnet"],
        request=request,
        dimensions=dimensions,
        profile="standard",
    )

    assert choice.id == "antigravity_claude_sonnet"
    assert choice.quota_group == "antigravity_claude_gpt"
    assert "antigravity_free" in rejected
    assert "provider/model unavailable" in rejected["antigravity_free"]
    assert "antigravity_gemini_pro" in rejected



def test_near_exhausted_gemini_quota_falls_through_to_sonnet_bucket():
    request = standard_request(
        {
            "provider:openai": unavailable(),
            "provider:openrouter": unavailable(),
            "quota:antigravity_gemini": ProviderState(
                quota_pressure=0.99912,
                available=True,
            ),
        }
    )
    engine = make_engine()
    dimensions = engine.compute_dimensions(request)

    choice, rejected = engine.select_model(
        role="executor",
        role_names=["executor"],
        preferred_ids=["antigravity_free", "antigravity_claude_sonnet"],
        request=request,
        dimensions=dimensions,
        profile="standard",
    )

    assert choice.id == "antigravity_claude_sonnet"
    assert choice.quota_group == "antigravity_claude_gpt"
    assert "antigravity_free" in rejected
    assert any(
        "quota pressure at/above routing reserve threshold" in reason
        for reason in rejected["antigravity_free"]
    )


def test_quota_pressure_below_reserve_threshold_remains_eligible():
    request = standard_request(
        {
            "provider:openai": unavailable(),
            "provider:openrouter": unavailable(),
            "quota:antigravity_gemini": ProviderState(
                quota_pressure=0.98,
                available=True,
            ),
        }
    )
    engine = make_engine()
    dimensions = engine.compute_dimensions(request)

    choice, rejected = engine.select_model(
        role="executor",
        role_names=["executor"],
        preferred_ids=["antigravity_free", "antigravity_claude_sonnet"],
        request=request,
        dimensions=dimensions,
        profile="standard",
    )

    assert choice.id == "antigravity_free"
    assert "antigravity_free" not in rejected
    assert any("quota penalty=" in reason for reason in choice.reasons)


def test_provider_wide_antigravity_failure_excludes_every_antigravity_bucket():
    request = standard_request(
        {
            "provider:openai": unavailable(),
            "provider:openrouter": unavailable(),
            "provider:google_antigravity": unavailable(),
        }
    )
    engine = make_engine()
    dimensions = engine.compute_dimensions(request)

    with pytest.raises(RuntimeError, match="No eligible model"):
        engine.select_model(
            role="executor",
            role_names=["executor"],
            preferred_ids=["antigravity_free", "antigravity_claude_sonnet"],
            request=request,
            dimensions=dimensions,
            profile="standard",
        )
