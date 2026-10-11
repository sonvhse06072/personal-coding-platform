"""Offline one-attempt G0D-T01 PCP fixture Runtime HTTP operator tests.

No model, network, Docker daemon, DB, GitHub or Owner local workspaces.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import subprocess
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/g0d-t01-pcp-operator.py"
SPEC = importlib.util.spec_from_file_location("g0d_t01_pcp_operator", SCRIPT)
op = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(op)
SHA = "a" * 40
JOB = "0123456789abcdef0123456789abcdef"


def job(status="queued", *, commit="b" * 40):
    result = {}
    if status == "waiting_human":
        result = {
            "stage": "awaiting_fixture_only_delivery",
            "commit": commit,
            "changed_files": list(op.ALLOWED_FILES),
        }
    return {
        "http_status": 200,
        "job_id": JOB,
        "project_id": op.PROJECT,
        "source_commit": op.SEED,
        "branch": "ai/" + JOB[:12],
        "job_status": status,
        "result": result,
    }


@pytest.fixture
def local(monkeypatch, tmp_path):
    private = tmp_path / ".pcp-g0d01"
    private.mkdir(mode=0o700)
    monkeypatch.setattr(op.Path, "home", lambda: tmp_path)
    monkeypatch.setattr(op.live, "inspect", lambda *a: {
        "status": "PASS", "g0_job_store_empty": True,
    })
    monkeypatch.setattr(op, "_identity", lambda *a: None)
    return {"repo": tmp_path, "fixture": tmp_path, "private": private}


def test_one_prepare_mints_exact_single_claim_without_model_or_github(
    local, monkeypatch
):
    calls = []
    monkeypatch.setattr(op, "_http", lambda *a: calls.append(a) or job())
    result = op.prepare(local["repo"], local["fixture"], SHA)
    assert result["status"] == "PASS"
    assert result["phase"] == "g0d_t01_pcp_prepared"
    assert result["model_calls_this_command"] == 0
    assert result["github_delivery_enabled"] is False
    assert calls == [("POST", "/v1/g0-fixture/prepare", 400)]
    path = local["private"] / op.JOURNAL
    assert path.stat().st_mode & 0o077 == 0
    payload = json.loads(path.read_text())
    assert payload["state"] == "prepared"
    assert payload["job_id"] == JOB
    assert payload["execute_attempted"] is False
    with pytest.raises(op.g0.GateError, match="already_claimed"):
        op.prepare(local["repo"], local["fixture"], SHA)
    assert len(calls) == 1


def test_preflight_stop_never_creates_claim_or_calls_post(local, monkeypatch):
    monkeypatch.setattr(op.live, "inspect", lambda *a: {"status": "STOP"})
    monkeypatch.setattr(
        op, "_http", lambda *a: (_ for _ in ()).throw(
            AssertionError("preflight must not dispatch")
        ),
    )
    with pytest.raises(op.g0.GateError, match="live_readiness_not_pass"):
        op.prepare(local["repo"], local["fixture"], SHA)
    assert not (local["private"] / op.JOURNAL).exists()


def test_lost_prepare_response_keeps_one_claim_and_forbids_retry(
    local, monkeypatch
):
    monkeypatch.setattr(
        op, "_http", lambda *a: (_ for _ in ()).throw(
            op.g0.GateError("g0_runtime_http_response_lost")
        ),
    )
    with pytest.raises(op.g0.GateError, match="response_lost"):
        op.prepare(local["repo"], local["fixture"], SHA)
    saved = json.loads((local["private"] / op.JOURNAL).read_text())
    assert saved["state"] == "prepare_claimed"
    assert saved["prepare_attempted"] is True
    assert "job_id" not in saved
    with pytest.raises(op.g0.GateError, match="already_claimed"):
        op.prepare(local["repo"], local["fixture"], SHA)


def test_status_does_only_readonly_get_with_one_known_job(local, monkeypatch):
    record = {
        "phase": "pcp", "state": "prepared", "source_sha": SHA, "job_id": JOB,
    }
    (local["private"] / op.JOURNAL).write_text(json.dumps(record))
    (local["private"] / op.JOURNAL).chmod(0o600)
    before = (local["private"] / op.JOURNAL).read_bytes()
    calls = []
    monkeypatch.setattr(op, "_http", lambda *a: calls.append(a) or job())
    report = op.status(local["repo"], local["fixture"], SHA)
    assert report["job_status"] == "queued"
    assert report["retry_authorized"] is False
    assert calls == [("GET", "/v1/g0-fixture/jobs/" + JOB, 30)]
    assert (local["private"] / op.JOURNAL).read_bytes() == before


def test_status_missing_prepared_uuid_preserves_failed_claim(
    local, monkeypatch
):
    path = local["private"] / op.JOURNAL
    path.write_text(json.dumps({
        "phase": "pcp", "state": "prepare_claimed", "source_sha": SHA,
    }))
    path.chmod(0o600)
    monkeypatch.setattr(op, "_http", lambda *a: (_ for _ in ()).throw(
        AssertionError("cannot infer unknown job id")
    ))
    report = op.status(local["repo"], local["fixture"], SHA)
    assert report["status"] == "STOP"
    assert report["retry_authorized"] is False
    assert "manual_reconciliation" in report["reason"]


@pytest.fixture
def prepared(local):
    record = {
        "phase": "pcp", "state": "prepared", "source_sha": SHA, "seed": op.SEED,
        "job_id": JOB, "branch": "ai/" + JOB[:12], "execute_attempted": False,
    }
    path = local["private"] / op.JOURNAL
    path.write_text(json.dumps(record))
    path.chmod(0o600)
    return local


def test_one_execute_then_no_second_attempt(prepared, monkeypatch):
    calls = []
    def http(method, path, timeout):
        calls.append((method, path, timeout))
        return job("queued") if method == "GET" else job("waiting_human")
    monkeypatch.setattr(op, "_http", http)
    result = op.execute(prepared["repo"], prepared["fixture"], SHA)
    assert result["status"] == "PASS"
    assert result["phase"] == "g0d_t01_pcp_executed"
    assert result["model_calls_this_command"] == 1
    assert result["needs_independent_ci_review"] is True
    assert result["github_delivery_enabled"] is False
    assert calls == [
        ("GET", "/v1/g0-fixture/jobs/" + JOB, 30),
        ("POST", "/v1/g0-fixture/jobs/" + JOB + "/execute", 1880),
    ]
    record = json.loads((prepared["private"] / op.JOURNAL).read_text())
    assert record["state"] == "executed"
    assert record["execute_attempted"] is True
    with pytest.raises(op.g0.GateError, match="already_claimed"):
        op.execute(prepared["repo"], prepared["fixture"], SHA)
    assert len(calls) == 2


def test_timeout_after_dispatch_is_durable_and_not_retried(prepared, monkeypatch):
    attempts = []
    def http(method, path, timeout):
        attempts.append(method)
        if method == "GET":
            return job()
        raise op.g0.GateError("g0_docker_exec_timeout")
    monkeypatch.setattr(op, "_http", http)
    with pytest.raises(op.g0.GateError, match="timeout"):
        op.execute(prepared["repo"], prepared["fixture"], SHA)
    path = prepared["private"] / op.JOURNAL
    record = json.loads(path.read_text())
    assert record["state"] == "execute_claimed"
    assert record["execute_attempted"] is True
    with pytest.raises(op.g0.GateError, match="already_claimed"):
        op.execute(prepared["repo"], prepared["fixture"], SHA)
    assert attempts == ["GET", "POST"]


@pytest.mark.parametrize("corruption", [
    lambda item: item.update(project_id="chonhac"),
    lambda item: item.update(source_commit="a"*40),
    lambda item: item.update(branch="benchmark/pcp"),
    lambda item: item.update(job_id="bad"),
    lambda item: item.update(job_status="unknown"),
    lambda item: item.update(result={
        "stage": "awaiting_fixture_only_delivery",
        "commit": "b"*40,
        "changed_files": ["composer.json"],
    }, job_status="waiting_human"),
    lambda item: item.update(result={
        "stage": "awaiting_fixture_only_delivery",
        "commit": "b"*40,
        "changed_files": op.ALLOWED_FILES[:2],
    }, job_status="waiting_human"),
])
def test_wrong_identity_source_or_diff_refuses_acceptance(corruption):
    response = job("waiting_human")
    corruption(response)
    with pytest.raises(op.g0.GateError):
        op._valid_job(response)


def test_http_uses_only_scoped_g0_runtime_and_private_container_token(
    monkeypatch
):
    commands = []
    def fake_run(argv, **kwargs):
        commands.append((argv, kwargs))
        return json.dumps(job())
    monkeypatch.setattr(op.g0, "run", fake_run)
    report = op._http("POST", "/v1/g0-fixture/prepare", 400)
    assert report["http_status"] == 200
    argv, opts = commands[0]
    assert argv[:4] == ["docker", "exec", "-e", "PYTHONDONTWRITEBYTECODE=1"]
    assert argv[4] == op.g0.NAMES["runtime"]
    assert argv[5:7] == ["python3", "-c"]
    assert argv[8:] == ["POST", "/v1/g0-fixture/prepare", "385"]
    assert "os.environ[\"RUNTIME_API_TOKEN\"]" in argv[7]
    assert "ProxyHandler({})" in argv[7]
    assert opts["timeout"] == 400
    assert "GITHUB_DELIVERY_TOKEN" not in json.dumps(argv)
    assert len(commands) == 1


@pytest.mark.parametrize("method,path", [
    ("POST", "/v1/jobs"), ("POST", "/v1/g0-fixture/jobs/notuuid/execute"),
    ("POST", "/v1/g0-fixture/jobs/" + JOB + "/deliver"),
    ("DELETE", "/v1/g0-fixture/jobs/" + JOB),
    ("GET", "/v1/jobs"),
    ("POST", "/v1/g0-fixture/jobs/" + JOB),
])
def test_host_http_allowlist_denies_nonfixture_or_delivery(method, path):
    with pytest.raises(op.g0.GateError, match="not_allowed"):
        op._http(method, path, 40)


def test_help_entrypoint_really_parses_without_model_or_docker():
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--help"],
        cwd=ROOT, capture_output=True, text=True, check=False, timeout=15,
    )
    assert result.returncode == 0, result.stderr
    assert "--expected-sha" in result.stdout
    assert "prepare" in result.stdout
    assert "execute" in result.stdout


def test_operator_source_does_not_handle_delivery_or_global_docker():
    code = SCRIPT.read_text(encoding="utf-8")
    for banned in (
        "docker stop", "docker restart", "docker compose up",
        "ddev start", "git push", "gh pr create", "GITHUB_DELIVERY_TOKEN=",
        "docker system prune", "rm -rf", "docker compose run",
    ):
        assert banned not in code
    assert "execute_attempted" in code
    assert "os.O_EXCL" in code
    assert "live.inspect(repo, fixture, sha)" in code
