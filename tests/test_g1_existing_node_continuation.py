"""Single existing G1 job one-command continuation: no real Docker/provider."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "scripts/g1-existing-node-continuation.py"
spec = importlib.util.spec_from_file_location("g1_existing_node_probe", SOURCE)
assert spec and spec.loader
g1 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(g1)


def test_only_preapproved_single_phase_and_inert_env(tmp_path, monkeypatch):
    monkeypatch.setattr(g1, "ROOT", tmp_path / ".pcp-g1-smoke")
    ws = g1.ROOT / "workspaces" / ("2c6db0aa6f19" + "0" * 20)
    argv = g1.npm_argv("abcdef123456", ws)
    assert argv[:5] == [
        "docker", "exec", "--workdir", str(ws), "abcdef123456",
    ]
    assert argv[5:7] == ["env", "-i"]
    assert argv[-7:] == ["ddev", "exec", "npm", "--prefix", "..", "run", "build"]
    assert "DDEV_XDG_CONFIG_HOME=" + str(g1.ROOT / "xdg") in argv
    assert not any("TOKEN=" in x or "PASSWORD=" in x or "SECRET=" in x
                   for x in argv)
    assert "docker compose" not in SOURCE.read_text(encoding="utf-8")
    assert "ddev start" not in SOURCE.read_text(encoding="utf-8")


@pytest.mark.parametrize("code,stdout,stderr,expected", [
    (0, "G1_NODE_BUILD_CHECK=PASS\n", "", "NONE"),
    (0, "npm run ok but marker absent\n", "", "ZERO_EXIT_WITHOUT_REQUIRED_MARKER"),
    (1, "", "npm error ENOENT package.json", "PACKAGE_OR_PATH_ERROR"),
    (1, "", "npm ERR! missing script", "NPM_SCRIPT_ERROR"),
    (125, "", "ddev project container not running", "DDEV_EXEC_ERROR"),
    (127, "", "some other failure", "UNCLASSIFIED_NONZERO_EXIT"),
])
def test_evidence_has_sanitized_outcome_no_logs(
    code, stdout, stderr, expected, monkeypatch,
):
    def fake_run(argv, **kwargs):
        assert argv == ["allowlisted"]
        assert kwargs.get("timeout") == g1.DOCKER_RUN_TIME
        return SimpleNamespace(returncode=code, stdout=stdout, stderr=stderr)
    monkeypatch.setattr(g1.subprocess, "run", fake_run)
    result = g1.run_bounded(["allowlisted"])
    assert result["returncode"] == code
    assert result["error_class"] == expected
    assert result["output_marker"] == (g1.OUTPUT in stdout)
    assert result["timed_out"] is False
    assert "stdout" not in result and "stderr" not in result


def test_timeout_does_not_claim_a_phase_pass(monkeypatch):
    import subprocess
    def timeout(*a, **kw):
        raise subprocess.TimeoutExpired(a[0], timeout=g1.DOCKER_RUN_TIME)
    monkeypatch.setattr(g1.subprocess, "run", timeout)
    result = g1.run_bounded(["only"])
    assert result["returncode"] is None
    assert result["error_class"] == "EXEC_TIMEOUT"
    assert result["timed_out"] is True
    assert result["output_marker"] is False


def test_single_permanent_attempt_marker_and_only_scoped_directory(
    tmp_path, monkeypatch,
):
    root = tmp_path / ".pcp-g1-smoke"
    root.mkdir()
    monkeypatch.setattr(g1, "ROOT", root)
    monkeypatch.setattr(g1, "EVIDENCE", root / "node-continuation-evidence.json")
    value = {"state": "started", "job_id": "2c6db0aa6f19" + "0" * 20}
    g1.store(value)
    with pytest.raises(FileExistsError):
        g1.store(value)
    updated = {**value, "state": "completed", "model_calls": 0}
    g1.persist(updated)
    assert json.loads(g1.EVIDENCE.read_text()) == updated
    assert not (root / "node-continuation-evidence.tmp").exists()


def test_persisted_job_and_workspace_identity_checked_before_command(
    tmp_path, monkeypatch,
):
    root = tmp_path / ".pcp-g1-smoke"
    job = "2c6db0aa6f19" + "0" * 20
    ws = root / "workspaces" / job
    ws.mkdir(parents=True)
    (root / "smoke-journal.json").write_text(json.dumps({
        "job_id": job, "project_id": g1.PROJECT,
        "source_sha": g1.SOURCE,
        "state": "workspace_pending", "model_calls": 0,
    }))
    monkeypatch.setattr(g1, "ROOT", root)
    monkeypatch.setattr(g1, "EVIDENCE", root / "node-continuation-evidence.json")
    monkeypatch.setattr(g1.os, "geteuid", lambda: root.stat().st_uid)
    monkeypatch.setattr(g1, "REPO", tmp_path / "pcp")
    g1.REPO.mkdir()
    checks = []
    def fake_call(argv, **_kw):
        checks.append(tuple(argv))
        if argv[0] != "git":
            pytest.fail("Only read-only Git checks permitted")
        if argv[3] == "rev-parse":
            if argv[4] == "--show-toplevel":
                return str(ws)
            return "1" * 40 if argv[2] == str(g1.REPO) else g1.SOURCE
        if argv[3] == "hash-object":
            return g1.DDEV_BLOB
        if argv[3] == "branch":
            return "main" if argv[2] == str(g1.REPO) else "ai/" + job[:12]
        return ""
    monkeypatch.setattr(g1, "call", fake_call)
    seen = []
    monkeypatch.setattr(g1, "attest_g1", lambda path: seen.append(path))
    found_job, found_ws = g1.workspace_identity("1" * 40)
    assert (found_job, found_ws) == (job, ws)
    assert seen == [ws]
    (root / "node-continuation-evidence.json").write_text("{}")
    with pytest.raises(g1.Stop, match="already_attempted"):
        g1.workspace_identity("1" * 40)


def test_only_exact_g1_executor_is_eligible(tmp_path, monkeypatch):
    ws = tmp_path / "workspace"
    ws.mkdir()
    monkeypatch.setattr(g1, "ROOT", tmp_path)
    def fake_call(argv, **_kw):
        if argv[:3] == ["docker", "context", "inspect"]:
            return json.dumps([{"Endpoints": {"docker": {
                "Host": "unix:///var/run/docker.sock",
            }}}])
        if "container" in argv and "ls" in argv:
            return "abcdef123456"
        raise AssertionError("No foreign Docker calls")
    monkeypatch.setattr(g1, "call", fake_call)
    monkeypatch.setattr(g1, "inspect", lambda _: {
        "Config": {"Labels": {
            "com.docker.compose.project": "pcp-g1-smoke",
            "com.docker.compose.service": "pcp-dev-executor",
            "pcp.scope": "g1-disposable-no-model",
        }},
        "State": {"Running": True},
        "HostConfig": {"Privileged": False},
        "NetworkSettings": {"Networks": {"pcp-g1-smoke-control": {}}},
        "Mounts": [
            {"Source": str(ws.parent), "Destination": str(ws.parent), "RW": True},
            {"Source": str(tmp_path / "source"),
             "Destination": str(tmp_path / "source"), "RW": False},
            {"Source": str(tmp_path / "xdg"),
             "Destination": str(tmp_path / "xdg"), "RW": True},
            {"Source": str(tmp_path / "config/projects.yml"),
             "Destination": "/g1/config/projects.yml", "RW": False},
        ],
    })
    monkeypatch.delenv("DOCKER_HOST", raising=False)
    assert g1.docker_identity(ws) == "abcdef123456"
    monkeypatch.setattr(g1, "inspect", lambda _: {"Config": {"Labels": {
        "com.docker.compose.project": "chonhac",
    }}})
    with pytest.raises(g1.Stop, match="g1_executor_identity_drift"):
        g1.docker_identity(ws)
