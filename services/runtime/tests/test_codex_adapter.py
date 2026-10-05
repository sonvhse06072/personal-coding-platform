import asyncio
import json
from pathlib import Path

import pytest

from app.adapters.base import AgentAdapter
from app.adapters.codex import CodexAdapter
from app.developer_stream import bind_developer_sink
from app.shell import CommandResult, CommandTimeoutError


def _event(payload: dict) -> str:
    return json.dumps(payload)


def _assert_bounded_unattended_policy(argv: list[str], *, sandbox: str) -> None:
    assert argv[argv.index("--sandbox") + 1] == sandbox
    assert 'approval_policy="never"' in argv
    assert "features.memories=false" in argv
    assert "memories.use_memories=false" in argv
    assert "memories.generate_memories=false" in argv
    assert "danger-full-access" not in argv
    assert "--dangerously-bypass-approvals-and-sandbox" not in argv


def test_invocation_capabilities_default_to_local_listener_available():
    assert AgentAdapter("test-model").invocation_capabilities("execute").local_listener is True


def test_codex_invocation_capabilities_are_explicit_by_mode():
    adapter = CodexAdapter("gpt-5.6-sol")

    for mode in ("execute", "repair"):
        capabilities = adapter.invocation_capabilities(mode)
        assert capabilities.local_listener is False
        assert capabilities.reason == "codex_workspace_network_disabled"

    evaluation = adapter.invocation_capabilities("evaluate")
    assert evaluation.local_listener is False
    assert evaluation.reason == "codex_read_only_evaluation"

    assert adapter.invocation_capabilities("plan").local_listener is True


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

    async def fake_run_command(argv, *, cwd, timeout, on_stdout_line=None):
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
    _assert_bounded_unattended_policy(captured["argv"], sandbox="workspace-write")
    assert "sandbox_workspace_write.network_access=false" in captured["argv"]


def test_codex_output_uses_only_last_agent_message(monkeypatch, tmp_path: Path):
    progress = "Inspecting the approved baseline before planning."
    final_json = json.dumps({
        "scope_assessment": "in_scope",
        "summary": "The ticket is routine and bounded.",
        "work_orders": [],
        "decision_boundaries": [],
    })
    stdout = "\n".join([
        _event({"type": "turn.started"}),
        _event({
            "type": "item.completed",
            "item": {"type": "agent_message", "text": progress},
        }),
        _event({
            "type": "item.completed",
            "item": {"type": "agent_message", "text": final_json},
        }),
        _event({"type": "turn.completed", "usage": {"input_tokens": 100, "output_tokens": 50}}),
    ])
    captured: dict[str, object] = {}

    async def fake_run_command(argv, *, cwd, timeout, on_stdout_line=None):
        output_index = argv.index("--output-last-message")
        output_path = Path(argv[output_index + 1])
        captured["path"] = output_path
        captured["argv"] = argv
        assert output_path.exists()
        output_path.write_text(final_json, encoding="utf-8")
        return CommandResult(argv=argv, returncode=0, stdout=stdout, stderr="")

    monkeypatch.setattr("app.adapters.codex.run_command", fake_run_command)
    run = asyncio.run(
        CodexAdapter("gpt-5.6-terra", "low").run(
            workspace=tmp_path,
            prompt="return one JSON object",
            mode="plan",
            timeout=30,
        )
    )

    assert run.returncode == 0
    assert run.output == final_json
    assert progress not in run.output
    raw_events = [json.loads(line) for line in run.raw.splitlines()]
    raw_messages = [
        event["item"]["text"]
        for event in raw_events
        if event.get("type") == "item.completed"
        and event.get("item", {}).get("type") == "agent_message"
    ]
    assert raw_messages == [progress, final_json]
    assert "--output-last-message" in captured["argv"]
    _assert_bounded_unattended_policy(captured["argv"], sandbox="read-only")
    assert not captured["path"].exists()


def test_codex_last_message_tempfile_is_removed_on_cancellation(monkeypatch, tmp_path: Path):
    captured: dict[str, Path] = {}

    async def fake_run_command(argv, *, cwd, timeout, on_stdout_line=None):
        output_index = argv.index("--output-last-message")
        output_path = Path(argv[output_index + 1])
        captured["path"] = output_path
        output_path.write_text("partial", encoding="utf-8")
        raise asyncio.CancelledError()

    monkeypatch.setattr("app.adapters.codex.run_command", fake_run_command)

    with pytest.raises(asyncio.CancelledError):
        asyncio.run(
            CodexAdapter("gpt-5.6-terra").run(
                workspace=tmp_path,
                prompt="plan",
                mode="plan",
                timeout=30,
            )
        )

    assert not captured["path"].exists()


