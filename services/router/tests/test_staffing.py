from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.config import clear_config_cache, get_config
from app.model_capabilities import reasoning_capability
from app.schemas import StaffingRequest
from app.staffing import RouterEngine


def make_engine() -> RouterEngine:
    clear_config_cache()
    return RouterEngine(get_config())


def pm_request(**overrides) -> StaffingRequest:
    data = {
        "request_id": "pm-plan-1",
        "project_id": "default",
        "role": "product_manager",
        "profile": "standard",
        "semantic": {
            "ambiguity": 45,
            "architecture_impact": 35,
            "verification_difficulty": 20,
            "risk": 30,
            "context_requirement": 60,
            "novelty": 35,
            "reasoning_requirement": 80,
        },
    }
    data.update(overrides)
    return StaffingRequest(**data)


def test_product_manager_staffing_selects_only_pm_eligible_agent() -> None:
    engine = make_engine()
    result = engine.staff(pm_request())

    assert result.role == "product_manager"
    assert result.profile == "standard"
    assert result.choice.id in {
        "codex_gpt6_sol",
        "codex_terra",
        "antigravity_free",
        "antigravity_gemini_pro",
        "antigravity_claude_sonnet",
    }
    assert result.choice.id != "codex_sol"
    capability = reasoning_capability(result.choice.id, engine.models[result.choice.id])
    assert result.choice.reasoning_effort == (
        "low" if capability.supports_explicit_effort else None
    )
    assert "product_manager" in engine.models[result.choice.id]["roles"]
    assert result.policy_version == 21
    assert result.registry_version == 13


def test_product_manager_staffing_respects_provider_availability_and_model_effort_capability() -> None:
    engine = make_engine()
    result = engine.staff(
        pm_request(provider_state={"provider:openai": {"available": False}})
    )

    assert result.choice.provider == "google_antigravity"
    capability = reasoning_capability(result.choice.id, engine.models[result.choice.id])
    assert result.choice.reasoning_effort == (
        "low" if capability.supports_explicit_effort else None
    )
    assert result.choice.quota_group in {"antigravity_gemini", "antigravity_claude_gpt"}


def test_product_manager_staffing_prefers_current_gpt6_sol_when_antigravity_is_unavailable() -> None:
    engine = make_engine()
    result = engine.staff(
        pm_request(
            provider_state={
                "codex_terra": {"available": False},
                "quota:antigravity_gemini": {"available": False, "healthy": False},
                "quota:antigravity_claude_gpt": {"available": False, "healthy": False},
            }
        )
    )

    assert result.choice.id == "codex_gpt6_sol"
    assert result.choice.model == "gpt-6-sol"
    assert result.choice.reasoning_effort == "low"


def test_unknown_staffing_role_and_disallowed_profile_fail_closed() -> None:
    engine = make_engine()

    with pytest.raises(RuntimeError, match="Unknown or unconfigured logical role"):
        engine.staff(pm_request(role="architect_invented"))

    with pytest.raises(RuntimeError, match="is not allowed"):
        engine.staff(pm_request(profile="fast"))


def test_staffing_request_forbids_direct_model_or_provider_selection() -> None:
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        StaffingRequest(
            request_id="pm-plan-1",
            project_id="default",
            role="product_manager",
            profile="standard",
            model_id="codex_sol",
        )

    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        StaffingRequest(
            request_id="pm-plan-2",
            project_id="default",
            role="product_manager",
            profile="standard",
            provider="openai",
        )


def test_staffing_keeps_project_privacy_policy_authoritative() -> None:
    engine = make_engine()
    result = engine.staff(pm_request())

    assert "openrouter_qwen3_coder_free" in result.rejected_candidates
    assert any(
        "missing required role" in reason
        for reason in result.rejected_candidates["openrouter_qwen3_coder_free"]
    )


def test_unconfigured_optional_agents_are_not_staffable() -> None:
    engine = make_engine()
    result = engine.staff(pm_request())
    for model_id in {"groq_oss_120b", "deepseek_flash", "frontier_codex"}:
        assert model_id in result.rejected_candidates
        assert any("missing required role" in reason for reason in result.rejected_candidates[model_id])


def test_product_manager_staffing_can_exclude_primary_developer_model() -> None:
    engine = make_engine()
    first = engine.staff(pm_request())

    second = engine.staff(
        pm_request(
            request_id="pm-plan-separated",
            exclude_model_ids=[first.choice.id],
        )
    )

    assert second.choice.id != first.choice.id
    assert first.choice.id in second.rejected_candidates
    assert any(
        "model excluded for role separation" in reason
        for reason in second.rejected_candidates[first.choice.id]
    )
