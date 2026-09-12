from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from app.adapters.opencode import provider_env_for_model
from app.shell import agent_subprocess_env, run_command


INTERNAL_SECRETS = {
    "RUNTIME_API_TOKEN": "runtime-secret",
    "ROUTER_API_TOKEN": "router-secret",
    "PLATFORM_INTERNAL_TOKEN": "executor-secret",
    "ANTIGRAVITY_BRIDGE_TOKEN": "bridge-secret",
    "GITHUB_DELIVERY_TOKEN": "github-secret",
}

PROVIDER_SECRETS = {
    "DEEPSEEK_API_KEY": "deepseek-secret",
    "ANTHROPIC_API_KEY": "anthropic-secret",
    "OPENAI_API_KEY": "openai-secret",
    "GROQ_API_KEY": "groq-secret",
    "OPENROUTER_API_KEY": "openrouter-secret",
}


def seed_secrets(monkeypatch) -> None:
    for key, value in {**INTERNAL_SECRETS, **PROVIDER_SECRETS}.items():
        monkeypatch.setenv(key, value)


def test_agent_subprocess_env_does_not_inherit_runtime_or_provider_secrets(monkeypatch) -> None:
    seed_secrets(monkeypatch)
    monkeypatch.setenv("PATH", "/safe/bin")
    monkeypatch.setenv("HOME", "/home/coder")

    env = agent_subprocess_env()

    assert env["PATH"] == "/safe/bin"
    assert env["HOME"] == "/home/coder"
    for key in {*INTERNAL_SECRETS, *PROVIDER_SECRETS}:
        assert key not in env


def test_agent_subprocess_env_allows_explicit_selected_provider_key(monkeypatch) -> None:
    seed_secrets(monkeypatch)

    env = agent_subprocess_env({"DEEPSEEK_API_KEY": "selected-secret"})

    assert env["DEEPSEEK_API_KEY"] == "selected-secret"
    assert "ANTHROPIC_API_KEY" not in env
    assert "OPENAI_API_KEY" not in env


@pytest.mark.parametrize("key", sorted(INTERNAL_SECRETS))
def test_agent_subprocess_env_rejects_explicit_internal_credentials(monkeypatch, key: str) -> None:
    seed_secrets(monkeypatch)

    with pytest.raises(ValueError, match="Refusing to expose Runtime credential"):
        agent_subprocess_env({key: "should-never-be-forwarded"})


def test_opencode_provider_env_forwards_only_selected_provider(monkeypatch) -> None:
    seed_secrets(monkeypatch)

    assert provider_env_for_model("deepseek/deepseek-v4-flash") == {
        "DEEPSEEK_API_KEY": "deepseek-secret"
    }
    assert provider_env_for_model("anthropic/claude-sonnet-5") == {
        "ANTHROPIC_API_KEY": "anthropic-secret"
    }
    assert provider_env_for_model("auto") == {}
    assert provider_env_for_model("unknown/model") == {}


def test_run_command_uses_sanitized_agent_environment(monkeypatch, tmp_path: Path) -> None:
    seed_secrets(monkeypatch)
    monkeypatch.setenv("PATH", "/safe/bin")
    captured: dict[str, object] = {}

    class FakeProcess:
        pid = 12345
        returncode = 0

        async def communicate(self):
            return b"ok", b""

    async def fake_create_subprocess_exec(*argv, **kwargs):
        captured["argv"] = argv
        captured["env"] = dict(kwargs["env"])
        return FakeProcess()

    monkeypatch.setattr("app.shell.asyncio.create_subprocess_exec", fake_create_subprocess_exec)

    result = asyncio.run(
        run_command(
            ["fake-agent", "run"],
            cwd=tmp_path,
            timeout=30,
            env={"DEEPSEEK_API_KEY": "selected-secret"},
        )
    )

    assert result.returncode == 0
    child_env = captured["env"]
    assert isinstance(child_env, dict)
    assert child_env["PATH"] == "/safe/bin"
    assert child_env["DEEPSEEK_API_KEY"] == "selected-secret"
    for key in INTERNAL_SECRETS:
        assert key not in child_env
    for key in PROVIDER_SECRETS:
        if key != "DEEPSEEK_API_KEY":
            assert key not in child_env
