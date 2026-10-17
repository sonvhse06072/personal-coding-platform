"""G1-T02 Runtime broker is scoped to a new source-only identity; no model."""
from __future__ import annotations

from pathlib import Path
import time

import pytest

from app import config, trusted_codex_broker as broker
from app.engine_execution import preserve_trusted_g1_ddev_name

PROJECT = "pcp-benchmark-g1-t02"
JOB = "a" * 32
SHA = "d4f4a56713e95f85ecc08c02bb43a5b5105a86a3"
SEED = (
    "# Disposable PCP G1 Codex broker smoke fixture, no hooks or custom mounts.\n"
    "name: pcp-g1-codex-smoke\n"
    "type: drupal11\n"
    "docroot: web\n"
    'php_version: "8.4"\n'
    "webserver_type: nginx-fpm\n"
    "database:\n"
    "  type: mariadb\n"
    '  version: "10.11"\n'
    'nodejs_version: "24"\n'
)


@pytest.fixture
def scope(monkeypatch, tmp_path: Path):
    root = tmp_path / "workspaces"
    ws = root / JOB
    ddev = ws / ".ddev"
    ddev.mkdir(parents=True)
    (ddev / "config.yaml").write_text(SEED, encoding="utf-8")
    (ddev / "config.g1-t02.yaml").write_text(
        broker._T02_NAME_OVERRIDE, encoding="utf-8")
    (ddev / broker._T02_CACHE_FILE).write_text(
        broker._T02_CACHE_COMPOSE, encoding="utf-8")
    project = {
        "path": str(tmp_path / "source"),
        "base_branch": "benchmark/g1-codex-smoke-v1",
        "runtime": {
            "developer_permission_mode": "trusted_project",
            "pilot_identity": "g1-t02-pcp",
            "workspace_mode": "isolated_clone",
            "exclusive_project_lease": False,
            "branch_prefix": "ai",
        },
        "ddev": {"enabled": True},
        "autonomy": {
            "allow_commit": False, "allow_push_ai_branch": False,
            "allow_create_pr": False, "allow_auto_merge_low_risk": False,
            "allow_production_deploy": False,
        },
    }
    monkeypatch.setenv("CODING_WORKSPACES_ROOT", str(root))
    monkeypatch.setenv("PCP_TRUSTED_CODEX_BROKER_ENABLED", "owner-approved")
    monkeypatch.setenv("PCP_G1_T02_IDENTITY_ENABLED", "owner-approved")
    monkeypatch.setenv("PCP_TRUSTED_CODEX_DEADLINE_EPOCH",
                       str(int(time.time()) + 900))
    monkeypatch.setenv("PCP_TRUSTED_CODEX_PROJECT_ID", PROJECT)
    monkeypatch.setenv("PCP_TRUSTED_CODEX_JOB_ID", JOB)
    monkeypatch.setenv("PCP_TRUSTED_CODEX_SOURCE_SHA", SHA)
    monkeypatch.setenv("PCP_TRUSTED_CODEX_DEV_TOKEN", "c" * 48)
    monkeypatch.setenv("PCP_TRUSTED_CODEX_BROKER_URL",
                       "http://pcp-dev-executor:8790")
    monkeypatch.setenv("PLATFORM_INTERNAL_TOKEN", "control-" + "d" * 48)
    monkeypatch.setattr(broker, "projects_doc",
                        lambda: {"projects": {PROJECT: project}})
    monkeypatch.setattr(broker, "_git_read", lambda _path, *args: (
        str(ws) if "--show-toplevel" in args else
        "ai/" + JOB[:12] if "--show-current" in args else SHA
    ))
    return ws, project


def request(ws, **change):
    args = {
        "job_id": JOB, "project_id": PROJECT, "source_commit": SHA,
        "workspace": ws, "mode": "execute", "adapter": "codex_cli",
    }
    args.update(change)
    return broker.trusted_codex_phase_broker(**args)


