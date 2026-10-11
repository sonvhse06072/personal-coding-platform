"""Offline negative regression tests for exact PCP session -> one direct turn.

No test contacts a provider, runs Docker or touches Owner Codex/fixture data.
"""
from __future__ import annotations

from datetime import datetime, timezone
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/g0-direct-only-parity-continuation.py"
SPEC = importlib.util.spec_from_file_location("g0_direct_only_continuation", SCRIPT)
cont = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(cont)
EXPECTED_SHA = "a" * 40


@pytest.fixture
def session(monkeypatch, tmp_path):
    private = tmp_path / ".pcp-g0d01"
    profile = private / "provider/pcp"
    path = profile / "sessions/2026/10/11"
    path.mkdir(parents=True)
    for directory in (private, private / "provider", profile):
        directory.chmod(0o700)
    journal = private / "model-parity-probe.json"
    journal.write_text("{}", encoding="utf-8")
    journal.chmod(0o600)
    session_file = path / "rollout-synthetic.jsonl"
    original = cont.original
    monkeypatch.setattr(cont.Path, "home", lambda: tmp_path)
    monkeypatch.setattr(original, "_journal_path", lambda: journal)
    monkeypatch.setattr(cont.auth, "_auth_dir", lambda arm: private / "provider" / arm)
    monkeypatch.setattr(original, "_read_existing_journal", lambda: {
        "state": "failed", "failed_arm": "pcp",
        "attempted_arms": ["pcp"], "completed_arms": [],
        "model": original.EXPECTED_MODEL,
        "reasoning_effort": original.EXPECTED_EFFORT,
        "codex_cli_version": original.EXPECTED_CLI,
        "source_sha": cont.EXPECTED_ORIGINAL_SHA,
    })
    monkeypatch.setattr(original, "_prepared_context",
                        lambda repo, fixture, sha: ({"PATH": "/usr/bin"}, {
                            "deployed_source_sha": cont.auth.DEPLOYED_SHA,
                            "installed_codex_cli_version": original.EXPECTED_CLI,
                        }))
    monkeypatch.setattr(cont.g0, "exists", lambda k, name: False)
    monkeypatch.setattr(cont.g0, "inspect", lambda kind, name: {
        "Labels": {"com.docker.compose.project": cont.g0.PROJECT},
        "Internal": False, "Containers": {},
    })
    monkeypatch.setattr(cont.g0, "require_headroom", lambda *a: None)

    def canonical(text):
        return {"type": "response_item", "payload": {
            "type": "message", "role": "user",
            "content": [{"type": "input_text", "text": text}],
        }}
    dt = datetime.now(timezone.utc)
    events = [
        {"type": "session_meta", "payload": {
            "cli_version": cont.original.EXPECTED_CLI,
        }},
        canonical("non-model system context received before requested probe"),
        {"type": "turn_context", "payload": {
            "model": cont.original.EXPECTED_MODEL,
            "effort": cont.original.EXPECTED_EFFORT,
        }},
        canonical(cont.original.PROBE_PROMPT),
        {"type": "event_msg", "payload": {"type": "token_count"}},
        {"type": "event_msg", "timestamp": dt.isoformat(), "payload": {
            "type": "task_complete",
            "last_agent_message": cont.original.EXPECTED_RESPONSE,
        }},
    ]

    def write(values):
        session_file.write_text(
            "\n".join(json.dumps(v) for v in values) + "\n", encoding="utf-8"
        )
        # Journal is supposed to be written *after* the model terminal event.
        os.utime(journal, None)
    write(events)
    return SimpleNamespace(
        repo=tmp_path, fixture=tmp_path, root=private,
        events=events, write=write, file=session_file, journal=journal,
    )


def test_attribution_accepts_one_exact_canonical_prompt_then_one_completion(session):
    evidence = cont._reconcile_existing_session()
    assert evidence["pcp_turn_reconciled"] is True
    assert evidence["original_wrapper_status"] == "failed_timeout_or_spawn"
    assert evidence["canonical_user_item_count"] == 2
    assert evidence["extra_user_inputs_before_fixed_prompt"] == 1
    assert evidence["canonical_user_input_after_fixed_prompt"] is False
    assert evidence["model"] == "gpt-6-luna"
    assert evidence["reasoning_effort"] == "medium"
    assert evidence["response_verified"] and evidence["token_count_present"]
    assert "prompt" not in evidence and "auth" not in evidence


