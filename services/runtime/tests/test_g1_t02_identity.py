"""G1-T02 Runtime broker is scoped to a new source-only identity; no model."""
from __future__ import annotations

from copy import deepcopy
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


def test_runtime_project_config_requires_exact_t02_registration(scope, monkeypatch):
    _, project = scope
    monkeypatch.setattr(config, "projects_doc",
                        lambda: {"projects": {PROJECT: project}})
    admitted = config.project_config(PROJECT)
    assert admitted["base_branch"] == "benchmark/g1-codex-smoke-v1"
    assert admitted["runtime"]["pilot_identity"] == "g1-t02-pcp"
    assert admitted["runtime"]["developer_permission_mode"] == "trusted_project"
    assert admitted["runtime"]["workspace_mode"] == "isolated_clone"
    assert admitted["runtime"]["exclusive_project_lease"] is False
    assert admitted["ddev"]["enabled"] is True
    assert all(admitted["autonomy"][key] is False for key in (
        "allow_commit", "allow_push_ai_branch", "allow_create_pr",
        "allow_auto_merge_low_risk", "allow_production_deploy",
    ))
    # Registration returns only inert configuration; it neither issues a
    # broker token nor establishes an approved baseline or starts DDEV.
    assert "PCP_DEV_BROKER_TOKEN" not in admitted
    assert "PLATFORM_INTERNAL_TOKEN" not in admitted


@pytest.mark.parametrize("case", [
    "flag_missing", "flag_wrong", "pilot_identity_wrong",
    "pilot_identity_missing", "base_branch_wrong", "base_branch_missing",
    "workspace_mode_direct", "workspace_mode_missing", "lease_true",
    "lease_missing", "branch_prefix_wrong", "branch_prefix_missing",
    "ddev_disabled", "ddev_missing", "autonomy_missing",
    "allow_commit", "allow_push_ai_branch", "allow_create_pr",
    "allow_auto_merge_low_risk", "allow_production_deploy",
    "commit_permission_missing", "push_permission_missing",
    "pr_permission_missing", "merge_permission_missing",
    "deploy_permission_missing",
])
def test_runtime_project_config_t02_rejects_unauthorized_variants(
    scope, monkeypatch, case,
):
    _, project = scope
    monkeypatch.setattr(config, "projects_doc",
                        lambda: {"projects": {PROJECT: project}})
    if case == "flag_missing":
        monkeypatch.delenv("PCP_G1_T02_IDENTITY_ENABLED")
    elif case == "flag_wrong":
        monkeypatch.setenv("PCP_G1_T02_IDENTITY_ENABLED", "true")
    elif case == "pilot_identity_wrong":
        project["runtime"]["pilot_identity"] = "g1-t01-pcp"
    elif case == "pilot_identity_missing":
        del project["runtime"]["pilot_identity"]
    elif case == "base_branch_wrong":
        project["base_branch"] = "main"
    elif case == "base_branch_missing":
        del project["base_branch"]
    elif case == "workspace_mode_direct":
        project["runtime"]["workspace_mode"] = "direct"
        project["runtime"]["exclusive_project_lease"] = True
    elif case == "workspace_mode_missing":
        del project["runtime"]["workspace_mode"]
    elif case == "lease_true":
        project["runtime"]["exclusive_project_lease"] = True
    elif case == "lease_missing":
        del project["runtime"]["exclusive_project_lease"]
    elif case == "branch_prefix_wrong":
        project["runtime"]["branch_prefix"] = "other"
    elif case == "branch_prefix_missing":
        del project["runtime"]["branch_prefix"]
    elif case == "ddev_disabled":
        project["ddev"]["enabled"] = False
    elif case == "ddev_missing":
        del project["ddev"]
    elif case == "autonomy_missing":
        del project["autonomy"]
    elif case in {
        "allow_commit", "allow_push_ai_branch", "allow_create_pr",
        "allow_auto_merge_low_risk", "allow_production_deploy",
    }:
        project["autonomy"][case] = True
    else:
        missing = {
            "commit_permission_missing": "allow_commit",
            "push_permission_missing": "allow_push_ai_branch",
            "pr_permission_missing": "allow_create_pr",
            "merge_permission_missing": "allow_auto_merge_low_risk",
            "deploy_permission_missing": "allow_production_deploy",
        }
        del project["autonomy"][missing[case]]
    with pytest.raises(ValueError, match="trusted_project requires exact"):
        config.project_config(PROJECT)


def test_runtime_project_config_t02_flag_never_admits_foreign_pilot(
    scope, monkeypatch,
):
    _, t02 = scope
    pilot = deepcopy(t02)
    pilot["runtime"]["pilot_identity"] = "g1-t01-pcp"
    monkeypatch.setattr(config, "projects_doc", lambda: {
        "projects": {"pcp-benchmark-g1-pilot": pilot},
    })
    monkeypatch.delenv("PCP_G1_PILOT_IDENTITY_ENABLED", raising=False)
    # An enabled T02 flag must not silently enable the consumed T01 project.
    with pytest.raises(ValueError, match="trusted_project requires exact"):
        config.project_config("pcp-benchmark-g1-pilot")
    with pytest.raises(KeyError, match="Unknown project_id"):
        config.project_config("pcp-benchmark-g1-foreign")


def test_runtime_project_config_preserves_smoke_and_t01_behavior(
    scope, monkeypatch,
):
    _, template = scope
    smoke = deepcopy(template)
    pilot = deepcopy(template)
    pilot["runtime"]["pilot_identity"] = "g1-t01-pcp"
    monkeypatch.setattr(config, "projects_doc", lambda: {"projects": {
        "pcp-benchmark-g1-smoke": smoke,
        "pcp-benchmark-g1-pilot": pilot,
    }})
    monkeypatch.delenv("PCP_G1_T02_IDENTITY_ENABLED", raising=False)
    monkeypatch.setenv("PCP_G1_PILOT_IDENTITY_ENABLED", "owner-approved")
    assert config.project_config(
        "pcp-benchmark-g1-smoke"
    )["runtime"]["developer_permission_mode"] == "trusted_project"
    assert config.project_config(
        "pcp-benchmark-g1-pilot"
    )["runtime"]["developer_permission_mode"] == "trusted_project"
    monkeypatch.delenv("PCP_G1_PILOT_IDENTITY_ENABLED")
    with pytest.raises(ValueError, match="trusted_project requires exact"):
        config.project_config("pcp-benchmark-g1-pilot")
    assert config.project_config(
        "pcp-benchmark-g1-smoke"
    )["runtime"]["developer_permission_mode"] == "trusted_project"
