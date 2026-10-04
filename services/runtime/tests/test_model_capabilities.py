from __future__ import annotations

from copy import deepcopy

import pytest

from app.config import models_doc
from app.model_capabilities import (
    ModelCapabilityError,
    REASONING_EFFORT_ORDER,
    reasoning_capability,
    validate_model_choice,
    validate_model_registry,
)


def choice(model_id: str, effort: str | None) -> dict:
    model = models_doc()["models"][model_id]
    return {
        "id": model_id,
        "provider": model["provider"],
        "adapter": model["adapter"],
        "model": model["model"],
        "reasoning_effort": effort,
    }


def test_valid_codex_and_new_frontier_effort_are_accepted() -> None:
    assert validate_model_choice(choice("codex_terra", "medium")).supports_explicit_effort
    capability = validate_model_choice(choice("frontier_codex", "max"))
    assert capability.allowed_efforts == REASONING_EFFORT_ORDER


@pytest.mark.parametrize(
    ("model_id", "effort"),
    [
        ("codex_luna", "low"),
        ("codex_terra", "medium"),
        ("codex_sol", "high"),
        ("antigravity_flash_high", "medium"),
        ("antigravity_gemini_pro", "high"),
    ],
)
def test_historical_low_medium_high_choices_remain_valid(
    model_id: str,
    effort: str,
) -> None:
    validate_model_choice(choice(model_id, effort))




@pytest.mark.parametrize(
    ("model_id", "upstream", "effort"),
    [
        ("codex_gpt6_luna", "gpt-6-luna", "low"),
        ("codex_gpt6_sol", "gpt-6-sol", "medium"),
        ("codex_gpt61_sol", "gpt-6.1-sol", "high"),
    ],
)
def test_current_codex_generation_choices_are_registry_valid(
    model_id: str,
    upstream: str,
    effort: str,
) -> None:
    selected = choice(model_id, effort)
    assert selected["model"] == upstream
    capability = validate_model_choice(selected)
    assert capability.supports_explicit_effort is True
    assert capability.allowed_efforts[-1] == "max"


def test_flash_medium_accepts_only_legacy_ignored_efforts_and_claude_stays_strict() -> None:
    assert not validate_model_choice(
        choice("antigravity_free", "low")
    ).supports_explicit_effort
    with pytest.raises(ModelCapabilityError, match="unsupported"):
        validate_model_choice(choice("antigravity_free", "xhigh"))

    with pytest.raises(ModelCapabilityError, match="unsupported"):
        validate_model_choice(choice("antigravity_claude_sonnet", "low"))
    assert not validate_model_choice(
        choice("antigravity_claude_sonnet", None)
    ).supports_explicit_effort


def test_unknown_model_adapter_and_upstream_mismatches_fail_closed() -> None:
    unknown = choice("codex_terra", "medium")
    unknown["id"] = "unknown-model"
    with pytest.raises(ModelCapabilityError, match="Unknown PCP model id"):
        validate_model_choice(unknown)

    adapter_mismatch = choice("codex_terra", "medium")
    adapter_mismatch["adapter"] = "antigravity_host"
    with pytest.raises(ModelCapabilityError, match="Adapter mismatch"):
        validate_model_choice(adapter_mismatch)

    upstream_mismatch = choice("codex_terra", "medium")
    upstream_mismatch["model"] = "gpt-6-astra"
    with pytest.raises(ModelCapabilityError, match="Upstream model mismatch"):
        validate_model_choice(upstream_mismatch)




def test_legacy_codex_logical_ids_keep_historical_upstreams() -> None:
    models = models_doc()["models"]

    assert models["codex_luna"]["model"] == "gpt-5.6-luna"
    assert models["codex_terra"]["model"] == "gpt-5.6-terra"
    assert models["codex_sol"]["model"] == "gpt-5.6-sol"
    assert models["frontier_codex"]["model"] == "gpt-6-astra"
    assert models["frontier_codex"]["roles"] == ["frontier_escalation"]
    assert {
        models[model_id]["quota_group"]
        for model_id in (
            "codex_gpt6_luna",
            "codex_gpt6_sol",
            "codex_gpt61_sol",
            "codex_luna",
            "codex_terra",
            "codex_sol",
            "frontier_codex",
        )
    } == {"codex_chatgpt_plus"}


def test_non_reasoning_adapter_rejects_an_explicit_effort() -> None:
    validate_model_choice(choice("openrouter_qwen3_coder_free", None))
    with pytest.raises(ModelCapabilityError, match="unsupported"):
        validate_model_choice(choice("openrouter_qwen3_coder_free", "low"))


@pytest.mark.parametrize(
    ("metadata", "message"),
    [
        ({"reasoning_efforts": "high"}, "must be a list"),
        ({"reasoning_efforts": ["low", "unknown"]}, "unknown value"),
        ({"reasoning_efforts": ["low", "low"]}, "duplicates"),
        ({"reasoning_efforts": ["high", "low"]}, "canonical order"),
        (
            {"supports_reasoning_effort": False, "reasoning_efforts": ["low"]},
            "also declares",
        ),
    ],
)
def test_malformed_registry_reasoning_metadata_is_rejected(
    metadata: dict,
    message: str,
) -> None:
    document = deepcopy(models_doc())
    document["models"]["codex_terra"].update(metadata)
    with pytest.raises(ValueError, match=message):
        validate_model_registry(document)


def test_registry_declares_bounded_antigravity_and_full_codex_capabilities() -> None:
    models = models_doc()["models"]
    for model_id in (
        "codex_gpt6_luna",
        "codex_gpt6_sol",
        "codex_gpt61_sol",
        "codex_luna",
        "codex_terra",
        "codex_sol",
        "frontier_codex",
    ):
        assert reasoning_capability(model_id, models[model_id]).allowed_efforts[-1] == "max"
    for model_id in ("antigravity_flash_high", "antigravity_gemini_pro"):
        assert reasoning_capability(model_id, models[model_id]).allowed_efforts == (
            "low",
            "medium",
            "high",
        )
    assert reasoning_capability(
        "antigravity_free", models["antigravity_free"]
    ).allowed_efforts == ()


def test_legacy_ignored_reasoning_metadata_is_validated() -> None:
    document = deepcopy(models_doc())
    document["models"]["antigravity_free"]["legacy_ignored_reasoning_efforts"] = [
        "low",
        "unknown",
    ]
    with pytest.raises(ValueError, match="unknown value"):
        validate_model_registry(document)
