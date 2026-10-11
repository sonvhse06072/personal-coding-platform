"""Offline, synthetic-only regression for ONE timed-out G0 Direct probe.

No provider calls, Docker writes, source changes or Owner data access.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/g0-direct-parity-timeout-forensics.py"
SPEC = importlib.util.spec_from_file_location("g0_direct_timeout_forensics", SCRIPT)
forensics = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(forensics)


@pytest.fixture
def attempt(monkeypatch, tmp_path):
    root = tmp_path / ".pcp-g0d01"
    direct = root / "provider/direct"
    session_dir = direct / "sessions/2026/10/11"
    session_dir.mkdir(parents=True)
    for directory in (root, root / "provider", direct):
        directory.chmod(0o700)
    journal = root / forensics.cont.CONTINUATION_NAME
    attempt_state = {
        "state": "failed",
        "error_class": "g0_direct_model_or_wrapper_timeout",
        "source_sha": forensics.ORIGINAL_DIRECT_ATTEMPT_SHA,
        "original_journal_status": "failed",
        "direct_attempted": True,
        "direct_completed": False,
        "ready_to_dispatch_g0d_t01": False,
        "pcp": {"pcp_turn_reconciled": True},
    }
    journal.write_text(json.dumps(attempt_state), encoding="utf-8")
    journal.chmod(0o600)
    file = session_dir / "rollout-fake.jsonl"
    dt = datetime.now(timezone.utc) - timedelta(seconds=10)

    def canonical(text):
        return {"type": "response_item", "payload": {
            "type": "message", "role": "user",
            "content": [{"type": "input_text", "text": text}],
        }}

    events = [
        {"type": "session_meta", "payload": {
            "cli_version": forensics.cont.original.EXPECTED_CLI,
        }},
        canonical("synthetic system context before fixed probe"),
        {"type": "turn_context", "payload": {
            "model": forensics.cont.original.EXPECTED_MODEL,
            "effort": forensics.cont.original.EXPECTED_EFFORT,
        }},
        canonical(forensics.cont.original.PROBE_PROMPT),
        {"type": "event_msg", "payload": {"type": "token_count"}},
        {"type": "event_msg", "timestamp": dt.isoformat(), "payload": {
            "type": "task_complete",
            "last_agent_message": forensics.cont.original.EXPECTED_RESPONSE,
        }},
    ]

    def write(items):
        file.write_text(
            "\n".join(json.dumps(x) for x in items) + "\n", encoding="utf-8"
        )
        os.utime(journal, None)

    write(events)
    monkeypatch.setattr(forensics.cont.Path, "home", lambda: tmp_path)
    monkeypatch.setattr(forensics.cont.original, "_prepared_context",
                        lambda *args: ({}, {}))
    monkeypatch.setattr(forensics.cont, "_original_failed_journal",
                        lambda: {"state": "failed"})
    monkeypatch.setattr(forensics.cont, "_reconcile_existing_session",
                        lambda: {"pcp_turn_reconciled": True})
    monkeypatch.setattr(forensics.g0, "exists", lambda kind, name: False)
    monkeypatch.setattr(
        forensics.g0, "inspect",
        lambda kind, name: (_ for _ in ()).throw(
            AssertionError("no docker inspect for an absent G0 container")
        )
    )
    return {"root": root, "journal": journal, "file": file,
            "events": events, "write": write, "state": attempt_state,
            "repo": tmp_path, "fixture": tmp_path}


def test_direct_terminal_recovered_preserving_both_failed_journals(attempt):
    original = json.dumps(attempt["state"], sort_keys=True)
    before = attempt["journal"].read_bytes()
    output = forensics.inspect(attempt["repo"], attempt["fixture"], "b" * 40)
    assert output["status"] == "PASS"
    assert output["phase"] == "g0_direct_timeout_forensics"
    assert output["direct_evidence"]["direct_turn_reconciled"] is True
    assert output["direct_evidence"]["canonical_user_item_count"] == 2
    assert output["direct_evidence"]["session_events_examined"] == 6
    assert output["direct_container_state"] == "absent"
    assert output["direct_session_candidates"] == 1
    assert output["direct_retry_authorized"] is False
    assert output["model_calls_this_command"] == 0
    assert output["ready_to_dispatch_g0d_t01"] is False
    assert attempt["journal"].read_bytes() == before
    assert json.dumps(json.loads(before), sort_keys=True) == original
    assert not (attempt["root"] / "recovered-model-parity.json").exists()


@pytest.mark.parametrize("alter", [
    lambda x: x[3]["payload"]["content"][0].update(text="wrong fixed prompt"),
    lambda x: x[5]["payload"].update(last_agent_message="not the expected reply"),
    lambda x: x[2]["payload"].update(model="different-model"),
    lambda x: x[2]["payload"].update(effort="high"),
    lambda x: x[0]["payload"].update(cli_version="0.999"),
    lambda x: x.insert(5, {"type": "event_msg",
                          "payload": {"type": "error"}}),
    lambda x: x.pop(),
    lambda x: x.append({"type": "response_item", "payload": {
        "type": "message", "role": "user",
        "content": [{"type": "input_text", "text": "unrelated newer turn"}],
    }}),
    lambda x: x.append(x[-1]),
])
def test_incorrect_or_incomplete_direct_session_cannot_pass(attempt, alter):
    values = json.loads(json.dumps(attempt["events"]))
    alter(values)
    attempt["write"](values)
    evidence = forensics.inspect(
        attempt["repo"], attempt["fixture"], "b" * 40
    )
    assert evidence["status"] == "STOP"
    assert evidence["reason"] == "g0_direct_session_attribution_inconclusive"
    assert evidence["model_calls_this_command"] == 0
    assert evidence["direct_retry_authorized"] is False


def test_ambiguous_session_is_not_attributed(attempt):
    other = attempt["file"].with_name("rollout-another.jsonl")
    other.write_bytes(attempt["file"].read_bytes())
    outcome = forensics.inspect(
        attempt["repo"], attempt["fixture"], "b" * 40
    )
    assert outcome["status"] == "STOP"
    assert outcome["reason"] == "g0_direct_session_not_unique"
    assert outcome["direct_session_candidates"] == 2


def test_completion_after_wrapper_failure_not_accepted(attempt):
    entries = json.loads(json.dumps(attempt["events"]))
    entries[5]["timestamp"] = (
        datetime.now(timezone.utc) + timedelta(seconds=120)
    ).isoformat()
    attempt["write"](entries)
    output = forensics.inspect(attempt["repo"], attempt["fixture"], "b" * 40)
    assert output["status"] == "STOP"
    assert not output["direct_evidence"]["gates"][
        "completion_before_failed_journal"
    ]


def test_journal_claim_cannot_be_mutated_or_relabeled(attempt):
    attempt["state"]["state"] = "direct_completed"
    attempt["journal"].write_text(json.dumps(attempt["state"]))
    with pytest.raises(
        forensics.g0.GateError, match="failed_continuation_not_exact"
    ):
        forensics.inspect(attempt["repo"], attempt["fixture"], "b" * 40)


def test_running_named_direct_container_is_not_misreported(attempt, monkeypatch):
    monkeypatch.setattr(forensics.g0, "exists", lambda *a: True)
    monkeypatch.setattr(forensics.g0, "inspect", lambda kind, name: {
        "Name": "/" + forensics.cont.DIRECT_CONTAINER,
        "Config": {"Labels": {
            "com.docker.compose.project": forensics.g0.PROJECT,
            "com.docker.compose.service": "auth_direct",
        }},
        "NetworkSettings": {"Networks": {
            forensics.cont.auth.G0_AUTH_NETWORKS["direct"]: {},
        }},
        "State": {"Running": True},
    })
    output = forensics.inspect(attempt["repo"], attempt["fixture"], "b" * 40)
    assert output["status"] == "STOP"
    assert output["reason"] == "g0_direct_container_still_running"
    assert output["direct_container_state"] == "running"


def test_foreign_container_refused_without_changes(attempt, monkeypatch):
    monkeypatch.setattr(forensics.g0, "exists", lambda *a: True)
    monkeypatch.setattr(forensics.g0, "inspect", lambda kind, name: {
        "Name": "/" + forensics.cont.DIRECT_CONTAINER,
        "Config": {"Labels": {"com.docker.compose.project": "unrelated"}},
        "NetworkSettings": {"Networks": {}}, "State": {"Running": False},
    })
    with pytest.raises(
        forensics.g0.GateError, match="container_identity_unverified"
    ):
        forensics.inspect(attempt["repo"], attempt["fixture"], "b" * 40)


def test_main_real_parser_dispatch_synthetic_readonly(
    attempt, monkeypatch, capsys
):
    monkeypatch.setattr(forensics.sys, "argv",
                        [str(SCRIPT), "inspect", "--expected-sha", "b" * 40])
    assert forensics.main() == 0
    data = json.loads(capsys.readouterr().out)
    assert data["status"] == "PASS"
    assert data["direct_retry_authorized"] is False


def test_real_help_cli_entrypoint_without_docker_or_provider():
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--help"],
        cwd=ROOT, capture_output=True, text=True, check=False,
        timeout=15, env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
    )
    assert result.returncode == 0, result.stderr
    assert "--expected-sha" in result.stdout
    assert "inspect" in result.stdout


def test_source_contains_no_mutating_or_model_execution_paths():
    source = SCRIPT.read_text(encoding="utf-8")
    for text in (
        "ddev start", "docker stop", "docker rm", "docker compose run",
        "git push", "git reset --hard", "subprocess.run(",
        "_probe_command(", "_direct_one_call(", "_write_continuation(",
        "_claim_continuation(", "_private_write(", "gh pr create",
        "OPENAI_API_KEY=", "GITHUB_DELIVERY_TOKEN=",
    ):
        assert text not in source
