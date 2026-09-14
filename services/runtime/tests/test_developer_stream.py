import json
from pathlib import Path

from app.developer_stream import codex_public_event


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
