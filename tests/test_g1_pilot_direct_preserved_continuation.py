"""G1 one-use DIRECT recovery tests; synthetic, no Docker/network/model."""
from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
from types import SimpleNamespace
import subprocess

import pytest

REPO = Path(__file__).resolve().parents[1]
SOURCE = REPO / "scripts/g1-pilot-direct-preserved-continuation.py"
spec = importlib.util.spec_from_file_location("g1_direct_preserved", SOURCE)
assert spec is not None and spec.loader is not None
g1 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(g1)

JOB_SEED = g1.SEED


def done(returncode=0, stdout="", stderr=""):
    return subprocess.CompletedProcess([], returncode, stdout, stderr)


def test_composes_only_three_reviewed_parked_files_and_direct_image(
    monkeypatch,
):
    argv = []
    def fake_run(args, **kwargs):
        argv.append(args)
        return done()
    monkeypatch.setattr(g1, "run", fake_run)
    env = {"PCP_G1_PILOT_RUNTIME_IMAGE": g1.DIRECT_IMAGE}
    g1.compose(env, "config", "--quiet")
    g1.compose(env, "build", "direct")
    assert len(argv) == 2
    assert argv[0][-2:] == ["config", "--quiet"]
    assert argv[1][-2:] == ["build", "direct"]
    assert argv[0][:4] == [
        "docker", "compose", "--project-name", "pcp-g1-pilot",
    ]
    assert argv[0].count("--file") == 3
    for name in g1.COMPOSE_FILES:
        assert str(g1.PCP / name) in argv[0]
    assert g1.DIRECT_IMAGE == "pcp-g1-pilot-direct-codex"
    assert "pcp-g1-pilot-runtime" not in g1.DIRECT_IMAGE
    assert "up" not in argv[1]
    assert "runtime" not in argv[1]


def test_build_failure_classification_never_returns_raw_output():
    p = done(11, "", "npm ERR! no matching version; secret=forbidden")
    assert g1.failure_kind(p) == "CODEX_NPM_PACKAGE_OR_REGISTRY"
    p = done(11, "", "apt-get failed to fetch host")
    assert g1.failure_kind(p) == "BASE_IMAGE_OR_APT_CONNECTIVITY"
    p = done(11, "", "unauthorized: image registry")
    assert g1.failure_kind(p) == "IMAGE_REGISTRY_OR_PERMISSION"
    p = done(11, "", "a totally unknown error TOKEN=abc")
    assert g1.failure_kind(p) == "UNCLASSIFIED_BUILD_OR_COMPOSE_FAILURE"


def test_exclusive_attempt_marker_preserves_prior_evidence(
    tmp_path, monkeypatch,
):
    root = tmp_path / "new-root"
    root.mkdir()
    before = root / "direct-t01-evidence.json"
    before.write_text(json.dumps({
        "state": "started", "lane": "direct", "seed": JOB_SEED,
        "model": "gpt-6-luna", "effort": "medium", "attempts": 0,
    }))
    monkeypatch.setattr(g1, "ROOT", root)
    monkeypatch.setattr(g1, "PREVIOUS", before)
    monkeypatch.setattr(g1, "NEW", root / "direct-t01-build-continuation-evidence.json")
    g1.record({"state": "continuation_started", "model_calls": 0}, initial=True)
    with pytest.raises(FileExistsError):
        g1.record({"state": "other"}, initial=True)
    assert g1.model_already_launched() is False
    g1.record({"state": "stopped_before_model", "model_calls": 0}, initial=False)
    assert g1.model_already_launched() is False
    g1.record({"state": "model_launched", "model_calls": 1}, initial=False)
    assert g1.model_already_launched() is True
    assert json.loads(before.read_text()) == {
        "state": "started", "lane": "direct", "seed": JOB_SEED,
        "model": "gpt-6-luna", "effort": "medium", "attempts": 0,
    }


