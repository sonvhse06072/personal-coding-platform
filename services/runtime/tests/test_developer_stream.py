import json
from pathlib import Path

from app.developer_stream import (
    agent_public_event,
    agent_response_event,
    codex_public_event,
    provider_for_adapter,
    runtime_activity_event,
)


def test_agent_message_is_bounded_redacted_and_hides_workspace(tmp_path: Path):
    secret = "sk-abcdefghijklmnopqrstuvwxyz123456"
    event = codex_public_event(
        {
            "type": "item.completed",
            "item": {
                "type": "agent_message",
                "text": f"Inspecting {tmp_path}/runner.py with API_KEY={secret}",
            },
        },
        workspace=tmp_path,
        mode="execute",
        model="gpt-5.6-terra",
    )
    assert event is not None
    encoded = json.dumps(event)
    assert str(tmp_path) not in encoded
    assert secret not in encoded
    assert "API_KEY=<redacted>" in encoded
    assert event["data"]["role"] == "executor"
    assert event["data"]["provider"] == "openai"
    assert event["data"]["adapter"] == "codex_cli"


def test_reasoning_events_are_never_exposed(tmp_path: Path):
    event = codex_public_event(
        {
            "type": "item.completed",
            "item": {"type": "reasoning", "text": "private chain of thought"},
        },
        workspace=tmp_path,
        mode="execute",
        model="gpt-5.6-terra",
    )
    assert event is None


def test_command_output_is_bounded_and_redacted(tmp_path: Path):
    event = codex_public_event(
        {
            "type": "item.completed",
            "item": {
                "type": "command_execution",
                "command": f"cd {tmp_path} && curl -H 'Authorization: Bearer abcdefghijklmnop' example.invalid",
                "aggregated_output": "PASSWORD=hunter2\n" + ("x" * 5000),
                "exit_code": 1,
                "status": "failed",
            },
        },
        workspace=tmp_path,
        mode="execute",
        model="gpt-5.6-terra",
    )
    assert event is not None
    assert event["event_type"] == "developer_command_completed"
    assert event["level"] == "error"
    assert str(tmp_path) not in json.dumps(event)
    assert "hunter2" not in json.dumps(event)
    assert "Bearer abcdefghijklmnop" not in json.dumps(event)
    assert len(event["data"]["output"]) <= 3000


def test_file_activity_keeps_only_bounded_paths(tmp_path: Path):
    changes = [{"path": f"{tmp_path}/file-{index}.php"} for index in range(20)]
    event = codex_public_event(
        {"type": "item.completed", "item": {"type": "file_change", "changes": changes}},
        workspace=tmp_path,
        mode="execute",
        model="gpt-5.6-terra",
    )
    assert event is not None
    assert len(event["data"]["paths"]) == 12
    assert all(str(tmp_path) not in path for path in event["data"]["paths"])


def test_openrouter_identity_is_distinct_from_opencode_adapter(tmp_path: Path):
    model = "openrouter/cohere/north-mini-code:free"
    assert provider_for_adapter("opencode", model) == "openrouter"
    event = agent_public_event(
        {"type": "step_start", "part": {"type": "step-start"}},
        workspace=tmp_path,
        mode="execute",
        adapter="opencode",
        provider="openrouter",
        model=model,
    )
    assert event is not None
    assert event["event_type"] == "developer_step"
    assert event["data"]["adapter"] == "opencode"
    assert event["data"]["provider"] == "openrouter"
    assert event["data"]["model"] == model


def test_opencode_text_and_reasoning_never_expose_raw_content(tmp_path: Path):
    for raw in (
        {"type": "reasoning", "part": {"type": "reasoning", "text": "private chain"}},
        {"type": "text", "part": {"type": "text", "text": "possibly compaction internals"}},
    ):
        event = agent_public_event(
            raw,
            workspace=tmp_path,
            mode="execute",
            adapter="opencode",
            provider="openrouter",
            model="openrouter/cohere/north-mini-code:free",
        )
        encoded = json.dumps(event) if event is not None else ""
        assert "private chain" not in encoded
        assert "compaction internals" not in encoded


def test_opencode_tool_activity_is_bounded_and_redacted(tmp_path: Path):
    event = agent_public_event(
        {
            "type": "tool_use",
            "part": {
                "type": "tool",
                "tool": "bash",
                "state": {
                    "status": "completed",
                    "input": {"command": f"cd {tmp_path} && echo TOKEN=abcdefghijklmno"},
                    "output": "PASSWORD=hunter2\nok",
                },
            },
        },
        workspace=tmp_path,
        mode="execute",
        adapter="opencode",
        provider="openrouter",
        model="openrouter/cohere/north-mini-code:free",
    )
    assert event is not None
    encoded = json.dumps(event)
    assert event["event_type"] == "developer_command_completed"
    assert str(tmp_path) not in encoded
    assert "hunter2" not in encoded
    assert event["data"]["provider"] == "openrouter"


def test_antigravity_drops_prompt_and_transport_response_deltas(tmp_path: Path):
    prompt_event = agent_public_event(
        {"event": "step_update", "step_update": {"step_type": "user_input", "text_delta": "SECRET PROMPT"}},
        workspace=tmp_path,
        mode="evaluate",
        adapter="antigravity_host",
        provider="google_antigravity",
        model="auto",
    )
    assert prompt_event is None

    response_delta = agent_public_event(
        {"event": "step_update", "step_update": {"step_type": "agent_response", "state": "ACTIVE", "text_delta": "huma"}},
        workspace=tmp_path,
        mode="evaluate",
        adapter="antigravity_host",
        provider="google_antigravity",
        model="auto",
    )
    assert response_delta is None


def test_completed_agent_response_is_single_bounded_redacted_activity(tmp_path: Path):
    secret = "sk-abcdefghijklmnopqrstuvwxyz123456"
    response = agent_response_event(
        adapter="antigravity_host",
        provider="google_antigravity",
        model="claude-sonnet-4-6",
        mode="evaluate",
        text=f"human_decision for {tmp_path} API_KEY={secret}",
        workspace=tmp_path,
    )

    assert response is not None
    encoded = json.dumps(response)
    assert response["event_type"] == "developer_message"
    assert response["data"]["status"] == "response_completed"
    assert response["data"]["provider"] == "google_antigravity"
    assert response["data"]["role"] == "evaluator"
    assert str(tmp_path) not in encoded
    assert secret not in encoded
    assert "API_KEY=<redacted>" in encoded


def test_runtime_activity_is_sanitized(tmp_path: Path):
    event = runtime_activity_event(
        kind="check",
        message="targeted_tests passed",
        phase="verification",
        workspace=tmp_path,
        command=f"cd {tmp_path} && TOKEN=secret-value run-tests",
        output="PASSWORD=hunter2\n24 passed",
        status="passed",
        level="success",
    )
    encoded = json.dumps(event)
    assert str(tmp_path) not in encoded
    assert "secret-value" not in encoded
    assert "hunter2" not in encoded
    assert "24 passed" in encoded
