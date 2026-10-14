"""G1 Codex scoped phase broker: no Docker/provider/real workspace needed."""
from __future__ import annotations

from pathlib import Path

import pytest

from app import trusted_codex_broker as broker

JOB = "a" * 32
SHA = "b" * 40
PROJECT = "pcp-benchmark-synthetic"


@pytest.fixture
def scope(monkeypatch, tmp_path: Path):
    workspace_root = tmp_path / "workspaces"
    workspace_root.mkdir()
    ws = workspace_root / JOB
    ws.mkdir()
    monkeypatch.setenv("CODING_WORKSPACES_ROOT", str(workspace_root))
    monkeypatch.setenv("PCP_TRUSTED_CODEX_BROKER_ENABLED", "owner-approved")
    monkeypatch.setenv("PCP_TRUSTED_CODEX_JOB_ID", JOB)
    monkeypatch.setenv("PCP_TRUSTED_CODEX_PROJECT_ID", PROJECT)
    monkeypatch.setenv("PCP_TRUSTED_CODEX_SOURCE_SHA", SHA)
    monkeypatch.setenv("PCP_TRUSTED_CODEX_DEV_TOKEN", "c" * 48)
    monkeypatch.setenv("PCP_TRUSTED_CODEX_BROKER_URL", "http://ddev-executor:8790")
    monkeypatch.setenv("PLATFORM_INTERNAL_TOKEN", "synthetic-control-" + "d" * 48)
    monkeypatch.setattr(broker, "projects_doc", lambda: {"projects": {
        PROJECT: {
            "runtime": {
                "developer_permission_mode": "trusted_project",
                "workspace_mode": "isolated_clone",
                "exclusive_project_lease": False,
                "branch_prefix": "ai",
            },
            "ddev": {"enabled": True},
            "autonomy": {
                "allow_auto_merge_low_risk": False,
                "allow_production_deploy": False,
            },
        },
    }})
    monkeypatch.setattr(
        broker, "_git_read", lambda _workspace, *args: (
            str(ws) if "--show-toplevel" in args
            else "ai/" + JOB[:12] if "--show-current" in args else SHA
        ),
    )
    return ws


def allowed(ws: Path, **changes):
    request = {
        "job_id": JOB, "project_id": PROJECT, "source_commit": SHA,
        "workspace": ws, "mode": "execute", "adapter": "codex_cli",
    }
    request.update(changes)
    return broker.trusted_codex_phase_broker(**request)


def test_one_exact_broker_scope_can_run_execute_and_repair(scope):
    for mode in ("execute", "repair"):
        cfg = allowed(scope, mode=mode)
        assert cfg["PCP_DEV_BROKER_TOKEN"] == "c" * 48
        assert cfg["PCP_DEV_WORKSPACE"] == str(scope)
        assert cfg["PCP_DEV_JOB_ID"] == JOB
        assert "PLATFORM_INTERNAL_TOKEN" not in cfg
        assert "GITHUB_DELIVERY_TOKEN" not in cfg


@pytest.mark.parametrize("change", [
    {"job_id": "f" * 32},
    {"project_id": "chonhac"},
    {"project_id": "pcp-g0-fullpath-fixture"},
    {"source_commit": "e" * 40},
    {"mode": "plan"},
    {"mode": "evaluate"},
    {"adapter": "antigravity_host"},
    {"adapter": "opencode"},
])
def test_foreign_job_project_role_adapter_never_receives_tool(scope, change):
    assert allowed(scope, **change) is None


@pytest.mark.parametrize("env,value", [
    ("PCP_TRUSTED_CODEX_BROKER_ENABLED", "yes"),
    ("PCP_TRUSTED_CODEX_PROJECT_ID", "chonhac"),
    ("PCP_TRUSTED_CODEX_JOB_ID", "f" * 32),
    ("PCP_TRUSTED_CODEX_SOURCE_SHA", "e" * 40),
    ("PCP_TRUSTED_CODEX_DEV_TOKEN", "short"),
    ("PCP_TRUSTED_CODEX_BROKER_URL", "https://example.com"),
    ("PCP_TRUSTED_CODEX_BROKER_URL", "http://localhost:8790"),
    ("PCP_TRUSTED_CODEX_BROKER_URL", "http://ddev-executor:8790/admin"),
])
def test_bad_environment_fails_closed(scope, monkeypatch, env, value):
    monkeypatch.setenv(env, value)
    assert allowed(scope) is None


def test_broker_disabled_by_default(scope, monkeypatch):
    monkeypatch.delenv("PCP_TRUSTED_CODEX_BROKER_ENABLED")
    assert allowed(scope) is None


def test_privileged_control_bearer_must_not_be_reused(scope, monkeypatch):
    monkeypatch.setenv("PLATFORM_INTERNAL_TOKEN", "c" * 48)
    assert allowed(scope) is None


def test_workspace_parent_and_symlink_escape_denied(scope, tmp_path):
    outsider = tmp_path / "chonhac"
    outsider.mkdir()
    assert allowed(outsider) is None
    link = scope.parent / "shortcut"
    link.symlink_to(outsider, target_is_directory=True)
    assert allowed(link) is None


def test_legacy_registry_or_production_permission_denied(scope, monkeypatch):
    monkeypatch.setattr(broker, "projects_doc", lambda: {"projects": {
        PROJECT: {}, "chonhac": {},
    }})
    assert allowed(scope) is None