@pytest.mark.parametrize("alter", [
    lambda d: d[3]["payload"]["content"][0].update(text="wrong prompt"),
    lambda d: d[5]["payload"].update(last_agent_message="wrong response"),
    lambda d: d[2]["payload"].update(model="other-model"),
    lambda d: d[2]["payload"].update(effort="high"),
    lambda d: d[0]["payload"].update(cli_version="0.999.0"),
    lambda d: d.append({
        "type": "response_item", "payload": {
            "type": "message", "role": "user",
            "content": [{"type": "input_text", "text": "later user prompt"}],
        }
    }),
    lambda d: d.insert(5, {"type": "event_msg", "payload": {"type": "error"}}),
    lambda d: d.append(d[-1]),
])
def test_wrong_prompt_model_reply_or_interleaved_error_stops_reconciliation(
    session, alter
):
    events = json.loads(json.dumps(session.events))
    alter(events)
    session.write(events)
    with pytest.raises(cont.g0.GateError, match="attribution_inconclusive"):
        cont._reconcile_existing_session()


def test_canonical_prompt_after_completion_does_not_get_attributed(session):
    items = json.loads(json.dumps(session.events))
    items[3], items[5] = items[5], items[3]
    session.write(items)
    with pytest.raises(cont.g0.GateError, match="attribution_inconclusive"):
        cont._reconcile_existing_session()


def test_multiple_sessions_are_ambiguous_without_provider_call(session):
    additional = session.file.with_name("rollout-another.jsonl")
    additional.write_text(session.file.read_text(encoding="utf-8"), encoding="utf-8")
    with pytest.raises(cont.g0.GateError, match="attribution_not_unique"):
        cont._reconcile_existing_session()


def test_existing_failed_original_is_never_replaced_by_reconciliation(session):
    before = session.journal.read_bytes()
    out = cont.status(session.repo, session.fixture, EXPECTED_SHA)
    assert out["pcp_evidence"]["pcp_turn_reconciled"] is True
    assert out["original_failed_journal_preserved"] is True
    assert out["model_calls_this_command"] == 0
    assert out["direct_only_call_authorized_by_operator"] is True
    assert out["ready_to_dispatch_g0d_t01"] is False
    assert session.journal.read_bytes() == before
    assert not (session.root / cont.CONTINUATION_NAME).exists()


def test_one_new_direct_only_call_and_private_separate_journal(session, monkeypatch):
    before = session.journal.read_bytes()
    attempts = []
    def direct_once(repo, env):
        attempts.append("direct")
        assert env["PATH"] == "/usr/bin"
        return {
            "response_verified": True, "terminal": "completed",
            "usage": {"input_tokens": 5, "output_tokens": 2},
            "elapsed_seconds": 1.1,
            "model": cont.original.EXPECTED_MODEL,
            "reasoning_effort": cont.original.EXPECTED_EFFORT,
            "codex_cli_version": cont.original.EXPECTED_CLI,
        }
    monkeypatch.setattr(cont, "_direct_one_call", direct_once)
    result = cont.direct(session.repo, session.fixture, EXPECTED_SHA)
    assert attempts == ["direct"]
    assert result["status"] == "PASS"
    assert result["original_wrapper_timeout_preserved"] is True
    assert result["direct_only_model_calls_attempted"] == 1
    assert result["ready_to_dispatch_g0d_t01"] is False
    assert session.journal.read_bytes() == before
    continuation = session.root / cont.CONTINUATION_NAME
    assert continuation.stat().st_mode & 0o077 == 0
    saved = json.loads(continuation.read_text())
    assert saved["state"] == "direct_completed"
    assert saved["direct_attempted"] and saved["direct_completed"]
    with pytest.raises(cont.g0.GateError, match="already_recorded"):
        cont.direct(session.repo, session.fixture, EXPECTED_SHA)
    assert attempts == ["direct"]


def test_direct_timeout_keeps_failure_evidence_and_blocks_retries(session, monkeypatch):
    monkeypatch.setattr(cont, "_direct_one_call",
                        lambda *a: (_ for _ in ()).throw(
                            cont.g0.GateError("g0_direct_model_or_wrapper_timeout")
                        ))
    with pytest.raises(cont.g0.GateError, match="wrapper_timeout"):
        cont.direct(session.repo, session.fixture, EXPECTED_SHA)
    state = json.loads((session.root / cont.CONTINUATION_NAME).read_text())
    assert state["state"] == "failed"
    assert state["direct_attempted"] and not state["direct_completed"]
    assert "wrapper_timeout" in state["error_class"]
    with pytest.raises(cont.g0.GateError, match="already_recorded"):
        cont.direct(session.repo, session.fixture, EXPECTED_SHA)