def test_codex_read_only_modes_are_noninteractive_without_write_network_override(monkeypatch, tmp_path: Path):
    captured: list[list[str]] = []

    async def fake_run_command(argv, *, cwd, timeout, on_stdout_line=None):
        captured.append(argv)
        return CommandResult(
            argv=argv,
            returncode=0,
            stdout=_event({"type": "turn.completed", "usage": {}}),
            stderr="",
        )

    monkeypatch.setattr("app.adapters.codex.run_command", fake_run_command)
    for mode in ("plan", "evaluate"):
        asyncio.run(
            CodexAdapter("gpt-5.6-luna").run(
                workspace=tmp_path,
                prompt="inspect",
                mode=mode,
                timeout=30,
            )
        )

    assert len(captured) == 2
    for argv in captured:
        _assert_bounded_unattended_policy(argv, sandbox="read-only")
        assert "sandbox_workspace_write.network_access=false" not in argv
        assert not any(str(arg).startswith("model_reasoning_effort=") for arg in argv)


def test_codex_turn_failed_still_classifies_provider_failure(monkeypatch, tmp_path: Path):
    stdout = "\n".join([
        _event({"type": "turn.started"}),
        _event({
            "type": "turn.failed",
            "error": {"message": "Too many requests: rate limit exceeded"},
        }),
    ])

    async def fake_run_command(argv, *, cwd, timeout, on_stdout_line=None):
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
    async def fake_run_command(argv, *, cwd, timeout, on_stdout_line=None):
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


def test_codex_emits_provider_neutral_activity_during_stdout_stream(monkeypatch, tmp_path: Path):
    line = _event({
        "type": "item.completed",
        "item": {"type": "agent_message", "text": "Editing the recovery runner."},
    })
    terminal = _event({"type": "turn.completed", "usage": {}})
    seen: list[dict] = []

    async def fake_run_command(argv, *, cwd, timeout, on_stdout_line=None):
        assert on_stdout_line is not None
        on_stdout_line(line)
        return CommandResult(argv=argv, returncode=0, stdout=f"{line}\n{terminal}", stderr="")

    monkeypatch.setattr("app.adapters.codex.run_command", fake_run_command)
    bind_developer_sink(seen.append)
    try:
        asyncio.run(
            CodexAdapter("gpt-5.6-terra").run(
                workspace=tmp_path,
                prompt="implement",
                mode="execute",
                timeout=30,
            )
        )
    finally:
        bind_developer_sink(None)

    messages = [event for event in seen if event["event_type"] == "developer_message"]
    assert len(messages) == 1
    assert messages[0]["data"]["text"] == "Editing the recovery runner."
    assert messages[0]["data"]["provider"] == "openai"
    assert messages[0]["data"]["adapter"] == "codex_cli"
    assert messages[0]["data"]["model"] == "gpt-5.6-terra"
    lifecycle = [event["data"].get("status") for event in seen if event["event_type"] == "developer_step"]
    assert lifecycle == ["started", "completed"]

def test_codex_timeout_returns_structured_failure_and_removes_last_message_file(monkeypatch, tmp_path: Path):
    captured: dict[str, Path] = {}
    seen: list[dict] = []
    partial = _event({
        "type": "item.completed",
        "item": {"type": "agent_message", "text": "Partial progress before timeout."},
    })

    async def fake_run_command(argv, *, cwd, timeout, on_stdout_line=None):
        output_index = argv.index("--output-last-message")
        output_path = Path(argv[output_index + 1])
        captured["path"] = output_path
        assert output_path.exists()
        assert on_stdout_line is not None
        on_stdout_line(partial)
        raise CommandTimeoutError(
            timeout=timeout,
            argv=argv,
            stdout=partial + "\n",
        )

    monkeypatch.setattr("app.adapters.codex.run_command", fake_run_command)
    bind_developer_sink(seen.append)
    try:
        run = asyncio.run(
            CodexAdapter("gpt-5.6-terra").run(
                workspace=tmp_path,
                prompt="implement",
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
    assert run.output == "Partial progress before timeout."
    assert not captured["path"].exists()
    lifecycle = [
        event["data"].get("status")
        for event in seen
        if event["event_type"] == "developer_step"
    ]
    assert lifecycle == ["started", "failed"]
