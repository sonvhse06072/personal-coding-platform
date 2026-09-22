from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from app.adapters.opencode import OpenCodeAdapter, opencode_env_for_model
from app.developer_stream import bind_developer_sink
from app.shell import CommandResult, CommandTimeoutError, agent_subprocess_env


MODEL = "openrouter/cohere/north-mini-code:free"
UPSTREAM_MODEL = "cohere/north-mini-code:free"


def test_openrouter_opencode_env_is_explicit_effectiveness_first_and_provider_scoped(monkeypatch) -> None:
    monkeypatch.setenv("OPENROUTER_API_KEY", "openrouter-secret")
    monkeypatch.setenv("OPENAI_API_KEY", "must-not-leak")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "must-not-leak")

    env = opencode_env_for_model(MODEL)

    assert env["OPENROUTER_API_KEY"] == "openrouter-secret"
    assert "OPENAI_API_KEY" not in env
    assert "ANTHROPIC_API_KEY" not in env
    assert env["OPENCODE_AUTO_SHARE"] == "false"

    config = json.loads(env["OPENCODE_CONFIG_CONTENT"])
    assert config["share"] == "disabled"
    assert config["enabled_providers"] == ["openrouter"]
    openrouter = config["provider"]["openrouter"]
    assert set(openrouter) == {"models", "whitelist"}
    models = openrouter["models"]
    assert list(models) == [UPSTREAM_MODEL]
    assert openrouter["whitelist"] == [UPSTREAM_MODEL]
    policy = models[UPSTREAM_MODEL]["options"]["provider"]
    assert policy == {"allow_fallbacks": True, "require_parameters": True}
    assert "zdr" not in policy
    assert "data_collection" not in policy
    serialized = json.dumps(config, sort_keys=True)
    assert '"models":["' not in serialized
    assert "model_fallbacks" not in serialized


def test_openrouter_adapter_forwards_only_its_key_and_required_opencode_policy(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("OPENROUTER_API_KEY", "openrouter-secret")
    monkeypatch.setenv("OPENAI_API_KEY", "must-not-leak")
    monkeypatch.setenv("RUNTIME_API_TOKEN", "must-not-leak")
    monkeypatch.setenv("ROUTER_API_TOKEN", "must-not-leak")
    monkeypatch.setenv("PLATFORM_INTERNAL_TOKEN", "must-not-leak")
    captured: dict[str, object] = {}
    seen: list[dict] = []
    event_line = json.dumps({"type": "step_start", "part": {"type": "step-start"}})

    async def fake_run_command(argv, *, cwd, timeout, env, on_stdout_line=None):
        captured["argv"] = argv
        captured["env"] = env
        assert on_stdout_line is not None
        on_stdout_line(event_line)
        return CommandResult(argv=argv, returncode=0, stdout=event_line, stderr="")

    monkeypatch.setattr("app.adapters.opencode.run_command", fake_run_command)
    bind_developer_sink(seen.append)
    try:
        run = asyncio.run(
            OpenCodeAdapter(MODEL).run(
                workspace=tmp_path,
                prompt="bounded test prompt",
                mode="execute",
                timeout=30,
            )
        )
    finally:
        bind_developer_sink(None)

    assert run.returncode == 0
    child_extra = captured["env"]
    assert isinstance(child_extra, dict)
    assert set(child_extra) == {"OPENROUTER_API_KEY", "OPENCODE_AUTO_SHARE", "OPENCODE_CONFIG_CONTENT"}
    assert child_extra["OPENROUTER_API_KEY"] == "openrouter-secret"
    assert "--model" in captured["argv"]
    assert MODEL in captured["argv"]
    sanitized = agent_subprocess_env(child_extra)
    assert sanitized["OPENROUTER_API_KEY"] == "openrouter-secret"
    for key in {"OPENAI_API_KEY", "RUNTIME_API_TOKEN", "ROUTER_API_TOKEN", "PLATFORM_INTERNAL_TOKEN"}:
        assert key not in sanitized
    streamed = [event for event in seen if event["event_type"] == "developer_step"]
    assert any(event["data"].get("provider") == "openrouter" for event in streamed)
    assert any(event["data"].get("adapter") == "opencode" for event in streamed)


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

def test_opencode_timeout_returns_structured_transient_failure(monkeypatch, tmp_path: Path) -> None:
    seen: list[dict] = []
    event_line = json.dumps({"type": "step_start", "part": {"type": "step-start"}})

    async def fake_run_command(argv, *, cwd, timeout, env, on_stdout_line=None):
        assert on_stdout_line is not None
        on_stdout_line(event_line)
        raise CommandTimeoutError(
            timeout=timeout,
            argv=argv,
            stdout=event_line + "\n",
        )

    monkeypatch.setattr("app.adapters.opencode.run_command", fake_run_command)
    bind_developer_sink(seen.append)
    try:
        run = asyncio.run(
            OpenCodeAdapter(MODEL).run(
                workspace=tmp_path,
                prompt="bounded test prompt",
                mode="execute",
                timeout=30,
            )
        )
    finally:
        bind_developer_sink(None)

    assert run.returncode == 124
    assert run.failure_kind == "timeout"
    assert run.failure_message == "Command timed out after 30s"
    assert run.provider_failed is True
    assert event_line in run.raw
    lifecycle = [
        event["data"].get("status")
        for event in seen
        if event["event_type"] == "developer_step"
    ]
    assert lifecycle == ["started", "failed"]

