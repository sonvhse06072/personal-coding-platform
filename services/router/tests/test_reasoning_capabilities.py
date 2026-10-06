from __future__ import annotations

from copy import deepcopy

import pytest
from pydantic import ValidationError

from app.config import clear_config_cache, get_config
from app.model_capabilities import (
    REASONING_EFFORT_ORDER,
    reasoning_capability,
)
from app.schemas import (
    ExecutionProgress,
    ModelChoice,
    ReasoningEffort,
    ReassessRequest,
    StaffingRequest,
)
from app.staffing import RouterEngine
from test_router import complex_request


def make_engine() -> RouterEngine:
    clear_config_cache()
    return RouterEngine(get_config())


def choice(model_id: str, *, effort: ReasoningEffort | None) -> ModelChoice:
    model = get_config()["models"]["models"][model_id]
    return ModelChoice(
        id=model_id,
        provider=model["provider"],
        adapter=model["adapter"],
        model=model["model"],
        reasoning_effort=effort,
        score=1.0,
        predicted_success=1.0,
        reasons=[],
    )


def test_reasoning_schema_accepts_xhigh_and_max() -> None:
    assert choice("frontier_codex", effort="xhigh").reasoning_effort == "xhigh"
    assert choice("frontier_codex", effort="max").reasoning_effort == "max"


def test_reasoning_schema_rejects_unknown_value() -> None:
    with pytest.raises(ValidationError):
        choice("frontier_codex", effort="extreme")  # type: ignore[arg-type]


def test_registry_capabilities_are_per_model_and_canonically_ordered() -> None:
    models = get_config()["models"]["models"]
    assert REASONING_EFFORT_ORDER == ("low", "medium", "high", "xhigh", "max")
    for model_id in (
        "codex_gpt6_luna",
        "codex_gpt6_sol",
        "codex_gpt61_sol",
        "codex_luna",
        "codex_terra",
        "codex_sol",
        "frontier_codex",
    ):
        assert reasoning_capability(model_id, models[model_id]).allowed_efforts == (
            "low",
            "medium",
            "high",
            "xhigh",
            "max",
        )
    assert reasoning_capability(
        "antigravity_gemini_pro", models["antigravity_gemini_pro"]
    ).allowed_efforts == (
        "low",
        "medium",
        "high",
    )
    for model_id in (
        "antigravity_free",
        "antigravity_flash_high",
        "antigravity_claude_sonnet",
    ):
        assert reasoning_capability(model_id, models[model_id]).allowed_efforts == ()


def test_non_effort_antigravity_models_omit_configured_effort() -> None:
    engine = make_engine()
    for model_id in (
        "antigravity_free",
        "antigravity_flash_high",
        "antigravity_claude_sonnet",
    ):
        selected = choice(model_id, effort=None)
        engine._apply_reasoning(selected, "high")
        assert selected.reasoning_effort is None


def test_same_model_escalation_respects_capability_and_route_ceiling() -> None:
    engine = make_engine()
    codex = choice("codex_terra", effort="medium")
    boosted = engine._next_reasoning_choice(codex, "high")
    assert boosted is not None
    assert boosted.reasoning_effort == "high"
    assert engine._next_reasoning_choice(boosted, "high") is None

    antigravity = choice("antigravity_free", effort=None)
    assert engine._next_reasoning_choice(antigravity, "max") is None


def test_failover_choice_respects_new_model_without_effort_support() -> None:
    engine = make_engine()
    new_model = choice("antigravity_free", effort=None)
    engine._apply_reasoning(new_model, "max")
    assert new_model.reasoning_effort is None


def test_reassessment_model_failover_revalidates_profile_effort() -> None:
    engine = make_engine()
    engine.models = deepcopy(engine.models)
    engine.models["codex_sol"]["reasoning_efforts"] = ["high"]
    provider_state = {
        "provider:google_antigravity": {
            "healthy": False,
            "available": False,
        },
        "codex_gpt61_sol": {
            "healthy": False,
            "available": False,
        },
    }
    route = engine.route(complex_request(provider_state=provider_state))
    assert route.strategy.executor.id == "codex_gpt6_sol"
    route.strategy.executor.reasoning_effort = "high"

    with pytest.raises(RuntimeError, match="unsupported"):
        engine.reassess(
            ReassessRequest(
                route=route,
                progress=ExecutionProgress(
                    iteration=2,
                    repair_iterations=1,
                    agent_succeeded=False,
                    last_agent_failure_kind="no_effect",
                ),
                provider_state=provider_state,
            )
        )