def test_pre_model_build_stop_never_launches_proxy_codex(
    monkeypatch, tmp_path,
):
    monkeypatch.setattr(g1, "assert_original", lambda *a: ("0.162.1", tmp_path))
    old = SimpleNamespace(
        MODEL="gpt-6-luna", EFFORT="medium",
        proxy_argv=lambda: pytest.fail("must not launch proxy on build STOP"),
        codex_argv=lambda: pytest.fail("must not launch Codex on build STOP"),
    )
    monkeypatch.setattr(g1, "previous_operator", lambda: old)
    monkeypatch.setattr(g1, "prepared_env", lambda *a: {"some": "synthetic"})
    stages = []
    def fake_compose(_env, *args, **kwargs):
        stages.append(args)
        if args == ("config", "--quiet"):
            return done()
        if args == ("build", "direct"):
            return done(254, "", "npm ERR! ETARGET Version not found")
        pytest.fail("Unexpected Docker/action after failed build")
    monkeypatch.setattr(g1, "compose", fake_compose)
    journal = []
    monkeypatch.setattr(g1, "record", lambda value, **_kw: journal.append(value))
    with pytest.raises(g1.Stop, match="g1_direct_lean_image_build_failed"):
        g1.execute("a" * 40)
    assert stages == [("config", "--quiet"), ("build", "direct")]
    assert journal[0]["model_calls"] == 0
    assert journal[-1] == {
        "state": "stopped_before_model", "phase": "build_direct_image",
        "lane": "direct", "source_sha": JOB_SEED, "model_calls": 0,
        "returncode": 254,
        "build_error_class": "CODEX_NPM_PACKAGE_OR_REGISTRY",
    }


def test_wrong_original_journal_does_not_run_any_docker_build(
    tmp_path, monkeypatch,
):
    root = tmp_path / ".pcp-g1-pilot"
    root.mkdir()
    ws = root / "direct-workspace"
    ws.mkdir()
    src = tmp_path / "old-smoke-source"
    src.mkdir()
    (root / "auth" / "pcp").mkdir(parents=True)
    (root / "auth" / "direct").mkdir()
    for lane in ("pcp", "direct"):
        a = root / "auth" / lane / "auth.json"
        a.write_text("fake-test-token")
        a.chmod(0o600)
    inactive = root / "inactive"
    inactive.mkdir()
    (inactive / "github-disabled").write_text(g1.DISABLED_GITHUB)
    (inactive / "github-disabled").chmod(0o600)
    old = SimpleNamespace(MODEL="gpt-6-luna", EFFORT="medium",
                          BRANCH="ai/g1-direct-t01-20261015", APP_IMAGE="old")
    journal = root / "direct-t01-evidence.json"
    journal.write_text(json.dumps({
        "state": "model_launched", "lane": "direct",
        "seed": JOB_SEED, "model": old.MODEL,
        "effort": old.EFFORT, "attempts": 1,
    }))
    monkeypatch.setattr(g1, "ROOT", root)
    monkeypatch.setattr(g1, "DIRECT", ws)
    monkeypatch.setattr(g1, "SMOKE_SOURCE", src)
    monkeypatch.setattr(g1, "PREVIOUS", journal)
    monkeypatch.setattr(g1, "NEW", root / "direct-t01-build-continuation-evidence.json")
    monkeypatch.setattr(g1.os, "geteuid", lambda: root.stat().st_uid or 1000)
    monkeypatch.setattr(g1, "PCP", tmp_path / "pcp")
    monkeypatch.setattr(g1, "read", lambda args, **_kw:
                        "main" if args[-2:] == ["branch", "--show-current"]
                        else "a" * 40)
    monkeypatch.setattr(g1, "run", lambda *a, **kw:
                        pytest.fail("no model/Docker/Compose after used journal"))
    with pytest.raises(g1.Stop, match="not_exact_pre_model_stop"):
        g1.assert_original("a" * 40, old)


def test_no_restart_old_smoke_no_delete_and_single_model_turn_contract():
    text = SOURCE.read_text(encoding="utf-8")
    for bad in (
        "docker system prune", "docker compose down",
        "shutil.rmtree(", "git reset --hard", "ddev start",
        "ddev stop", "create_job(", "CODEX_AUTH=", "Bearer ",
        "OPENAI_API_KEY", "GITHUB_DELIVERY_TOKEN",
    ):
        assert bad not in text
    assert text.count('old.codex_argv()') == 1
    assert '"model_launched"' in text
    assert '"continuation_started"' in text
    assert "not NEW.exists()" in text
    assert '"build", "direct"' in text
