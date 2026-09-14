from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.config import clear_config_cache, get_config
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
    assert result.choice.id in {"codex_terra", "antigravity_free"}
    assert result.choice.id != "codex_sol"
    if result.choice.adapter == "codex_cli":
        assert result.choice.reasoning_effort == "low"
    assert "product_manager" in engine.models[result.choice.id]["roles"]
    assert result.policy_version == 5
    assert result.registry_version == 5


def test_product_manager_staffing_respects_provider_availability() -> None:
    engine = make_engine()
    result = engine.staff(
        pm_request(provider_state={"codex_terra": {"available": False}})
    )

    assert result.choice.id == "antigravity_free"
    assert result.choice.reasoning_effort is None
    assert "provider/model unavailable" in result.rejected_candidates["codex_terra"]


def test_product_manager_staffing_can_fall_back_to_sol_when_lower_cost_capacity_is_unavailable() -> None:
    engine = make_engine()
    result = engine.staff(
        pm_request(
            provider_state={
                "codex_terra": {"available": False},
                "antigravity_free": {"available": False},
            }
        )
    )

    assert result.choice.id == "codex_sol"
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
