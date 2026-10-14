"""G1 single-use npm prefix correction on the original job, no Docker/model."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "scripts/g1-original-job-node-prefix-repair.py"
spec = importlib.util.spec_from_file_location("g1_node_prefix_repair", SCRIPT)
assert spec and spec.loader
g1 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(g1)


def test_commands_only_replace_relative_npm_prefix():
    assert g1.OLD == ["ddev", "exec", "npm", "--prefix", "..", "run", "build"]
    assert g1.NEW == [
        "ddev", "exec", "npm", "--prefix", "/var/www/html", "run", "build",
    ]
    assert g1.EXPECTED_CWD == "/var/www/html"
    previous = SimpleNamespace(
        npm_argv=lambda _id, _ws: [
            "docker", "exec", "--workdir", "/safe/job", "safe-executor",
            "env", "-i", "DDEV_XDG_CONFIG_HOME=/safe/xdg", *g1.OLD,
        ],
    )
    argv = g1.executor_args(previous, "safe-executor", Path("/safe/job"), g1.NEW)
    assert argv[-7:] == g1.NEW
    assert argv[:8] == [
        "docker", "exec", "--workdir", "/safe/job", "safe-executor",
        "env", "-i", "DDEV_XDG_CONFIG_HOME=/safe/xdg",
    ]
    with pytest.raises(g1.Stop, match="g1_node_command_contract_changed"):
        g1.executor_args(previous, "safe-executor", Path("/safe/job"),
                         ["bash", "-lc", "docker ps"])


def test_exact_singleton_config_cannot_be_broadened(tmp_path, monkeypatch):
    root = tmp_path / ".pcp-g1-smoke"
    (root / "config").mkdir(parents=True)
    monkeypatch.setattr(g1, "ROOT", root)
    monkeypatch.setattr(g1, "CONFIG", root / "config/projects.yml")
    previous = SimpleNamespace(PROJECT="pcp-benchmark-g1-smoke")
    data = {
        "version": 1,
        "projects": {"pcp-benchmark-g1-smoke": {
            "path": str(root / "source"),
            "runtime": {
                "developer_permission_mode": "trusted_project",
                "workspace_mode": "isolated_clone",
                "exclusive_project_lease": False,
            },
            "autonomy": {
                "allow_auto_merge_low_risk": False,
                "allow_production_deploy": False,
            },
            "ddev": {"enabled": True},
            "trusted_codex_tools": {
                "targeted_tests": [],
                "static_analysis": [],
                "frontend_quality": [g1.OLD],
            },
        }},
    }
    g1.CONFIG.write_text(json.dumps(data), encoding="utf-8")
    assert g1.read_config(previous, root / "workspaces/job") == data
    g1.update_config(data, previous.PROJECT)
    new = json.loads(g1.CONFIG.read_text(encoding="utf-8"))
    assert new["projects"][previous.PROJECT]["trusted_codex_tools"][
        "frontend_quality"] == [g1.NEW]
    with pytest.raises(g1.Stop, match="g1_trusted_phase_registry_drift"):
        g1.read_config(previous, root / "workspaces/job")
    new["projects"]["chonhac"] = {}
    g1.CONFIG.write_text(json.dumps(new), encoding="utf-8")
    with pytest.raises(g1.Stop, match="g1_trusted_phase_registry_drift"):
        g1.read_config(previous, root / "workspaces/job")


def test_cwd_probe_classifies_only_exposed_cwd_not_logs(monkeypatch):
    previous = SimpleNamespace(npm_argv=lambda *_: [
        "docker", "exec", "--workdir", "/safe/job", "executor",
        "env", "-i", *g1.OLD,
    ])
    seen = []
    def fake_run(argv, **kwargs):
        seen.append(argv)
        assert kwargs["timeout"] == 25
        assert argv[-3:] == ["ddev", "exec", "pwd"]
        return SimpleNamespace(returncode=0, stdout="/var/www/html\n",
                               stderr="not printed")
    monkeypatch.setattr(g1.subprocess, "run", fake_run)
    assert g1.observe_ddev_cwd(previous, "executor", Path("/safe/job")) == (
        "/var/www/html")
    assert len(seen) == 1


def test_cwd_mismatch_stops_before_config_change_or_build(monkeypatch):
    previous = SimpleNamespace(PROJECT="pcp-benchmark-g1-smoke")
    monkeypatch.setattr(g1, "prior_operator", lambda: previous)
    monkeypatch.setattr(g1, "exact_origin",
                        lambda *_: ("2c6db0aa6f19" + "0" * 20,
                                    Path("/safe/job"), "executor"))
    monkeypatch.setattr(g1, "read_config", lambda *_: {"projects": {}})
    monkeypatch.setattr(g1, "observe_ddev_cwd",
                        lambda *_: "/var/www/html/web")
    monkeypatch.setattr(g1, "exclusive_record", lambda *_:
                        pytest.fail("no marker before pwd proof"))
    monkeypatch.setattr(g1, "update_config", lambda *_:
                        pytest.fail("config must not be changed"))
    monkeypatch.setattr(g1, "one_node_attempt", lambda *_:
                        pytest.fail("build must not run"))
    with pytest.raises(g1.Stop, match="g1_cwd_not_expected_root"):
        g1.execute("f" * 40)


def test_one_bounded_attempt_persists_sanitized_result(tmp_path, monkeypatch):
    root = tmp_path / ".pcp-g1-smoke"
    root.mkdir()
    monkeypatch.setattr(g1, "ROOT", root)
    monkeypatch.setattr(g1, "REPAIR_FILE", root / "node-prefix-repair-evidence.json")
    previous = SimpleNamespace(PROJECT="pcp-benchmark-g1-smoke")
    job = "2c6db0aa6f19" + "0" * 20
    monkeypatch.setattr(g1, "prior_operator", lambda: previous)
    monkeypatch.setattr(g1, "exact_origin",
                        lambda *_: (job, Path("/safe/job"), "executor"))
    cfg = {"projects": {}}
    monkeypatch.setattr(g1, "read_config", lambda *_: cfg)
    monkeypatch.setattr(g1, "observe_ddev_cwd", lambda *_: g1.EXPECTED_CWD)
    called = []
    monkeypatch.setattr(g1, "update_config",
                        lambda *_: called.append("config_only"))
    monkeypatch.setattr(g1, "one_node_attempt", lambda *_: {
        "returncode": 0, "timed_out": False,
        "output_marker": True, "error_class": "NONE",
        "elapsed_seconds": 0.5,
    })
    report = g1.execute("f" * 40)
    assert called == ["config_only"]
    assert report["status"] == "PASS_G1_CORRECTED_NODE_OPERATOR_NOT_MCP"
    assert report["model_calls"] == 0
    assert report["mcp_replayed"] is False
    assert report["ready_for_autonomous_e2e"] is False
    private = json.loads(g1.REPAIR_FILE.read_text(encoding="utf-8"))
    assert private["state"] == "complete"
    assert private["config_changed"] is True
    with pytest.raises(FileExistsError):
        g1.exclusive_record({"state": "started"})


def test_source_never_replays_mcp_or_manages_containers():
    s = SCRIPT.read_text(encoding="utf-8")
    for forbidden in (
        "ddev start", "ddev stop", "docker compose", "docker system prune",
        "model.run", "create_job(", "git reset --hard",
        "PCP_TRUSTED_CODEX_DEV_TOKEN", "Bearer ", "auto_run=True",
    ):
        assert forbidden not in s