def test_direct_subprocess_uses_only_direct_image_and_no_php_files(
    session, monkeypatch
):
    args = []
    def fake_run(argv, **kw):
        args.append((argv, kw))
        return SimpleNamespace(
            returncode=0, stdout="\n".join([
                json.dumps({"type": "item.completed", "item": {
                    "type": "agent_message", "text": cont.original.EXPECTED_RESPONSE,
                }}),
                json.dumps({"type": "turn.completed", "usage": {
                    "input_tokens": 20, "output_tokens": 2,
                }}),
            ]), stderr="private-not-printed",
        )
    monkeypatch.setattr(cont.original, "_probe_command",
                        lambda repo, arm: [
                            "docker", "compose", "run", "--rm", "--no-deps",
                            "-T", "auth_" + arm, "exec", "--sandbox", "read-only",
                            cont.original.PROBE_PROMPT,
                        ])
    monkeypatch.setattr(cont.subprocess, "run", fake_run)
    report = cont._direct_one_call(session.repo, {"PATH": "/usr/bin"})
    assert report["response_verified"] is True
    assert len(args) == 1
    argv, options = args[0]
    assert argv[argv.index("--name")+1] == cont.DIRECT_CONTAINER
    assert argv[argv.index("exec")-1] == "auth_direct"
    assert "auth_pcp" not in argv
    assert "run" in argv and "--rm" in argv
    assert options["capture_output"] is True
    assert options["timeout"] == cont.TIMEOUT_SECONDS
    assert "private-not-printed" not in json.dumps(report)


def test_continuation_claim_is_atomic_not_a_renewal(session):
    data = {"state": "started"}
    cont._claim_continuation(data)
    with pytest.raises(cont.g0.GateError, match="already_recorded"):
        cont._claim_continuation(data)
    assert json.loads((session.root / cont.CONTINUATION_NAME).read_text()) == data



def test_real_cli_help_enters_entrypoint_without_model_or_docker():
    """A real Python process must reach argparse; no credentials or model calls."""
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--help"],
        cwd=ROOT, capture_output=True, text=True, check=False,
        timeout=15, env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
    )
    assert result.returncode == 0, result.stderr
    assert "status" in result.stdout
    assert "direct" in result.stdout
    assert "--expected-sha" in result.stdout


def test_cli_status_main_reconciles_synthetic_session_without_side_effects(
    session, monkeypatch, capsys
):
    """Exercise actual main() argument parsing and read-only status path."""
    before = session.journal.read_bytes()

    def forbidden(*args, **kwargs):
        raise AssertionError("status must not call model, direct arm or Docker")

    monkeypatch.setattr(cont, "direct", forbidden)
    monkeypatch.setattr(cont, "_direct_one_call", forbidden)
    monkeypatch.setattr(cont.subprocess, "run", forbidden)
    monkeypatch.setattr(
        cont.sys, "argv", [str(SCRIPT), "status", "--expected-sha", EXPECTED_SHA]
    )

    assert cont.main() == 0
    report = json.loads(capsys.readouterr().out)
    assert report["status"] == "PASS"
    assert report["phase"] == "g0_pcp_recovered_direct_pending"
    assert report["pcp_evidence"]["pcp_turn_reconciled"] is True
    assert report["model_calls_this_command"] == 0
    assert report["ready_to_dispatch_g0d_t01"] is False
    assert session.journal.read_bytes() == before
    assert not (session.root / cont.CONTINUATION_NAME).exists()


def test_no_pcp_retry_or_fixture_ddev_delivery():
    script = SCRIPT.read_text(encoding="utf-8")
    for forbidden in (
        "ddev start", "ddev poweroff", "docker system prune",
        "docker restart", "docker stop", "gh pr create",
        "git push", "rm -rf", "git reset --hard",
        "PCP_G0_EXECUTION_ENABLED=owner-approved",
        "OPENAI_API_KEY=", "GITHUB_DELIVERY_TOKEN=",
    ):
        assert forbidden not in script
    assert 'original._probe_command(repo, "direct")' in script
    assert 'original._probe_command(repo, "pcp")' not in script
