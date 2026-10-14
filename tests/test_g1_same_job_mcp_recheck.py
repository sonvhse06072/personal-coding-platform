"""G1 one-use corrected MCP proof; synthetic tests only, no Docker or Codex."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
FILE = ROOT / "scripts/g1-same-job-mcp-recheck.py"
spec = importlib.util.spec_from_file_location("g1_one_mcp_recheck", FILE)
assert spec and spec.loader
g1 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(g1)
JOB = "2c6db0aa6f19" + "a" * 20


def rpc(*, rc=0, passed=True, marker=True, calls=1) -> str:
    body = {
        "job_id": JOB, "project_id": g1.PROJECT, "phase": "frontend_quality",
        "passed": passed, "tool_calls_used": calls, "tool_calls_max": 8,
        "commands": [{
            "command": "npm", "returncode": rc, "timed_out": False,
            "stdout": g1.MARKER if marker else "not present", "stderr": "",
        }],
    }
    replies = [
        {"jsonrpc": "2.0", "id": 1, "result": {
            "serverInfo": {"name": "pcp-fixture-dev"},
        }},
        {"jsonrpc": "2.0", "id": 2, "result": {
            "tools": [{"name": "pcp_run_project_checks"}],
        }},
        {"jsonrpc": "2.0", "id": 3, "result": {
            "isError": not passed,
            "content": [{"type": "text", "text": json.dumps(body)}],
        }},
    ]
    return "\n".join(json.dumps(v, separators=(",", ":")) for v in replies)


def test_only_one_corrected_mcp_phase_is_sent():
    items = [json.loads(line) for line in g1.rpc_request().splitlines()]
    assert len(items) == 4
    assert len([x for x in items if x["method"] == "tools/call"]) == 1
    assert items[-1]["params"] == {
        "name": "pcp_run_project_checks",
        "arguments": {"phase": "frontend_quality"},
    }


def test_exact_http_phase_must_pass_and_match_output():
    p = g1.parse_phase(rpc(), JOB)
    assert p["accepted"] is True
    assert p["returncode"] == 0 and p["output_marker"] is True
    assert p["phase_http_200"] is True and p["tool_calls_used"] == 1
    assert p["model_calls"] == 0
    for options in (
        {"rc": 254, "passed": False, "marker": False},
        {"rc": 0, "passed": True, "marker": False},
        {"rc": 0, "passed": True, "marker": True, "calls": 2},
    ):
        assert g1.parse_phase(rpc(**options), JOB)["accepted"] is False
    with pytest.raises(g1.Stop, match="g1_mcp_phase_response_invalid"):
        g1.parse_phase(rpc(), "f" * 32)


def test_no_secrets_in_single_use_private_journal(tmp_path, monkeypatch):
    root = tmp_path / ".pcp-g1-smoke"
    root.mkdir()
    monkeypatch.setattr(g1, "ROOT", root)
    monkeypatch.setattr(g1, "ATTEMPT", root / "mcp-corrected-recheck-evidence.json")
    data = {"job_id": JOB, "model_calls": 0, "state": "started"}
    g1.save(data, first=True)
    with pytest.raises(FileExistsError):
        g1.save(data, first=True)
    assert json.loads(g1.ATTEMPT.read_text()) == data
    g1.save({**data, "state": "completed", "accepted": True}, first=False)
    assert json.loads(g1.ATTEMPT.read_text())["state"] == "completed"
    assert not (root / "mcp-corrected-recheck-evidence.tmp").exists()


def test_db_web_and_executor_identity_stop_on_drift_before_mcp(monkeypatch):
    ws = Path("/home/test/.pcp-g1-smoke/workspaces") / JOB
    old = {"Image": "sha256:old"}
    oldid, dbid = "old-exec", "old-db"
    database_sha = "d" * 64
    web_sha = "w" * 64
    fixture_db_sha = "b" * 64
    new_env = {
        "PCP_TRUSTED_CODEX_BROKER_ENABLED": "owner-approved",
        "PCP_TRUSTED_CODEX_DEV_TOKEN": "new-rotated-dev-token",
        "PCP_TRUSTED_CODEX_JOB_ID": JOB,
        "PCP_TRUSTED_CODEX_SOURCE_SHA": g1.PINNED_SOURCE,
        "PCP_TRUSTED_CODEX_DEADLINE_EPOCH": "1800000000",
    }
    previous = SimpleNamespace(
        attest_g1=lambda _ws: None,
        docker_identity=lambda _ws: "new-exec",
    )
    def fake_inspect(kind, key):
        assert kind == "container"
        if key == "new-exec":
            return {
                "Image": old["Image"], "State": {"Running": True},
                "NetworkSettings": {"Networks": {g1.CONTROL: {}}},
                "Config": {"Env": [f"{k}={v}" for k,v in new_env.items()]},
            }
        return {"Id": {
            dbid: database_sha,
            "ddev-pcp-g1-codex-smoke-web": "unapproved-new-web",
            "ddev-pcp-g1-codex-smoke-db": fixture_db_sha,
        }[key]}

    called = []
    monkeypatch.setattr(g1, "identity", lambda *_:
        (previous, JOB, ws, oldid, dbid, database_sha,
         web_sha, fixture_db_sha, "local-db-password", old))
    monkeypatch.setattr(g1, "configure", lambda *_: {
        "PCP_G1_DEV_TOKEN": "new-rotated-dev-token",
        "PCP_G1_DEADLINE": "1800000000",
    })
    monkeypatch.setattr(g1, "service_id", lambda _name: "new-exec")
    monkeypatch.setattr(g1, "inspect", fake_inspect)
    monkeypatch.setattr(g1, "save", lambda *a, **k: called.append("journal"))
    monkeypatch.setattr(g1, "compose", lambda *_args, **_kw: called.append("executor-recreate"))
    monkeypatch.setattr(g1, "run", lambda *_args, **_kw:
        pytest.fail("MCP must not be executed after foreign container drift"))
    with pytest.raises(g1.Stop, match="g1_other_containers_changed"):
        g1.execute("f" * 40)
    assert called == ["journal", "executor-recreate"]


def test_one_use_smoke_calls_only_executor_up_and_one_mcp(monkeypatch):
    ws = Path("/home/test/.pcp-g1-smoke/workspaces") / JOB
    dbid = "db-id"
    ids = {"db": "d" * 64, "web": "a" * 64, "fixture_db": "b" * 64}
    old = {"Image": "sha256:build"}
    env = {
        "PCP_G1_DEV_TOKEN": "rotated-token",
        "PCP_G1_DEADLINE": "1800000000",
    }
    previous = SimpleNamespace(
        attest_g1=lambda _ws: None,
        docker_identity=lambda _ws: "new-exec",
    )
    monkeypatch.setattr(g1, "identity", lambda *_:
        (previous, JOB, ws, "old-exec", dbid, ids["db"], ids["web"],
         ids["fixture_db"], "db-password", old))
    monkeypatch.setattr(g1, "configure", lambda *_: env)
    monkeypatch.setattr(g1, "service_id", lambda name: "new-exec")
    def inspect(kind, target):
        if target == "new-exec":
            return {
                "Image": old["Image"], "State": {"Running": True},
                "NetworkSettings": {"Networks": {g1.CONTROL: {}}},
                "Config": {"Env": [
                    "PCP_TRUSTED_CODEX_BROKER_ENABLED=owner-approved",
                    f"PCP_TRUSTED_CODEX_DEV_TOKEN={env['PCP_G1_DEV_TOKEN']}",
                    f"PCP_TRUSTED_CODEX_JOB_ID={JOB}",
                    f"PCP_TRUSTED_CODEX_SOURCE_SHA={g1.PINNED_SOURCE}",
                    f"PCP_TRUSTED_CODEX_DEADLINE_EPOCH={env['PCP_G1_DEADLINE']}",
                ]},
            }
        return {"Id": {
            dbid: ids["db"],
            "ddev-pcp-g1-codex-smoke-web": ids["web"],
            "ddev-pcp-g1-codex-smoke-db": ids["fixture_db"],
        }[target]}
    monkeypatch.setattr(g1, "inspect", inspect)
    history = []
    monkeypatch.setattr(g1, "save", lambda *a, **kw:
                        history.append(("save", kw.get("first"))))
    def fake_compose(_env, *args, **kwargs):
        history.append(("compose", args))
        return rpc() if args[0] == "run" else ""
    monkeypatch.setattr(g1, "compose", fake_compose)
    monkeypatch.setattr(g1, "run", lambda *a, **kw: "")
    monkeypatch.setattr(g1, "service_id", lambda _n: "new-exec")
    result = g1.execute("f" * 40)
    assert result["status"] == "PASS_G1_CORRECTED_MCP_HTTP_EXECUTOR_NO_MODEL"
    assert result["model_calls"] == 0 and result["ready_for_autonomous_e2e"] is False
    assert history[1] == ("compose", (
        "up", "-d", "--no-deps", "--no-build", "--force-recreate",
        "pcp-dev-executor",
    ))
    assert [x for x in history if x[0] == "compose" and x[1][0] == "run"] == [
        ("compose", ("run", "--rm", "--no-deps", "-T", "runtime",
                     "python3", "/app/app/trusted_codex_mcp.py"))
    ]
    assert history[0] == ("save", True) and history[-1] == ("save", False)


def test_must_not_modify_f2_or_start_ddev_or_invoke_codex():
    text = FILE.read_text(encoding="utf-8")
    for forbidden in (
        "ddev start", "ddev stop", "docker system prune", "git reset --hard",
        "create_job(", "codex exec", "PCP_F2_GIT_ONLY_ENABLED",
    ):
        assert forbidden not in text
