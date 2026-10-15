"""G1-T01 existing proxy expiry recovery: synthetic, no Docker/model calls."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import importlib.util
import json
from pathlib import Path
import subprocess
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "scripts/g1-direct-existing-proxy-expiry-continuation.py"
spec = importlib.util.spec_from_file_location("g1_direct_proxy_expiry", SOURCE)
assert spec and spec.loader
g1 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(g1)


def done(rc=0, stdout="", stderr=""):
    return subprocess.CompletedProcess([], rc, stdout, stderr)


def lifetime(duration, *, exit_code=1, running=False, oom=False):
    end = datetime(2026, 10, 15, 10, 0, tzinfo=timezone.utc)
    start = end - timedelta(seconds=duration)
    return {
        "Running": running, "ExitCode": exit_code,
        "OOMKilled": oom, "Error": "",
        "StartedAt": start.isoformat(), "FinishedAt": end.isoformat(),
    }


@pytest.mark.parametrize("duration", [1140, 1200, 1259, 1320])
def test_only_expected_20_minute_time_window_accepts(duration):
    assert g1.require_expired_window(lifetime(duration)) == duration


@pytest.mark.parametrize("state,reason", [
    (lifetime(4), "g1_direct_proxy_did_not_exit_by_20m_window"),
    (lifetime(1360), "g1_direct_proxy_did_not_exit_by_20m_window"),
    (lifetime(1200,exit_code=137), "g1_direct_proxy_not_cleanly_expired"),
    (lifetime(1200,running=True), "g1_direct_proxy_not_cleanly_expired"),
    (lifetime(1200,oom=True), "g1_direct_proxy_not_cleanly_expired"),
])
def test_early_crash_active_oom_and_other_termination_do_not_restart(
    state, reason,
):
    with pytest.raises(g1.Stop, match=reason):
        g1.require_expired_window(state)


def preflight(*, fail=None) -> subprocess.CompletedProcess[str]:
    data = {
        "auth_file_readable": True,
        "codex_login_status_pass": True,
        "proxy_dns_pass": True,
        "github_connect_denied": True,
        "chatgpt_connect_allowed": True,
        "tls_verified": True,
        "failed_at": "NONE",
    }
    if fail:
        data[fail] = False
        data["failed_at"] = {
            "auth_file_readable": "AUTH_FILE",
            "codex_login_status_pass": "CODEX_LOGIN_STATUS",
            "proxy_dns_pass": "PROXY_DNS",
            "github_connect_denied": "GITHUB_DENY",
            "chatgpt_connect_allowed": "CHATGPT_CONNECT",
            "tls_verified": "TLS_HANDSHAKE",
        }[fail]
    return done(2 if fail else 0, json.dumps(data,sort_keys=True) + "\n")


@pytest.mark.parametrize("which", [
    None, "auth_file_readable", "codex_login_status_pass",
    "proxy_dns_pass", "github_connect_denied",
    "chatgpt_connect_allowed", "tls_verified",
])
def test_preflight_boolean_output_and_no_token_disclosure(which):
    response = preflight(fail=which)
    parsed = g1.parse_gate(response)
    assert parsed["pass"] is (which is None)
    if which is not None:
        assert parsed["failed_at"] in g1.ALLOWED_STAGES
    assert all(key not in parsed for key in ("token", "stderr", "stdout", "auth_json"))


def test_invalid_preflight_fails_closed():
    for raw in (
        "not-json\n",
        json.dumps({"error":"bearer=private"})+"\n",
        json.dumps({"auth_file_readable": "secret"})+"\n",
    ):
        with pytest.raises(g1.Stop, match="g1_direct_preflight_response_invalid"):
            g1.parse_gate(done(0,raw))


def test_python_probe_checks_stderr_and_stdout_and_live_tls():
    text = g1.PREFLIGHT
    assert 'status.stdout + "\\n" + status.stderr' in text
    assert '"logged in" in combined' in text
    assert '"chatgpt" in combined' in text
    assert "api.github.com:443" in text
    assert "HTTP/1.1 403" in text
    assert "chatgpt.com:443" in text
    assert "HTTP/1.1 200" in text
    assert "ssl.create_default_context().wrap_socket(" in text
    assert "GITHUB_DELIVERY_TOKEN" not in text
    assert "openai_api_key" not in text.lower()


def test_private_attempt_exclusive_and_prior_journals_unchanged(tmp_path, monkeypatch):
    root = tmp_path / ".pcp-g1-pilot"
    root.mkdir()
    old = root / "direct-t01-evidence.json"
    new = root / "direct-t01-build-continuation-evidence.json"
    for f, data in (
        (old,{"state":"started","lane":"direct","seed":g1.SEED,"attempts":0}),
        (new,{"state":"continuation_started","lane":"direct",
              "source_sha":g1.SEED,"model_calls":0}),
    ):
        f.write_text(json.dumps(data))
    monkeypatch.setattr(g1,"ROOT",root)
    marker = root / "direct-t01-expired-proxy-evidence.json"
    monkeypatch.setattr(g1,"EVIDENCE",marker)
    g1.persist({"state":"started","model_calls":0},first=True)
    with pytest.raises(FileExistsError):
        g1.persist({"state":"started","model_calls":0},first=True)
    g1.persist({"state":"preflight_stopped","model_calls":0,
                "failed_at":"CODEX_LOGIN_STATUS"},first=False)
    assert json.loads(marker.read_text())["model_calls"] == 0
    assert json.loads(old.read_text())["attempts"] == 0
    assert json.loads(new.read_text())["state"] == "continuation_started"


@pytest.mark.parametrize("fail_stage", [
    "codex_login_status_pass", "proxy_dns_pass",
    "github_connect_denied", "chatgpt_connect_allowed", "tls_verified",
])
def test_one_proxy_start_but_never_model_if_container_preflight_fails(
    monkeypatch, tmp_path, fail_stage,
):
    root = tmp_path / "root"
    root.mkdir()
    monkeypatch.setattr(g1,"ROOT",root)
    monkeypatch.setattr(g1,"EVIDENCE",root / "third-journal.json")
    monkeypatch.setattr(g1,"attest_existing",
                        lambda *a: ("0.162.1","a"*64,"1200.0"))
    prev = SimpleNamespace(
        MODEL="gpt-6-luna",EFFORT="medium",
        codex_argv=lambda: pytest.fail("MUST NOT launch Codex before preflight PASS"),
    )
    recovery = SimpleNamespace(
        prepared_env=lambda *_a: {"synthetic":"tokenless"},
    )
    monkeypatch.setattr(g1,"import_script",
                        lambda path, _name: (
                            prev if "first-turn" in path else recovery
                        ))
    calls=[]
    def fake_command(argv, **_):
        calls.append(tuple(argv))
        if argv[:3] == ["python3", str(g1.PCP / "scripts/g1-pilot-source-contract.py")][:3]:
            return done(0,'"PASS_G1_PILOT_SOURCE_PARKED"')
        if argv[:3] == ["docker","container","start"]:
            return done()
        pytest.fail(f"unexpected host command {argv[0]}")
    monkeypatch.setattr(g1,"command",fake_command)
    monkeypatch.setattr(g1,"inspect",lambda kind,name: {
        "Id":"a"*64,"State":{"Running":True},
        "NetworkSettings":{"Networks":{n:{} for n in g1.EXPECTED_NETS}},
        "Containers":{"p":{"Name":g1.PROXY_NAME}},
    })
    def fake_compose(_env,*args,**_kw):
        assert args[:6] == (
            "run","--rm","--no-deps","-T","--entrypoint","python3")
        return preflight(fail=fail_stage)
    recovery.compose=fake_compose
    with pytest.raises(g1.Stop,match="g1_direct_classified_container_preflight_failed"):
        g1.execute("b"*40)
    journal=json.loads(g1.EVIDENCE.read_text())
    assert journal["state"] == "preflight_stopped"
    assert journal["model_calls"] == 0
    assert journal["failed_at"] in g1.ALLOWED_STAGES
    assert [a[:3] for a in calls if a[0]=="docker"] == [
        ("docker","container","start")
    ]


def test_source_only_reuses_existing_proxy_and_does_not_create_job():
    s = SOURCE.read_text(encoding="utf-8")
    assert s.count('"docker", "container", "start", PROXY_NAME') == 1
    assert 'old.codex_argv()' in s
    assert s.count('old.codex_argv()') == 1
    assert "MAX_MODEL_SECONDS = 1080" in s
    for forbidden in (
        "docker compose down","docker system prune",
        "docker container run","docker network create",
        "shutil.rmtree(","git reset --hard",
        "ddev start","ddev stop","create_job(",
        "OPENAI_API_KEY","GITHUB_DELIVERY_TOKEN",
        "gh auth git-credential",
    ):
        assert forbidden not in s
