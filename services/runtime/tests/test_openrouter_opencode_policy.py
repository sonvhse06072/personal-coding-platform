from __future__ import annotations

import json

import pytest

from app.adapters.opencode import opencode_env_for_model


def test_openrouter_opencode_env_is_explicit_private_and_provider_scoped(monkeypatch) -> None:
    monkeypatch.setenv("OPENROUTER_API_KEY", "openrouter-secret")
    monkeypatch.setenv("OPENAI_API_KEY", "must-not-leak")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "must-not-leak")

    env = opencode_env_for_model("openrouter/qwen/qwen3-coder:free")

    assert env["OPENROUTER_API_KEY"] == "openrouter-secret"
    assert "OPENAI_API_KEY" not in env
    assert "ANTHROPIC_API_KEY" not in env
    assert env["OPENCODE_AUTO_SHARE"] == "false"

    config = json.loads(env["OPENCODE_CONFIG_CONTENT"])
    models = config["provider"]["openrouter"]["models"]
    assert list(models) == ["qwen/qwen3-coder:free"]
    policy = models["qwen/qwen3-coder:free"]["options"]["provider"]
    assert policy == {
        "allow_fallbacks": True,
        "data_collection": "deny",
        "require_parameters": True,
        "zdr": True,
    }
    # OpenRouter receives one explicit model. There is no request-level model
    # fallback list for OpenRouter to select another model behind PCP Router.
    serialized = json.dumps(config, sort_keys=True)
    assert '"models":["' not in serialized


def test_openrouter_free_router_is_rejected_for_durable_coding_runs(monkeypatch) -> None:
    monkeypatch.setenv("OPENROUTER_API_KEY", "openrouter-secret")

    with pytest.raises(RuntimeError, match="explicit model"):
        opencode_env_for_model("openrouter/free")


def test_non_openrouter_model_keeps_existing_provider_env_contract(monkeypatch) -> None:
    monkeypatch.setenv("DEEPSEEK_API_KEY", "deepseek-secret")
    monkeypatch.setenv("OPENROUTER_API_KEY", "must-not-leak")

    env = opencode_env_for_model("deepseek/deepseek-v4-flash")

    assert env == {"DEEPSEEK_API_KEY": "deepseek-secret"}
    assert "OPENCODE_CONFIG_CONTENT" not in env
    assert "OPENCODE_AUTO_SHARE" not in env
