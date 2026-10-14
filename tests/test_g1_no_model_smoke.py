"""Source-only regression for one-shot G1 owner operator. No Docker/model calls."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/g1-no-model-smoke.py"
SPEC = importlib.util.spec_from_file_location("g1_no_model_operator", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
g1 = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(g1)


def test_only_singleton_g1_config_and_omitted_shared_ddev(tmp_path, monkeypatch):
    monkeypatch.setattr(g1, "ROOT", tmp_path)
    g1.files()
    projects = yaml.safe_load((tmp_path / "config/projects.yml").read_text())
    assert list(projects["projects"]) == ["pcp-benchmark-g1-smoke"]
    cfg = projects["projects"]["pcp-benchmark-g1-smoke"]
    assert cfg["runtime"]["developer_permission_mode"] == "trusted_project"
    assert cfg["runtime"]["workspace_mode"] == "isolated_clone"
    assert cfg["autonomy"]["allow_auto_merge_low_risk"] is False
    assert cfg["autonomy"]["allow_production_deploy"] is False
    assert cfg["ddev"]["preflight"] == []
    assert set(cfg["trusted_codex_tools"]) == {
        "targeted_tests", "static_analysis", "frontend_quality",
    }
    assert cfg["trusted_codex_tools"]["frontend_quality"] == [[
        "ddev", "exec", "npm", "--prefix", "..", "run", "build",
    ]]
    baseline = yaml.safe_load((tmp_path / "config/project-baselines.yml").read_text())
    rev = baseline["projects"]["pcp-benchmark-g1-smoke"]["revisions"][g1.BASELINE]
    assert rev["source_commit"] == g1.SOURCE
    assert rev["status"] == "approved"
    config = (tmp_path / "xdg/ddev/global_config.yaml").read_text()
    assert "ddev-router" in config and "ddev-ssh-agent" in config
    assert "chonhac" not in json.dumps(projects)
    with pytest.raises(FileExistsError):
        g1.files()


def test_compose_scope_and_only_executor_has_docker_socket():
    doc = yaml.safe_load(
        (ROOT / "deploy/g1/compose.no-model.yml").read_text(encoding="utf-8")
    )
    assert doc["name"] == "pcp-g1-smoke"
    assert set(doc["services"]) == {"db", "runtime", "pcp-dev-executor"}
    assert set(doc["networks"]) == {"g1-control"}
    assert doc["networks"]["g1-control"]["internal"] is True
    for name, service in doc["services"].items():
        assert service["profiles"] == ["g1-no-model"]
        assert "ports" not in service
        assert service["restart"] == "no"
    assert all(
        "/var/run/docker.sock" not in json.dumps(doc["services"][name])
        for name in ("runtime", "db")
    )
    assert "/var/run/docker.sock" in json.dumps(doc["services"]["pcp-dev-executor"])
    assert doc["volumes"]["g1-db"]["name"] == "pcp-g1-smoke-postgres"


def test_container_identity_rejected_before_network_mutation(monkeypatch, tmp_path):
    env = {}
    ws = tmp_path / "workspaces" / ("a" * 32)
    ws.mkdir(parents=True)

    def call(argv, _env, step, **_kw):
        assert step == "fixture_container_inventory"
        return "\n".join(g1.CONTAINERS)

    def docker_json(_env, kind, name):
        return {
            "Name": "/" + name,
            "Config": {"Labels": {"com.ddev.site-name": "chonhac",
                                  "com.ddev.approot": str(ws)}},
            "State": {"Running": True},
            "HostConfig": {"Privileged": False},
        }

    monkeypatch.setattr(g1, "call", call)
    monkeypatch.setattr(g1, "docker_json", docker_json)
    with pytest.raises(g1.Stop, match="fixture_runtime_identity_or_privilege_drift"):
        g1.require_new_ddev(env, ws)


def test_mcp_no_model_proof_requires_exact_tool_success(monkeypatch):
    def response(passed: bool):
        return "\n".join(json.dumps(line) for line in (
            {"jsonrpc": "2.0", "id": 1,
             "result": {"serverInfo": {"name": "pcp-fixture-dev"}}},
            {"jsonrpc": "2.0", "id": 2,
             "result": {"tools": [{"name": "pcp_run_project_checks"}]}},
            {"jsonrpc": "2.0", "id": 3,
             "result": {"isError": not passed,
                        "content": [{"text": "G1_NODE_BUILD_CHECK=PASS" if passed
                                     else "failed"}]}},
        ))
    passed = [True]
    def fake_compose(_env, _step, *args, **kw):
        assert args[-2:] == ("python3", "/app/app/trusted_codex_mcp.py")
        assert kw["stdin"].count('"method": "tools/call"') == 1
        return response(passed[0])
    monkeypatch.setattr(g1, "compose", fake_compose)
    g1.no_model_mcp({})
    passed[0] = False
    with pytest.raises(g1.Stop, match="g1_real_executor_node_phase_failed"):
        g1.no_model_mcp({})


def test_no_hidden_g0_chonhac_auto_model_or_global_cleanup():
    content = SCRIPT.read_text(encoding="utf-8")
    for forbidden in ("docker system prune", "ddev poweroff", "docker compose down",
                      "git reset --hard", "git pull --force", "resume_f2",
                      "PCP_F2_GIT_ONLY_ENABLED", "auto_run':True"):
        assert forbidden not in content
    assert "PCP_G1_BROKER_ENABLED" in content
    assert '"model_calls": 0' in content
