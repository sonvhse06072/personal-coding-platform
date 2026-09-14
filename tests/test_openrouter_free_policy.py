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


def test_openrouter_free_uses_one_explicit_private_code_model() -> None:
    models_doc, _ = documents()
    models = models_doc["models"]
    model = models[MODEL_ID]

    assert all(item.get("model") != "openrouter/free" for item in models.values())
    assert model["kind"] == "agent"
    assert model["provider"] == "openrouter"
    assert model["adapter"] == "opencode"
    assert model["model"] == "openrouter/qwen/qwen3-coder:free"
    assert model["cost_class"] == "free"
    assert model["quota_group"] == "openrouter_free"
    assert model["allowed_profiles"] == ["fast", "standard", "complex"]

    assert set(model["roles"]) == {"fast_executor", "standard_executor", "reviewer"}
    assert not ({"executor", "debugger", "critical_executor", "product_manager", "planner"} & set(model["roles"]))

    assert model["privacy"] == {
        "private_code_allowed": True,
        "training_allowed": False,
        "zero_retention_supported": True,
        "enforcement_basis": "openrouter_request_policy",
    }
    assert model["provider_policy"] == {
        "data_collection": "deny",
        "zdr": True,
        "require_parameters": True,
        "allow_fallbacks": True,
        "model_fallbacks": False,
    }
    assert model["free_tier"]["authoritative_remaining_available"] is False


def test_openrouter_free_is_opportunistic_and_excluded_from_critical_and_pm() -> None:
    _, policy = documents()
    profiles = policy["profiles"]

    assert "fast_executor" in profiles["fast"]["executor_roles"]
    assert profiles["fast"]["preferred_executor_ids"][0] == MODEL_ID

    assert "standard_executor" in profiles["standard"]["executor_roles"]
    standard = profiles["standard"]["preferred_executor_ids"]
    assert standard[:2] == ["antigravity_free", MODEL_ID]

    assert MODEL_ID not in profiles["complex"]["preferred_executor_ids"]
    assert MODEL_ID not in profiles["complex"]["preferred_planner_ids"]
    complex_evaluators = profiles["complex"]["preferred_evaluator_ids"]
    assert complex_evaluators.index("antigravity_free") < complex_evaluators.index(MODEL_ID)
    assert complex_evaluators.index(MODEL_ID) < complex_evaluators.index("codex_terra")

    critical = profiles["critical"]
    assert MODEL_ID not in critical["preferred_executor_ids"]
    assert MODEL_ID not in critical["preferred_planner_ids"]
    assert MODEL_ID not in critical["preferred_evaluator_ids"]

    product_manager = policy["staffing_roles"]["product_manager"]
    assert MODEL_ID not in product_manager["preferred_ids"]
