import asyncio
import json
from pathlib import Path

from app.adapters.codex import CodexAdapter
from app.shell import CommandResult


def _event(payload: dict) -> str:
    return json.dumps(payload)


def test_codex_turn_completed_is_authoritative_over_transient_rate_limit_text(monkeypatch, tmp_path: Path):
    stdout = "\n".join([
        _event({"type": "turn.started"}),
        _event({"type": "rate_limits.updated", "message": "rate limit telemetry refreshed"}),
        _event({
            "type": "item.completed",
            "item": {"type": "agent_message", "text": "Implemented the requested test."},
        }),
        _event({
            "type": "turn.completed",
            "usage": {"input_tokens": 513294, "output_tokens": 6475},
        }),
    ])
    captured = {}

    async def fake_run_command(argv, *, cwd, timeout):
        captured["argv"] = argv
        return CommandResult(argv=argv, returncode=0, stdout=stdout, stderr="")

    monkeypatch.setattr("app.adapters.codex.run_command", fake_run_command)
    run = asyncio.run(
        CodexAdapter("gpt-5.6-sol", "medium").run(
            workspace=tmp_path,
            prompt="add a test",
            mode="execute",
            timeout=30,
        )
    )

    assert run.returncode == 0
    assert run.failure_kind is None
    assert not run.provider_failed
    assert run.output == "Implemented the requested test."
    assert run.usage["input_tokens"] == 513294
    assert run.usage["output_tokens"] == 6475
    assert "--model" in captured["argv"]
    assert "gpt-5.6-sol" in captured["argv"]
    assert "--config" in captured["argv"]
    assert 'model_reasoning_effort="medium"' in captured["argv"]


def test_codex_without_routed_effort_does_not_invent_override(monkeypatch, tmp_path: Path):
    captured = {}

    async def fake_run_command(argv, *, cwd, timeout):
        captured["argv"] = argv
        return CommandResult(
            argv=argv,
            returncode=0,
            stdout=_event({"type": "turn.completed", "usage": {}}),
            stderr="",
        )

    monkeypatch.setattr("app.adapters.codex.run_command", fake_run_command)
    asyncio.run(
        CodexAdapter("gpt-5.6-luna").run(
            workspace=tmp_path,
            prompt="inspect",
            mode="plan",
            timeout=30,
        )
    )

    assert not any(str(arg).startswith("model_reasoning_effort=") for arg in captured["argv"])


def test_codex_turn_failed_still_classifies_provider_failure(monkeypatch, tmp_path: Path):
    stdout = "\n".join([
        _event({"type": "turn.started"}),
        _event({
            "type": "turn.failed",
            "error": {"message": "Too many requests: rate limit exceeded"},
        }),
    ])

    async def fake_run_command(argv, *, cwd, timeout):
        return CommandResult(argv=argv, returncode=0, stdout=stdout, stderr="")

    monkeypatch.setattr("app.adapters.codex.run_command", fake_run_command)
    run = asyncio.run(
        CodexAdapter("gpt-5.6-sol").run(
            workspace=tmp_path,
            prompt="add a test",
            mode="execute",
            timeout=30,
        )
    )

    assert run.returncode != 0
    assert run.failure_kind == "rate_limited"
    assert run.provider_failed


def test_codex_plain_cli_failure_without_terminal_json_is_still_classified(monkeypatch, tmp_path: Path):
    async def fake_run_command(argv, *, cwd, timeout):
        return CommandResult(
            argv=argv,
            returncode=1,
            stdout="",
            stderr="You have reached your usage limit. Try again later.",
        )

    monkeypatch.setattr("app.adapters.codex.run_command", fake_run_command)
    run = asyncio.run(
        CodexAdapter("gpt-5.6-sol").run(
            workspace=tmp_path,
            prompt="add a test",
            mode="execute",
            timeout=30,
        )
    )

    assert run.returncode == 1
    assert run.failure_kind == "quota_exhausted"
    assert run.provider_failed