def test_exact_t02_source_gate_is_separate_from_t01(scope):
    ws, _ = scope
    permit = request(ws)
    assert permit is not None
    assert permit["PCP_DEV_PROJECT_ID"] == PROJECT
    assert permit["PCP_DEV_SOURCE_SHA"] == SHA
    assert permit["PCP_DEV_BROKER_TOKEN"] == "c" * 48
    assert "PLATFORM_INTERNAL_TOKEN" not in permit
    assert preserve_trusted_g1_ddev_name(
        job_id=JOB, project_id=PROJECT, source_commit=SHA, workspace=ws,
    ) is True


@pytest.mark.parametrize("env,value", [
    ("PCP_G1_T02_IDENTITY_ENABLED", ""),
    ("PCP_TRUSTED_CODEX_BROKER_ENABLED", ""),
    ("PCP_TRUSTED_CODEX_PROJECT_ID", "pcp-benchmark-g1-pilot"),
    ("PCP_TRUSTED_CODEX_JOB_ID", "b" * 32),
    ("PCP_TRUSTED_CODEX_SOURCE_SHA", "b" * 40),
    ("PCP_TRUSTED_CODEX_DEV_TOKEN", "short"),
    ("PCP_TRUSTED_CODEX_BROKER_URL", "https://outside.example"),
])
def test_missing_or_foreign_gate_never_admits_t02(scope, monkeypatch, env, value):
    ws, _ = scope
    monkeypatch.setenv(env, value)
    assert request(ws) is None
    assert preserve_trusted_g1_ddev_name(
        job_id=JOB, project_id=PROJECT, source_commit=SHA, workspace=ws,
    ) is False


@pytest.mark.parametrize("case", [
    "foreign_project", "wrong_source", "planner", "wrong_role",
    "other_workspace", "changed_seed", "changed_name", "changed_cache",
    "extra_config", "symlink", "hooks", "wrong_branch", "other_project",
    "can_commit", "can_push", "can_create_pr",
])
def test_t02_immutable_source_workspace_and_permissions(scope, monkeypatch, tmp_path, case):
    ws, project = scope
    args = {}
    if case == "foreign_project":
        args["project_id"] = "pcp-benchmark-g1-pilot"
    elif case == "wrong_source":
        args["source_commit"] = "f" * 40
    elif case == "planner":
        args["mode"] = "plan"
    elif case == "wrong_role":
        args["adapter"] = "antigravity_host"
    elif case == "other_workspace":
        outsider = tmp_path / "outsider"
        outsider.mkdir()
        args["workspace"] = outsider
    elif case == "changed_seed":
        (ws / ".ddev/config.yaml").write_text(SEED + "# changed\n")
    elif case == "changed_name":
        (ws / ".ddev/config.g1-t02.yaml").write_text(
            "override_config: true\nname: pcp-g1-codex-pilot\n")
    elif case == "changed_cache":
        (ws / ".ddev" / broker._T02_CACHE_FILE).write_text("services: {}\n")
    elif case == "extra_config":
        (ws / ".ddev/config.coding-platform.yaml").write_text("name: foreign\n")
    elif case == "symlink":
        (ws / ".ddev/shortcut").symlink_to(ws / ".ddev/config.yaml")
    elif case == "hooks":
        (ws / ".ddev/hooks").mkdir()
    elif case == "wrong_branch":
        project["base_branch"] = "main"
    elif case == "other_project":
        monkeypatch.setattr(broker, "projects_doc",
                            lambda: {"projects": {PROJECT: project, "foreign": {}}})
    elif case == "can_commit":
        project["autonomy"]["allow_commit"] = True
    elif case == "can_push":
        project["autonomy"]["allow_push_ai_branch"] = True
    elif case == "can_create_pr":
        project["autonomy"]["allow_create_pr"] = True
    assert request(ws, **args) is None


def test_runtime_project_config_still_fails_closed_for_t02(scope, monkeypatch):
    _, project = scope
    monkeypatch.setattr(config, "projects_doc",
                        lambda: {"projects": {PROJECT: project}})
    # This source-only PR MUST NOT rewrite project_config's T01-only trust rule.
    with pytest.raises(ValueError, match="trusted_project requires exact"):
        config.project_config(PROJECT)