def test_staffing_fails_closed_when_profile_effort_is_not_supported() -> None:
    engine = make_engine()
    engine.models = deepcopy(engine.models)
    engine.models["codex_gpt6_sol"]["reasoning_efforts"] = ["medium", "high"]
    request = StaffingRequest(
        request_id="pm-capability-mismatch",
        project_id="default",
        role="product_manager",
        profile="standard",
        provider_state={
            "provider:google_antigravity": {"available": False},
            "codex_sol": {"available": False},
        },
    )

    with pytest.raises(RuntimeError, match="unsupported"):
        engine.staff(request)


@pytest.mark.parametrize(
    ("model_id", "metadata", "message"),
    [
        ("bad", {"reasoning_efforts": "high"}, "must be a list"),
        ("bad", {"reasoning_efforts": ["high", "unknown"]}, "unknown value"),
        ("bad", {"reasoning_efforts": ["high", "high"]}, "duplicates"),
        (
            "bad",
            {"supports_reasoning_effort": False, "reasoning_efforts": ["low"]},
            "also declares",
        ),
    ],
)
def test_malformed_reasoning_metadata_fails_closed(
    model_id: str,
    metadata: dict,
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        reasoning_capability(model_id, metadata)


def test_frontier_codex_stays_manual_only() -> None:
    engine = make_engine()
    assert engine.models["frontier_codex"]["roles"] == ["frontier_escalation"]
    result = engine.staff(
        StaffingRequest(
            request_id="ordinary-pm",
            project_id="default",
            role="product_manager",
            profile="critical",
        )
    )
    assert result.choice.id != "frontier_codex"
    assert any(
        "missing required role" in reason
        for reason in result.rejected_candidates["frontier_codex"]
    )


def test_automatic_policy_ceilings_remain_low_medium_high_only() -> None:
    policy = get_config()["policy"]
    assert policy["version"] == 20
    assert {
        profile: config.get("reasoning_ceiling", {}).get("executor")
        for profile, config in policy["profiles"].items()
    } == {
        "fast": "low",
        "standard": "medium",
        "complex": "high",
        "critical": "high",
    }
    configured = {
        effort
        for config in policy["profiles"].values()
        for effort in (config.get("reasoning_effort") or {}).values()
    }
    assert configured == {"low", "medium", "high"}


def test_persisted_flash_high_effort_is_normalized_for_reassessment() -> None:
    engine = make_engine()
    stale = choice("antigravity_flash_high", effort="medium")

    capability = engine._validate_reasoning_choice(stale)

    assert capability.supports_explicit_effort is False
    assert stale.reasoning_effort is None
    assert "ignored_legacy_reasoning_effort=medium" in stale.reasons


def test_staffing_flash_medium_omits_effort() -> None:
    engine = make_engine()
    request = StaffingRequest(
        request_id="pm-flash-medium-no-effort",
        project_id="default",
        role="product_manager",
        profile="standard",
        provider_state={
            "antigravity_gemini_pro": {"available": False},
            "codex_gpt6_sol": {"available": False},
            "codex_terra": {"available": False},
            "antigravity_claude_sonnet": {"available": False},
            "codex_sol": {"available": False},
        },
    )

    result = engine.staff(request)

    assert result.choice.id == "antigravity_free"
    assert result.choice.model == "gemini-3.8-flash-medium"
    assert result.choice.reasoning_effort is None


def test_persisted_flash_medium_effort_is_normalized_for_reassessment() -> None:
    engine = make_engine()
    stale = choice("antigravity_free", effort="low")

    capability = engine._validate_reasoning_choice(stale)

    assert capability.supports_explicit_effort is False
    assert stale.reasoning_effort is None
    assert "ignored_legacy_reasoning_effort=low" in stale.reasons
