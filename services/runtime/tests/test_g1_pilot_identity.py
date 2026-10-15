"""G1 pilot Runtime admission is separate from accepted smoke and default OFF."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import time

import pytest
import yaml

from app import config, trusted_codex_broker as broker
from app.engine_execution import preserve_trusted_g1_ddev_name

PROJECT = "pcp-benchmark-g1-pilot"
SEED_SHA = "d4f4a56713e95f85ecc08c02bb43a5b5105a86a3"
JOB = "a" * 32
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
PILOT_NAME = "override_config: true\nname: pcp-g1-codex-pilot\n"
PILOT_CACHE = (
    "# G1-T01 private DDEV cache; never model editable.\n"
    "services:\n"
    "  web:\n"
    "    volumes:\n"
    "      - g1-pilot-private-cache:/mnt/ddev-global-cache\n"
    "  db:\n"
    "    volumes:\n"
    "      - g1-pilot-private-cache:/mnt/ddev-global-cache\n"
    "volumes:\n"
    "  g1-pilot-private-cache:\n"
    "    external: true\n"
    "    name: pcp-g1-pilot-cache\n"
)


@pytest.fixture
def scope(monkeypatch, tmp_path):
    root = tmp_path / "workspaces"
    ws = root / JOB
    ddev = ws / ".ddev"
    ddev.mkdir(parents=True)
    (ddev / "config.yaml").write_text(SEED, encoding="utf-8")
    (ddev / "config.g1-pilot.yaml").write_text(PILOT_NAME, encoding="utf-8")
    (ddev / "docker-compose.g1-pilot.yaml").write_text(PILOT_CACHE, encoding="utf-8")
    assert hashlib.sha1(
        b"blob " + str(len(SEED.encode())).encode() + b"\0" + SEED.encode()
    ).hexdigest() == broker._PILOT_DDEV_SEED_SHA

    source = tmp_path / "source"
    source.mkdir()
    project = {
        "path": str(source),
        "base_branch": "benchmark/g1-codex-smoke-v1",
        "runtime": {
            "developer_permission_mode": "trusted_project",
            "pilot_identity": "g1-t01-pcp",
            "workspace_mode": "isolated_clone",
            "exclusive_project_lease": False,
            "branch_prefix": "ai",
        },
        "ddev": {"enabled": True},
        "autonomy": {
            "allow_auto_merge_low_risk": False,
            "allow_production_deploy": False,
        },
    }
    monkeypatch.setenv("CODING_WORKSPACES_ROOT", str(root))
    monkeypatch.setenv("PCP_G1_PILOT_IDENTITY_ENABLED", "owner-approved")
    monkeypatch.setenv("PCP_TRUSTED_CODEX_BROKER_ENABLED", "owner-approved")
    monkeypatch.setenv("PCP_TRUSTED_CODEX_DEADLINE_EPOCH", str(int(time.time()) + 900))
    monkeypatch.setenv("PCP_TRUSTED_CODEX_PROJECT_ID", PROJECT)
    monkeypatch.setenv("PCP_TRUSTED_CODEX_JOB_ID", JOB)
    monkeypatch.setenv("PCP_TRUSTED_CODEX_SOURCE_SHA", SEED_SHA)
    monkeypatch.setenv("PCP_TRUSTED_CODEX_DEV_TOKEN", "c" * 48)
    monkeypatch.setenv("PCP_TRUSTED_CODEX_BROKER_URL", "http://pcp-dev-executor:8790")
    monkeypatch.setenv("PLATFORM_INTERNAL_TOKEN", "control-" + "d" * 48)
    monkeypatch.setattr(broker, "projects_doc", lambda: {"projects": {PROJECT: project}})
    monkeypatch.setattr(broker, "_git_read", lambda _path, *args: (
        str(ws) if "--show-toplevel" in args else
        "ai/" + JOB[:12] if "--show-current" in args else SEED_SHA
    ))
    return ws, source, project


def admitted(ws, **diff):
    args = {
        "job_id": JOB, "project_id": PROJECT, "source_commit": SEED_SHA,
        "workspace": ws, "mode": "execute", "adapter": "codex_cli",
    }
    args.update(diff)
    return broker.trusted_codex_phase_broker(**args)


def test_pilot_explicit_scope_positive_and_runtime_preserves_operator_name(scope):
    ws, _, _ = scope
    permit = admitted(ws)
    assert permit is not None
    assert set(permit) == {
        "PCP_DEV_BROKER_URL", "PCP_DEV_BROKER_TOKEN",
        "PCP_DEV_JOB_ID", "PCP_DEV_PROJECT_ID",
        "PCP_DEV_WORKSPACE", "PCP_DEV_SOURCE_SHA",
    }
    assert permit["PCP_DEV_JOB_ID"] == JOB
    assert permit["PCP_DEV_SOURCE_SHA"] == SEED_SHA
    assert preserve_trusted_g1_ddev_name(
        job_id=JOB, project_id=PROJECT,
        source_commit=SEED_SHA, workspace=ws,
    ) is True


@pytest.mark.parametrize("name,value", [
    ("PCP_G1_PILOT_IDENTITY_ENABLED", ""),
    ("PCP_TRUSTED_CODEX_BROKER_ENABLED", ""),
    ("PCP_TRUSTED_CODEX_PROJECT_ID", "pcp-benchmark-g1-smoke"),
    ("PCP_TRUSTED_CODEX_JOB_ID", "b" * 32),
    ("PCP_TRUSTED_CODEX_SOURCE_SHA", "b" * 40),
])
def test_pilot_flags_fail_closed(scope, monkeypatch, name, value):
    ws, _, _ = scope
    monkeypatch.setenv(name, value)
    assert admitted(ws) is None
    assert preserve_trusted_g1_ddev_name(
        job_id=JOB, project_id=PROJECT, source_commit=SEED_SHA, workspace=ws,
    ) is False


@pytest.mark.parametrize("case", [
    "foreign_project", "wrong_source", "planner",
    "wrong_role", "other_workspace",
    "changed_name", "changed_cache", "extra_compose", "symlink",
    "missing_cache", "host_hooks", "wrong_branch", "merge_grant",
])
def test_pilot_broker_denies_cross_project_and_malicious_overrides(
    scope, monkeypatch, tmp_path, case,
):
    ws, _, project = scope
    opts = {}
    if case == "foreign_project":
        opts["project_id"] = "chonhac"
    elif case == "wrong_source":
        opts["source_commit"] = "e" * 40
    elif case == "planner":
        opts["mode"] = "plan"
    elif case == "wrong_role":
        opts["adapter"] = "antigravity_host"
    elif case == "other_workspace":
        stranger = tmp_path / "chonhac"
        stranger.mkdir()
        opts["workspace"] = stranger
    elif case == "changed_name":
        (ws / ".ddev/config.g1-pilot.yaml").write_text(
            "name: chonhac\n", encoding="utf-8")
    elif case == "changed_cache":
        (ws / ".ddev/docker-compose.g1-pilot.yaml").write_text(
            "services: {}\n", encoding="utf-8")
    elif case == "extra_compose":
        (ws / ".ddev/docker-compose.foreign.yaml").write_text(
            "services: {}\n", encoding="utf-8")
    elif case == "symlink":
        (ws / ".ddev/shortcut").symlink_to(ws / ".ddev/config.yaml")
    elif case == "missing_cache":
        (ws / ".ddev/docker-compose.g1-pilot.yaml").unlink()
    elif case == "host_hooks":
        (ws / ".ddev/commands").mkdir()
    elif case == "wrong_branch":
        project["base_branch"] = "main"
    elif case == "merge_grant":
        project["autonomy"]["allow_auto_merge_low_risk"] = True
    assert admitted(ws, **opts) is None


def test_project_config_requires_pilot_gate_and_exact_contract(scope, monkeypatch, tmp_path):
    _, source, project = scope
    config_path = tmp_path / "projects.yml"
    config_path.write_text(yaml.safe_dump({
        "version": 1, "projects": {PROJECT: project},
    }), encoding="utf-8")
    monkeypatch.setenv("PROJECTS_FILE", str(config_path))
    assert config.project_config(PROJECT)["runtime"]["pilot_identity"] == "g1-t01-pcp"
    monkeypatch.setenv("PCP_G1_PILOT_IDENTITY_ENABLED", "")
    with pytest.raises(ValueError, match="trusted_project requires exact"):
        config.project_config(PROJECT)
    monkeypatch.setenv("PCP_G1_PILOT_IDENTITY_ENABLED", "owner-approved")
    project["runtime"]["pilot_identity"] = "g1-t02-anything"
    config_path.write_text(yaml.safe_dump({
        "version": 1, "projects": {PROJECT: project},
    }), encoding="utf-8")
    with pytest.raises(ValueError, match="trusted_project requires exact"):
        config.project_config(PROJECT)
