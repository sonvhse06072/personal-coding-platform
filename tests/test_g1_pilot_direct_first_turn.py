"""G1 direct one-model-turn contract. Synthetic; no Docker, GitHub or model."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
FILE = ROOT / "scripts/g1-pilot-direct-first-turn.py"
spec = importlib.util.spec_from_file_location("g1_direct_first_turn", FILE)
assert spec and spec.loader
g1 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(g1)


def test_direct_action_exact_model_effort_and_no_docker_capability():
    args = list(g1.codex_argv())
    assert args[:6] == [
        "run", "--rm", "--no-deps", "-T", "--entrypoint", "codex",
    ]
    assert args[6:10] == ["direct", "exec", "--json", "--sandbox"]
    assert args[10] == "workspace-write"
    assert args[args.index("--model") + 1] == "gpt-6-luna"
    assert 'model_reasoning_effort="medium"' in args
    assert 'approval_policy="never"' in args
    assert "sandbox_workspace_write.network_access=false" in args
    assert "features.memories=false" in args
    assert args[-1] == g1.TASK
    assert "intersectionMinutes" in g1.TASK
    assert "overnight" in g1.TASK
    assert "Only edit" in g1.TASK
    assert "Do not commit or push" in g1.TASK
    assert "gpt-6-astra" not in repr(args)
    assert "docker.sock" not in repr(args)
    assert not any("GITHUB_TOKEN" in v for v in args)


def test_container_preflight_checks_auth_and_live_tls_before_model():
    args = g1.direct_container_gate_argv()
    assert args[:7] == (
        "run", "--rm", "--no-deps", "-T", "--entrypoint",
        "python3", "direct",
    )
    probe = args[-1]
    assert "codex','login','status" in probe
    assert "api.github.com:443" in probe
    assert "response.startswith(b'HTTP/1.1 403')" in probe
    assert "chatgpt.com:443" in probe
    assert "ssl.create_default_context()" in probe
    assert "G1_DIRECT_CONTAINER_AUTH_AND_EGRESS=PASS" in probe


def test_direct_proxy_is_one_fixed_service_one_model_window():
    args = list(g1.proxy_argv())
    assert args[:3] == ["run", "-d", "--no-deps"]
    assert "--use-aliases" in args
    assert g1.PROXY_NAME in args and g1.PROXY_SERV in args
    assert "provider" in args[-1]
    assert "timeout=1200" in args[-1]
    assert "g1-pilot-github-proxy" not in repr(args)
    assert "docker" not in args[-1].lower()
    assert g1.LIMIT_SECONDS == 1200


def test_summarize_codex_usage_without_echoing_agent_stream():
    raw = "\n".join([
        json.dumps({"type": "item.completed", "item": {
            "type": "agent_message", "text": "sensitive source output",
        }}),
        json.dumps({"type": "turn.completed", "usage": {
            "input_tokens": 310, "cached_input_tokens": 40,
            "output_tokens": 90, "other": "private bearer",
        }}),
    ])
    result = g1.summarise_codex(SimpleNamespace(returncode=0, stdout=raw))
    assert result == {
        "returncode": 0, "terminal": "turn.completed",
        "usage": {
            "input_tokens": 310, "cached_input_tokens": 40,
            "output_tokens": 90,
        },
    }
    assert "sensitive" not in repr(result)
    assert "bearer" not in repr(result)
    assert g1.summarise_codex(SimpleNamespace(
        returncode=1,
        stdout=json.dumps({"type": "turn.failed", "error": "Authorization 401"}),
    )) == {"returncode": 1, "terminal": "turn.failed", "usage": {}}


def test_only_two_allowed_fixture_paths_are_in_scope(tmp_path, monkeypatch):
    monkeypatch.setattr(g1, "WS", tmp_path / "direct")
    head = g1.SEED
    commands = []
    def fake_read(args, **kw):
        commands.append(tuple(args))
        if args[-2:] == ["branch", "--show-current"]:
            return g1.BRANCH
        if args[-2:] == ["rev-parse", "HEAD"]:
            return head
        if args[-2:] == ["diff", "--name-only"]:
            return "\n".join(sorted(g1.ALLOW))
        if args[-3:] == ["--others", "--exclude-standard"]:
            return ""
        return ""
    monkeypatch.setattr(g1, "read", fake_read)
    ok, files = g1.code_scope()
    assert ok is True and set(files).issubset(g1.ALLOW)
    monkeypatch.setattr(g1, "read", lambda args, **kw: (
        "UNTRACKED_OUT_OF_SCOPE.env" if args[-2:] == ["diff", "--name-only"]
        else fake_read(args, **kw)
    ))
    ok, files = g1.code_scope()
    assert ok is False
    assert "UNTRACKED_OUT_OF_SCOPE.env" in files
    monkeypatch.setattr(g1, "read", lambda args, **kw: (
        ".env" if "--ignored" in args else fake_read(args, **kw)
    ))
    ignored_ok, ignored_files = g1.code_scope()
    assert ignored_ok is False and ".env" in ignored_files
    monkeypatch.setattr(g1, "read", lambda args, **kw: (
        "composer.json" if "--cached" in args else fake_read(args, **kw)
    ))
    staged_ok, staged_files = g1.code_scope()
    assert staged_ok is False and "composer.json" in staged_files


def test_attempt_record_written_exclusively_and_cannot_retry(tmp_path, monkeypatch):
    root = tmp_path / "new-pilot"
    root.mkdir()
    monkeypatch.setattr(g1, "ROOT", root)
    monkeypatch.setattr(g1, "EVIDENCE", root / "direct-t01-evidence.json")
    starting = {"lane": "direct", "state": "started", "attempts": 0}
    g1.save(starting, initial=True)
    with pytest.raises(FileExistsError):
        g1.save(starting, initial=True)
    g1.save({"lane": "direct", "state": "completed", "model_calls": 1},
            initial=False)
    assert json.loads(g1.EVIDENCE.read_text()) == {
        "lane": "direct", "state": "completed", "model_calls": 1,
    }


def test_do_not_create_a_new_pcp_job_or_touch_existing_smoke():
    src = FILE.read_text(encoding="utf-8")
    for prohibited in (
        "docker compose down", "docker system prune",
        "ddev stop", "ddev start", "create_job(",
        "git reset --hard", "shutil.rmtree(", "os.system(",
        "pcp-g1-smoke-postgres", "ddev-pcp-g1-codex-smoke",
        "GITHUB_DELIVERY_TOKEN", "OPENAI_API_KEY", "gh auth",
        "PCP_G1_PILOT_IDENTITY_ENABLED", "PCP_TRUSTED_CODEX_BROKER_ENABLED",
    ):
        assert prohibited not in src
    assert "no_automatic_retry" in src
    assert "model_calls" in src
    assert "old_smoke_job_unchanged" in src


def test_one_direct_turn_uses_only_private_auth_and_a_disabled_placeholder(
    tmp_path, monkeypatch,
):
    root = tmp_path / ".pcp-g1-pilot"
    root.mkdir()
    (root / "auth" / "pcp").mkdir(parents=True)
    (root / "auth" / "direct").mkdir()
    monkeypatch.setattr(g1, "ROOT", root)
    monkeypatch.setattr(g1, "WS", root / "direct-workspace")
    monkeypatch.setattr(g1, "PCP", tmp_path / "pcp")
    monkeypatch.setattr(g1.os, "geteuid", lambda: 1000)
    monkeypatch.setattr(g1.os, "getegid", lambda: 1000)
    monkeypatch.setattr(g1.Path, "stat", lambda *a, **kw: SimpleNamespace(st_gid=998))
    env = g1.compose_env("0.162.1")
    assert env["PCP_G1_PILOT_PCP_CODEX_AUTH_DIR"] == str(root / "auth" / "pcp")
    assert env["PCP_G1_PILOT_DIRECT_CODEX_AUTH_DIR"] == str(root / "auth" / "direct")
    assert env["PCP_G1_PILOT_RUNTIME_IMAGE"] == g1.APP_IMAGE
    assert (root / "inactive" / "github-disabled").read_text().strip() == (
        "DISABLED_FOR_DIRECT_CONTROL_ONLY"
    )
    assert env["PCP_G1_PILOT_GITHUB_TOKEN_FILE"] == str(
        root / "inactive" / "github-disabled")
