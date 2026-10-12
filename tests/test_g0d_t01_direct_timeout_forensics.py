"""Synthetic and disposable-Git tests for read-only G0D-T01 Direct timeout forensics.

No real G0 Docker, provider API, global Codex, GitHub, DDEV, or other project.
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
SCRIPT = ROOT / "scripts/g0d-t01-direct-timeout-forensics.py"
SPEC = importlib.util.spec_from_file_location("g0d_t01_direct_forensics", SCRIPT)
op = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(op)
SHA = "a" * 40
NOW = datetime.now(timezone.utc)


@pytest.fixture
def attempt(monkeypatch, tmp_path):
    journal = tmp_path / "g0d-t01-direct-attempt.json"
    claim = {
        "arm": "direct", "task_id": "G0D-T01",
        "state": "execute_claimed", "source_sha": op.ATTEMPT_SOURCE_SHA,
        "seed": op.direct.SEED, "branch": op.direct.BRANCH,
        "model": op.direct.MODEL, "reasoning_effort": op.direct.EFFORT,
        "codex_cli_version": op.direct.CLI_VERSION,
        "execute_attempted": True, "github_delivery_enabled": False,
        "prepare_started_at": (NOW - timedelta(hours=2)).isoformat(),
        "execute_started_at": (NOW - timedelta(hours=1)).isoformat(),
    }
    journal.write_text(json.dumps(claim), encoding="utf-8")
    journal.chmod(0o600)
    monkeypatch.setattr(op.direct, "_journal_path", lambda: journal)
    monkeypatch.setattr(op.direct, "_read_journal", lambda: json.loads(journal.read_text()))
    return {"journal": journal, "claim": claim, "start": NOW - timedelta(hours=1)}


def test_claim_is_exact_and_immutable(attempt):
    before = attempt["journal"].read_bytes()
    record, started = op._attempt()
    assert record["state"] == "execute_claimed"
    assert abs(started.timestamp() - attempt["start"].timestamp()) < 1
    assert before == attempt["journal"].read_bytes()


@pytest.mark.parametrize("key,value", [
    ("state", "executed"), ("execute_attempted", False),
    ("commit", "e"*40), ("arm", "pcp"), ("branch", "main"),
    ("source_sha", "b"*40), ("model", "unapproved-model"),
    ("github_delivery_enabled", True), ("reasoning_effort", "high"),
])
def test_claim_mutation_refused(attempt, key, value):
    doc = attempt["claim"]
    doc[key] = value
    attempt["journal"].write_text(json.dumps(doc))
    with pytest.raises(op.g0.GateError, match="original_claim_not_exact"):
        op._attempt()


def _user(text):
    return {"type": "response_item", "payload": {
        "type": "message", "role": "user",
        "content": [{"type": "input_text", "text": text}],
    }}


def _events(start, *, exact_prompt="FROZEN-G0-PROMPT"):
    end = start + timedelta(seconds=123)
    return [
        {"type": "session_meta", "timestamp": start.isoformat(),
         "payload": {"cli_version": op.direct.CLI_VERSION}},
        _user("injected tool preamble preceding actual task"),
        {"type": "turn_context", "payload": {
            "model": op.direct.MODEL, "effort": op.direct.EFFORT,
        }},
        _user(exact_prompt),
        {"type": "event_msg", "payload": {"type": "token_count"}},
        {"type": "event_msg", "timestamp": end.isoformat(),
         "payload": {
             "type": "task_complete", "last_agent_message": "Work done",
         }},
    ]


@pytest.fixture
def session(monkeypatch, tmp_path):
    prompt = "FROZEN-G0-PROMPT"
    monkeypatch.setattr(op.direct, "_fixed_prompt", lambda: prompt)
    started = NOW - timedelta(minutes=10)
    file = tmp_path / "rollout-direct.jsonl"
    items = _events(started)
    def write(events):
        file.write_text(
            "\n".join(json.dumps(x) for x in events) + "\n", encoding="utf-8"
        )
    write(items)
    return {"path": file, "start": started, "events": items, "write": write}


def test_original_session_complete_without_wrapper_success(session):
    original = session["path"].read_bytes()
    report = op._rollout(session["path"], session["start"])
    assert report["completed_turn_attributed"] is True
    assert all(report["gates"].values())
    assert report["session_events_examined"] == 6
    assert session["path"].read_bytes() == original


@pytest.mark.parametrize("change", [
    lambda x: x.pop(),
    lambda x: x.append(_user("new user task after fixed prompt")),
    lambda x: x.append(x[-1]),
    lambda x: x.__setitem__(2, {"type": "turn_context", "payload": {
        "model": "wrong", "effort": op.direct.EFFORT,
    }}),
    lambda x: x.__setitem__(3, _user("not the frozen prompt")),
    lambda x: x.append({"type": "event_msg", "payload": {"type": "error"}}),
])
def test_inconclusive_original_rollout_cannot_be_reconciled(session, change):
    events = json.loads(json.dumps(session["events"]))
    change(events)
    session["write"](events)
    evidence = op._rollout(session["path"], session["start"])
    assert evidence["completed_turn_attributed"] is False


def test_malformed_rollout_stops_without_writes(session):
    session["path"].write_text("{invalid JSON")
    with pytest.raises(op.g0.GateError, match="session_unreadable"):
        op._rollout(session["path"], session["start"])


def test_no_foreign_parity_session_attribution(monkeypatch, session, tmp_path):
    root = tmp_path / ".pcp-g0d01"
    profile = root / "provider/direct"
    sessions = profile / "sessions/2026/10/12"
    sessions.mkdir(parents=True)
    for directory in (root, root/"provider", profile):
        directory.chmod(0o700)
    good = sessions / "rollout-coding.jsonl"
    good.write_bytes(session["path"].read_bytes())
    old = sessions / "rollout-prior-parity.jsonl"
    old.write_bytes(session["path"].read_bytes())
    historic = NOW - timedelta(hours=5)
    os.utime(old, (historic.timestamp(), historic.timestamp()))
    monkeypatch.setattr(op.Path, "home", lambda: tmp_path)
    monkeypatch.setattr(op.auth, "_auth_dir", lambda arm: profile)
    result = op._session_evidence(session["start"])
    assert result["candidate_count"] == 1
    assert result["reconciled"] is True
    assert "gates" in result
    # A second new rollout blocks any automatic attribution.
    os.utime(old, None)
    result = op._session_evidence(session["start"])
    assert result["candidate_count"] == 2
    assert result["reconciled"] is False


@pytest.mark.parametrize("state,service,foreign,expected", [
    ("absent", "direct", False, "absent"),
    ("running", "direct", False, "running"),
    ("not_running", "direct", False, "not_running"),
    ("running", "other", False, "error"),
    ("absent", "direct", True, "error"),
])
def test_exact_g0_container_identity_or_absence_only(
    monkeypatch, tmp_path, state, service, foreign, expected
):
    name = op.direct.DIRECT_CONTAINER
    net = op.auth.G0_AUTH_NETWORKS["direct"]
    members = (
        {"id": {"Name": "foreign"}} if foreign else
        {"id": {"Name": name}} if state == "running" else {}
    )
    network = {
        "Internal": False, "Labels": {"com.docker.compose.project": op.g0.PROJECT},
        "Containers": members,
    }
    workspace = tmp_path / "direct"
    workspace.mkdir()
    profile = tmp_path / "auth"
    profile.mkdir()
    monkeypatch.setattr(op.direct, "_workspace", lambda: workspace)
    monkeypatch.setattr(op.auth, "_auth_dir", lambda arm: profile)
    image = {"Id": "sha256:image123"}
    container = {
        "Name": "/" + name,
        "Config": {"Labels": {
            "com.docker.compose.project": op.g0.PROJECT,
            "com.docker.compose.service": service,
        }},
        "State": {"Running": state == "running"},
        "Image": image["Id"],
        "NetworkSettings": {"Networks": {net: {}}},
        "HostConfig": {
            "ReadonlyRootfs": True, "Privileged": False, "PortBindings": {},
        },
        "Mounts": [
            {"Destination": "/home/coder/.codex-direct", "Type": "bind",
             "Source": str(profile), "RW": True},
            {"Destination": "/g0/direct-workspace", "Type": "bind",
             "Source": str(workspace), "RW": True},
            {"Destination": "/tmp", "Type": "tmpfs", "RW": True},
        ],
    }
    monkeypatch.setattr(op.g0, "exists",
                        lambda typ, thing: state != "absent")
    def inspect(kind, name_arg):
        return (network if kind == "network" else
                image if kind == "image" else container)
    monkeypatch.setattr(op.g0, "inspect", inspect)
    if expected == "error":
        with pytest.raises(op.g0.GateError):
            op._container()
    else:
        assert op._container() == expected


@pytest.fixture
def real_fixture_git(monkeypatch, tmp_path):
    # Standalone disposable Git fixture; NO checkout/user repo involved.
    repo = tmp_path / "workspace"
    repo.mkdir()
    subprocess.run(
        ["git", "init", "-q", "-b", op.direct.BRANCH, str(repo)],
        check=True, capture_output=True, timeout=15,
    )
    for file in op.direct.ALLOWED_FILES:
        path = repo / file
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("baseline\n")
    subprocess.run(["git", "-C", str(repo), "add", "--all"],
                   check=True, capture_output=True, timeout=15)
    subprocess.run([
        "git", "-C", str(repo), "-c", "user.name=fixture",
        "-c", "user.email=fixture@invalid", "commit", "-q", "-m", "seed",
    ], check=True, capture_output=True, timeout=15)
    original = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "HEAD"],
        check=True, capture_output=True, text=True, timeout=15,
    ).stdout.strip()
    monkeypatch.setattr(op.direct, "SEED", original)
    monkeypatch.setattr(op.direct, "_workspace", lambda: repo)
    for file in op.direct.ALLOWED_FILES:
        (repo / file).write_text("baseline\nnew valid content\n")
    return repo


def test_real_git_audit_reads_only_three_bounded_paths(real_fixture_git):
    repo = real_fixture_git
    index_before = (repo / ".git/index").read_bytes()
    report = op._workspace_evidence()
    assert report["within_three_file_contract"] is True
    assert report["tracked_changed_count"] == 3
    assert report["untracked_or_out_of_scope"] is False
    assert report["diff_check_pass"] is True
    assert report["same_frozen_seed_ancestor"] is True
    assert len(report["git_blob_hashes"]) == 3
    assert (repo / ".git/index").read_bytes() == index_before


def test_real_git_foreign_untracked_file_blocks_acceptance(real_fixture_git):
    extra = real_fixture_git / "random.txt"
    extra.write_text("unexpected file")
    report = op._workspace_evidence()
    assert report["within_three_file_contract"] is False
    assert report["untracked_or_out_of_scope"] is True
    assert report["git_blob_hashes"] == {}


def test_read_only_recovery_requires_both_model_and_workspace(monkeypatch, attempt):
    monkeypatch.setattr(op.g0, "require_local_docker_context", lambda: None)
    monkeypatch.setattr(op.g0, "require_exact_repo", lambda *a: None)
    monkeypatch.setattr(op.live, "_activated_state", lambda: None)
    monkeypatch.setattr(op.live, "_docker_boundary", lambda *a: None)
    monkeypatch.setattr(op, "_container", lambda: "absent")
    monkeypatch.setattr(op, "_session_evidence", lambda *_: {
        "reconciled": True, "candidate_count": 1,
        "completed_turn_attributed": True,
    })
    monkeypatch.setattr(op, "_workspace_evidence", lambda: {
        "same_frozen_seed_ancestor": True, "within_three_file_contract": True,
        "untracked_or_out_of_scope": False, "diff_check_pass": True,
    })
    report = op.inspect(ROOT, ROOT, SHA)
    assert report["status"] == "PASS"
    assert report["recoverable_without_model"] is True
    assert report["wrapper_status"] == "failed_timeout"
    assert report["retry_authorized"] is False
    assert report["model_calls_this_command"] == 0
    monkeypatch.setattr(op, "_container", lambda: "running")
    report = op.inspect(ROOT, ROOT, SHA)
    assert report["status"] == "STOP"
    assert report["recoverable_without_model"] is False


def test_no_session_cannot_be_mistaken_for_model_success(monkeypatch, attempt):
    monkeypatch.setattr(op.g0, "require_local_docker_context", lambda: None)
    monkeypatch.setattr(op.g0, "require_exact_repo", lambda *a: None)
    monkeypatch.setattr(op.live, "_activated_state", lambda: None)
    monkeypatch.setattr(op.live, "_docker_boundary", lambda *a: None)
    monkeypatch.setattr(op, "_container", lambda: "absent")
    monkeypatch.setattr(op, "_session_evidence", lambda *_: {
        "reconciled": False, "candidate_count": 0,
        "reason": "g0_direct_coding_session_not_unique",
    })
    monkeypatch.setattr(op, "_workspace_evidence", lambda: {
        "same_frozen_seed_ancestor": True, "within_three_file_contract": True,
        "untracked_or_out_of_scope": False, "diff_check_pass": True,
    })
    report = op.inspect(ROOT, ROOT, SHA)
    assert report["status"] == "STOP"
    assert report["retry_authorized"] is False
    assert report["recoverable_without_model"] is False


def test_help_is_not_model_inference_or_docker_call():
    run = subprocess.run(
        [sys.executable, str(SCRIPT), "--help"],
        cwd=ROOT, capture_output=True, text=True, check=False, timeout=15,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
    )
    assert run.returncode == 0, run.stderr
    assert "inspect" in run.stdout
    assert "--expected-sha" in run.stdout


def test_script_has_no_mutation_or_provider_action():
    source = SCRIPT.read_text(encoding="utf-8")
    for forbidden in (
        "docker compose run", "docker stop", "docker restart", "docker rm",
        "git add", "git commit", "git push", "gh pr create",
        "_direct_one_call(", "_commit_scope(", "_save(",
        "GITHUB_DELIVERY_TOKEN=", "OPENAI_API_KEY=",
        "ddev start", "subprocess.Popen",
    ):
        assert forbidden not in source
    assert 'GIT_OPTIONAL_LOCKS' in source
    assert 'readonly' in source.lower() or 'read-only' in source.lower()
