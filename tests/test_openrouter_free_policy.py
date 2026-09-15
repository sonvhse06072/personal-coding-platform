from __future__ import annotations

from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
MODELS = ROOT / "config" / "models.yml"
POLICY = ROOT / "config" / "routing-policy.yml"
MODEL_ID = "openrouter_qwen3_coder_free"


def documents() -> tuple[dict, dict]:
    return (
        yaml.safe_load(MODELS.read_text(encoding="utf-8")),
        yaml.safe_load(POLICY.read_text(encoding="utf-8")),
    )


def test_openrouter_free_uses_one_explicit_effectiveness_first_model() -> None:
    models_doc, _ = documents()
    models = models_doc["models"]
    model = models[MODEL_ID]

    assert models_doc["version"] == 8
    assert all(item.get("model") != "openrouter/free" for item in models.values())
    assert model["kind"] == "agent"
    assert model["provider"] == "openrouter"
    assert model["adapter"] == "opencode"
    assert model["model"] == "openrouter/cohere/north-mini-code:free"
    assert model["cost_class"] == "free"
    assert model["quota_group"] == "openrouter_free"
    assert model["allowed_profiles"] == ["fast", "standard", "complex"]

    assert set(model["roles"]) == {"fast_executor", "standard_executor", "reviewer"}
    assert not ({"executor", "debugger", "critical_executor", "product_manager", "planner"} & set(model["roles"]))

    assert model["privacy"] == {
        "private_code_allowed": True,
        "training_allowed": True,
        "zero_retention_supported": False,
        "enforcement_basis": "human_owner_effectiveness_first_2026_09_14",
    }
    assert model["provider_policy"] == {
        "require_parameters": True,
        "allow_fallbacks": True,
        "model_fallbacks": False,
        "zdr_required": False,
        "data_collection_deny_required": False,
    }
    assert model["free_tier"]["authoritative_remaining_available"] is False


def test_openrouter_free_is_preferred_for_routine_work_and_excluded_from_critical_and_pm() -> None:
    _, policy = documents()
    profiles = policy["profiles"]

    assert policy["version"] == 12
    assert policy["telemetry_calibration"]["minimum_sample_size"] == 5
    assert "fast_executor" in profiles["fast"]["executor_roles"]
    assert profiles["fast"]["preferred_executor_ids"][0] == MODEL_ID

    assert "standard_executor" in profiles["standard"]["executor_roles"]
    assert profiles["standard"]["preferred_order_bonus"] == 0.14
    standard = profiles["standard"]["preferred_executor_ids"]
    assert standard[:2] == [MODEL_ID, "antigravity_free"]

    assert MODEL_ID not in profiles["complex"]["preferred_executor_ids"]
    assert MODEL_ID not in profiles["complex"]["preferred_planner_ids"]
    complex_evaluators = profiles["complex"]["preferred_evaluator_ids"]
    assert complex_evaluators.index("antigravity_claude_sonnet") < complex_evaluators.index(MODEL_ID)
    assert complex_evaluators.index(MODEL_ID) < complex_evaluators.index("codex_terra")

    critical = profiles["critical"]
    assert MODEL_ID not in critical["preferred_executor_ids"]
    assert MODEL_ID not in critical["preferred_planner_ids"]
    assert MODEL_ID not in critical["preferred_evaluator_ids"]

    product_manager = policy["staffing_roles"]["product_manager"]
    assert MODEL_ID not in product_manager["preferred_ids"]
