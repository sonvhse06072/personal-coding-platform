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
    assert result.choice.id == "codex_plus"
    assert "product_manager" in engine.models[result.choice.id]["roles"]
    assert result.policy_version == 3
    assert result.registry_version == 4


def test_product_manager_staffing_respects_provider_availability() -> None:
    engine = make_engine()
    result = engine.staff(
        pm_request(provider_state={"codex_plus": {"available": False}})
    )

    assert result.choice.id == "antigravity_free"
    assert "provider/model unavailable" in result.rejected_candidates["codex_plus"]


def test_product_manager_staffing_can_fall_back_to_premium_when_lower_cost_capacity_is_unavailable() -> None:
    engine = make_engine()
    result = engine.staff(
        pm_request(
            provider_state={
                "codex_plus": {"available": False},
                "antigravity_free": {"available": False},
            }
        )
    )

    assert result.choice.id == "claude_sonnet"


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
            model_id="claude_sonnet",
        )

    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        StaffingRequest(
            request_id="pm-plan-2",
            project_id="default",
            role="product_manager",
            profile="standard",
            provider="anthropic",
        )


def test_staffing_keeps_project_privacy_policy_authoritative() -> None:
    engine = make_engine()
    result = engine.staff(pm_request())

    # Public/training-eligible providers and non-agent utilities remain rejected;
    # StaffingRequest has no privacy override field, so callers cannot relax the
    # checked-in project privacy policy.
    assert "openrouter_free" in result.rejected_candidates
    assert any(
        "train" in reason or "not an agent" in reason
        for reason in result.rejected_candidates["openrouter_free"]
    )
