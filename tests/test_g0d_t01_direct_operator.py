"""Offline G0D-T01 Direct-arm one-attempt security and parity regression.

No real Docker, model, WSL/G0 credential, GitHub, DDEV or Chợ Nhạc access.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/g0d-t01-direct-operator.py"
SPEC = importlib.util.spec_from_file_location("g0d_t01_direct_op", SCRIPT)
op = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(op)
SHA = "a" * 40


@pytest.fixture
def local(monkeypatch, tmp_path):
    private = tmp_path / ".pcp-g0d01"
    workspace = private / "arms/direct/workspace"
    workspace.mkdir(parents=True, mode=0o700)
    for folder in (private, private / "arms", private / "arms/direct"):
        folder.chmod(0o700)
    workspace.chmod(0o700)
    monkeypatch.setattr(op.Path, "home", lambda: tmp_path)
    monkeypatch.setattr(op, "_identity", lambda *args: None)
    monkeypatch.setattr(op.g0, "require_headroom", lambda *a: None)
    monkeypatch.setattr(op, "_assert_frozen_workspace", lambda *a: None)
    return SimpleNamespace(
        root=private, workspace=workspace, repo=tmp_path, fixture=tmp_path,
    )


def test_same_literal_frozen_g0_task_prompt_as_pcp():
    prompt = op._fixed_prompt()
    assert "Implement G0D-T01" in prompt
    assert "Do not push, open a pull request" in prompt
    assert "nonbreaking spaces (NBSP U+00A0)" in prompt
    assert "Unit/Kernel" in prompt
    assert op.MODEL == "gpt-6-luna"
    assert op.EFFORT == "medium"
    assert op.CLI_VERSION == "0.160.0"


def test_one_direct_prepare_claims_before_private_clone(local, monkeypatch):
    calls = []

    def fake_git(repo, *args, **kwargs):
        calls.append((repo, args))
        return ""

    monkeypatch.setattr(op, "_git", fake_git)
    report = op.prepare(local.repo, local.fixture, SHA)
    assert report["status"] == "PASS"
    assert report["phase"] == "g0d_t01_direct_prepared"
    assert report["codex_cli_invocations_attempted"] == 0
    assert report["github_delivery_enabled"] is False
    assert calls[0][1][:4] == ("clone", "--no-local", "--no-checkout", "--branch")
    assert calls[0][1][4] == "benchmark/pcp"
    assert calls[1][1] == ("remote", "remove", "origin")
    assert calls[2][1] == ("checkout", "-b", op.BRANCH, op.SEED)
    journal = local.root / op.JOURNAL_NAME
    assert journal.stat().st_mode & 0o077 == 0
    data = json.loads(journal.read_text())
    assert data["state"] == "prepared"
    assert data["execute_attempted"] is False
    with pytest.raises(op.g0.GateError, match="already_claimed"):
        op.prepare(local.repo, local.fixture, SHA)
    assert len(calls) == 3


def test_source_clone_failure_preserves_durable_attempt_no_retry(local, monkeypatch):
    monkeypatch.setattr(
        op, "_git", lambda *a, **k: (_ for _ in ()).throw(
            op.g0.GateError("g0_direct_scoped_git_failed")
        ),
    )
    with pytest.raises(op.g0.GateError, match="scoped_git_failed"):
        op.prepare(local.repo, local.fixture, SHA)
    data = json.loads((local.root / op.JOURNAL_NAME).read_text())
    assert data["state"] == "prepare_claimed"
    assert data["execute_attempted"] is False
    with pytest.raises(op.g0.GateError, match="already_claimed"):
        op.prepare(local.repo, local.fixture, SHA)


def _prepared(local, *, state="prepared", attempted=False):
    journal = local.root / op.JOURNAL_NAME
    journal.write_text(json.dumps({
        "arm": "direct", "task_id": "G0D-T01",
        "state": state, "source_sha": SHA,
        "seed": op.SEED, "branch": op.BRANCH,
        "model": op.MODEL, "reasoning_effort": op.EFFORT,
        "codex_cli_version": op.CLI_VERSION,
        "execute_attempted": attempted,
    }), encoding="utf-8")
    journal.chmod(0o600)
    return journal


def test_one_execute_records_claim_before_one_model_call(local, monkeypatch):
    journal = _prepared(local)
    calls = []

    def once(repo, fixture):
        state = json.loads(journal.read_text())
        assert state["state"] == "execute_claimed"
        assert state["execute_attempted"] is True
        calls.append("direct")
        return {"terminal_verified": True, "elapsed_seconds": 9.0,
                "usage": {"input_tokens": 100, "output_tokens": 50}}

    monkeypatch.setattr(op, "_direct_one_call", once)
    monkeypatch.setattr(op, "_commit_scope", lambda *a: "f"*40)
    out = op.execute(local.repo, local.fixture, SHA)
    assert out["status"] == "PASS"
    assert out["codex_cli_invocations_attempted"] == 1
    assert out["model_api_calls_observed"] is None
    assert out["commit"] == "f"*40
    assert out["github_delivery_enabled"] is False
    assert json.loads(journal.read_text())["state"] == "executed"
    with pytest.raises(op.g0.GateError, match="already_used"):
        op.execute(local.repo, local.fixture, SHA)
    assert calls == ["direct"]


def test_timeout_is_terminal_attempt_even_if_model_possibly_completed(local, monkeypatch):
    journal = _prepared(local)
    called = []

    def timeout(*args):
        called.append("direct")
        raise op.g0.GateError("g0_direct_coding_wrapper_timeout_no_retry")

    monkeypatch.setattr(op, "_direct_one_call", timeout)
    with pytest.raises(op.g0.GateError, match="no_retry"):
        op.execute(local.repo, local.fixture, SHA)
    assert json.loads(journal.read_text())["state"] == "execute_claimed"
    assert json.loads(journal.read_text())["execute_attempted"] is True
    with pytest.raises(op.g0.GateError, match="already_used"):
        op.execute(local.repo, local.fixture, SHA)
    assert called == ["direct"]


def test_prepared_workspace_must_be_empty_before_claim(local, monkeypatch):
    (local.workspace / "unrelated.txt").write_text("existing")
    monkeypatch.setattr(
        op, "_git", lambda *a, **k: (_ for _ in ()).throw(
            AssertionError("occupied workspace cannot be cloned into")
        ),
    )
    with pytest.raises(op.g0.GateError, match="occupied"):
        op.prepare(local.repo, local.fixture, SHA)
    assert not (local.root / op.JOURNAL_NAME).exists()


def test_readonly_status_does_not_touch_model_or_mutate_journal(local, monkeypatch):
    journal = _prepared(local)
    saved = journal.read_bytes()
    monkeypatch.setattr(op.g0, "require_local_docker_context", lambda: None)
    monkeypatch.setattr(op.g0, "require_exact_repo", lambda *a: None)
    monkeypatch.setattr(
        op, "_direct_one_call", lambda *a: (_ for _ in ()).throw(
            AssertionError("read-only status must never invoke Codex")
        ),
    )
    status = op.status(local.repo, local.fixture, SHA)
    assert status["status"] == "PASS"
    assert status["execute_attempted"] is False
    assert status["model_calls_this_command"] == 0
    assert status["retry_authorized"] is False
    assert journal.read_bytes() == saved


def test_direct_invocation_pins_image_cli_model_reasoning_and_sandbox(monkeypatch):
    invoked = []
    monkeypatch.setattr(op.auth, "_compose", lambda *a: [
        "docker", "compose", "-p", op.g0.PROJECT,
    ])
    monkeypatch.setattr(op, "_compose_env", lambda *a: {"PATH": "/bin"})
    monkeypatch.setattr(op, "_fixed_prompt", lambda: "synthetic frozen G0 task")
    def fake_run(argv, **kwargs):
        invoked.append((argv, kwargs))
        return SimpleNamespace(
            returncode=0, stdout="\n".join([
                json.dumps({"type": "item.completed",
                            "item": {"type": "agent_message", "text": "done"}}),
                json.dumps({"type": "turn.completed", "usage": {
                    "input_tokens": 12, "cached_input_tokens": 3,
                    "output_tokens": 7,
                }}),
            ]), stderr="not-exposed",
        )
    monkeypatch.setattr(op.subprocess, "run", fake_run)
    result = op._direct_one_call(ROOT, ROOT)
    assert result["terminal_verified"] is True
    assert result["usage"]["output_tokens"] == 7
    assert len(invoked) == 1
    args, kwargs = invoked[0]
    assert "direct" in args
    assert args[args.index("--name") + 1] == op.DIRECT_CONTAINER
    assert "--no-deps" in args and "--rm" in args and "-T" in args
    assert args[args.index("--model") + 1] == op.MODEL
    assert 'model_reasoning_effort="medium"' in args
    assert "sandbox_workspace_write.network_access=false" in args
    assert "features.memories=false" in args
    assert args[-1] == "synthetic frozen G0 task"
    assert "GITHUB_DELIVERY_TOKEN" not in json.dumps(kwargs)
    assert kwargs["timeout"] == op.TIMEOUT_SECONDS


@pytest.mark.parametrize("stdout,code", [
    (json.dumps({"type": "turn.failed"}), 0),
    (json.dumps({"type": "turn.completed"}) + "\n"
     + json.dumps({"type": "error", "message": "bad"}), 0),
    ("", 0),
    (json.dumps({"type": "turn.completed"}), 7),
])
def test_no_false_success_for_incomplete_or_failed_codex(monkeypatch, stdout, code):
    monkeypatch.setattr(op.auth, "_compose", lambda *a: ["docker"])
    monkeypatch.setattr(op, "_compose_env", lambda *a: {})
    monkeypatch.setattr(op, "_fixed_prompt", lambda: "synthetic")
    monkeypatch.setattr(op.subprocess, "run", lambda *a, **kw:
                        SimpleNamespace(returncode=code, stdout=stdout, stderr=""))
    with pytest.raises(op.g0.GateError, match="failed|unverified"):
        op._direct_one_call(ROOT, ROOT)


def test_diff_scope_rejects_unrelated_php_or_untracked_content(monkeypatch, local):
    def fake_git(repo, *args, **kwargs):
        if args == ("remote",): return ""
        if args == ("branch", "--show-current"): return op.BRANCH
        if args == ("ls-files", "--others", "--exclude-standard"): return ""
        if args == ("diff", "--name-only", op.SEED):
            return "\n".join([op.ALLOWED_FILES[0], "composer.json"])
        raise AssertionError(f"unexpected scoped git command: {args}")
    monkeypatch.setattr(op, "_git", fake_git)
    with pytest.raises(op.g0.GateError, match="diff_not_three_frozen_files"):
        op._commit_scope(local.workspace)


def test_commit_only_three_exact_files_with_sanitized_git(local, monkeypatch):
    calls=[]
    def fake_git(repo, *args, **kwargs):
        calls.append(args)
        if args == ("remote",): return ""
        if args == ("branch", "--show-current"): return op.BRANCH
        if args == ("ls-files", "--others", "--exclude-standard"): return ""
        if args == ("diff", "--name-only", op.SEED):
            return "\n".join(op.ALLOWED_FILES)
        if args == ("diff", "--cached", "--name-only"):
            return "\n".join(op.ALLOWED_FILES)
        if args == ("status", "--porcelain=v1"): return ""
        if args == ("rev-parse", "HEAD"): return "f"*40
        return ""
    monkeypatch.setattr(op, "_git", fake_git)
    result=op._commit_scope(local.workspace)
    assert result == "f"*40
    assert ("add", "--", *op.ALLOWED_FILES) in calls
    assert ("merge-base", "--is-ancestor", op.SEED, "f"*40) in calls
    assert any("commit" in a for a in calls)
    assert all("push" not in a for a in calls)


def test_g0_direct_negative_provider_network_scope_blocks_prepare(monkeypatch):
    monkeypatch.setattr(op.g0, "require_local_docker_context", lambda: None)
    monkeypatch.setattr(op.g0, "require_exact_repo", lambda *a: None)
    monkeypatch.setattr(op.auth, "_validate_overlay", lambda: None)
    monkeypatch.setattr(op.live, "_activated_state", lambda: None)
    monkeypatch.setattr(op.live, "_docker_boundary", lambda *a: None)
    monkeypatch.setattr(op, "_verify_pcp_completed", lambda: None)
    monkeypatch.setattr(op.auth, "_check_config", lambda *a: True)
    monkeypatch.setattr(op.g0, "exists", lambda *a: False)
    monkeypatch.setattr(op.g0, "inspect", lambda kind, name:
                        {"Internal": False,
                         "Labels": {"com.docker.compose.project": "foreign"},
                         "Containers": {}})
    with pytest.raises(op.g0.GateError, match="network_ownership_or_busy"):
        op._identity(ROOT, ROOT, SHA)


def test_pcp_provenance_enforced_without_dispatch(monkeypatch):
    record = {
        "phase": "pcp", "state": "executed", "source_sha": op.ORIGINAL_PCP_SOURCE,
        "job_id": op.PCP_JOB, "commit": op.PCP_COMMIT,
        "execute_attempted": True,
    }
    monkeypatch.setattr(op.pcp, "_existing", lambda: record)
    monkeypatch.setattr(op.pcp, "_http", lambda *a: {
        "job_status": "waiting_human",
        "result": {"commit": op.PCP_COMMIT},
    })
    monkeypatch.setattr(op.pcp, "_valid_job", lambda *a, **k: op.PCP_JOB)
    op._verify_pcp_completed()
    record["commit"] = "9"*40
    with pytest.raises(op.g0.GateError, match="pcp_original_trial_not_completed"):
        op._verify_pcp_completed()


def test_real_cli_help_without_provider_or_docker():
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--help"],
        cwd=ROOT, capture_output=True, text=True, check=False, timeout=15,
    )
    assert result.returncode == 0, result.stderr
    assert "prepare" in result.stdout
    assert "execute" in result.stdout
    assert "--expected-sha" in result.stdout


def test_source_never_runs_host_codex_ddev_chonhac_or_github_delivery():
    content = SCRIPT.read_text(encoding="utf-8")
    for forbidden in (
        "docker system prune", "docker stop", "docker restart",
        "ddev start", "gh pr create", "git push",
        "GITHUB_DELIVERY_TOKEN=", "/home/sonvh/chonhac",
        "CodexAdapter(", "docker exec pcp",
    ):
        assert forbidden not in content
    assert "O_EXCL" in content
    assert "execute_attempted" in content
    assert "original" not in content or "ORIGINAL_PCP_SOURCE" in content
