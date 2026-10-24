"""B2.2c1-A3 parked PCP-only DDEV SOURCE-template guards. NO real DDEV/Docker."""
from __future__ import annotations

from pathlib import Path
import runpy

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
PROFILE = ROOT / "profiles" / "pcp-local" / ".ddev"
CONFIG = PROFILE / "config.yaml"
COMPOSE = PROFILE / "docker-compose.platform.yaml"
CURRENT_DDEV = ROOT / ".ddev"


def _config():
    return yaml.safe_load(CONFIG.read_text(encoding="utf-8"))


def _compose():
    return yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))


def test_templates_are_outside_active_ddev_directory_and_readable():
    assert PROFILE.is_dir() and not PROFILE.is_symlink()
    assert CONFIG.is_file() and not CONFIG.is_symlink()
    assert COMPOSE.is_file() and not COMPOSE.is_symlink()
    assert not CONFIG.is_relative_to(CURRENT_DDEV)
    assert not COMPOSE.is_relative_to(CURRENT_DDEV)
    assert CONFIG.parent == COMPOSE.parent


def test_fresh_ddev_identity_and_hooks_absent():
    cfg = _config()
    assert set(cfg) == {
        "name", "type", "docroot", "php_version", "webserver_type",
        "database", "use_dns_when_possible", "composer_version",
    }
    assert cfg["name"] == "pcp-local"
    assert cfg["name"] != "personal-coding-platform"
    assert cfg["type"] == "php" and cfg["docroot"] == "public"
    assert cfg["php_version"] == "8.4"
    assert cfg["webserver_type"] == "nginx-fpm"
    assert cfg["database"] == {"type": "postgres", "version": "17"}
    assert "hooks" not in cfg
    assert "post-start" not in CONFIG.read_text()
    assert "exec-host" not in CONFIG.read_text()


def test_only_opt_in_inspection_service_and_no_runtime_launch_by_default():
    data = _compose()
    assert type(data) is dict and set(data) == {"services"}
    services = data["services"]
    assert set(services) == {"coding-runtime"}
    svc = services["coding-runtime"]
    assert svc["profiles"] == ["pcp-inspect"]
    assert svc["restart"] == "no"
    assert svc["image"] == "pcp-local-runtime-inspect:source-unresolved-do-not-run"
    assert svc["command"] == ["/PCP_H1B_SOURCE_ONLY_NOT_AUTHORIZED"]
    assert "personal-coding-platform-coding-runtime:local" not in COMPOSE.read_text()
    assert svc["container_name"] == "ddev-${DDEV_SITENAME}-coding-runtime"
    assert "entrypoint" not in svc
    assert "depends_on" not in svc
    assert "ports" not in svc and "expose" not in svc
    assert "build" not in svc


def test_service_is_unprivileged_readonly_and_without_docker_socket():
    svc = _compose()["services"]["coding-runtime"]
    assert svc["user"] == "${DDEV_UID}:${DDEV_GID}"
    assert svc["read_only"] is True
    assert svc["cap_drop"] == ["ALL"]
    assert svc["security_opt"] == ["no-new-privileges:true"]
    assert svc["tmpfs"] == ["/tmp:rw,nosuid,nodev,size=67108864"]
    for key in ("privileged", "pid", "network_mode", "devices", "userns_mode",
                "extra_hosts", "secrets", "env_file"):
        assert key not in svc
    raw = COMPOSE.read_text()
    assert "docker.sock" not in raw


def test_exact_parked_registry_environment_and_no_provider_secrets():
    env = _compose()["services"]["coding-runtime"]["environment"]
    assert env == {
        "PCP_RUNTIME_STARTUP_MODE": "pcp_local_inspect",
        "PROJECTS_FILE": "/config/projects.pcp-local.yml",
        "PROJECT_BASELINES_FILE": "/config/project-baselines.pcp-local.yml",
        "HOME": "/home/coder",
        "PYTHONDONTWRITEBYTECODE": "1",
    }
    assert "PCP_LOCAL_TASK_WORKER_ENABLED" not in COMPOSE.read_text()


def test_mounts_only_exact_two_readonly_draft_yaml_files():
    mounts = _compose()["services"]["coding-runtime"]["volumes"]
    assert mounts == [
        {
            "type": "bind",
            "source": "${DDEV_APPROOT}/config/projects.pcp-local.yml",
            "target": "/config/projects.pcp-local.yml",
            "read_only": True,
        },
        {
            "type": "bind",
            "source": "${DDEV_APPROOT}/config/project-baselines.pcp-local.yml",
            "target": "/config/project-baselines.pcp-local.yml",
            "read_only": True,
        },
    ]


@pytest.mark.parametrize("forbidden", [
    "/var/run/docker.sock", "HOST_HOME", "CODING_PROJECTS_ROOT",
    "CODING_WORKSPACES_ROOT", "CODING_DIRECT_PROJECT_ROOT",
    "/config/projects.yml", "/config/project-baselines.yml",
    "GITHUB_DELIVERY_TOKEN", "GITHUB_TOKEN", "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY", "ANTIGRAVITY", "DDEV_EXECUTOR",
    "n8n", "router", "host.docker.internal", "volumes_from",
    "--dangerously-bypass", "allow_commit",
])
def test_no_legacy_or_privileged_configuration_escape(forbidden):
    raw = COMPOSE.read_text(encoding="utf-8")
    assert forbidden not in raw


def test_active_legacy_config_still_has_its_old_hooks_and_project_id():
    # This test makes no edits and is NOT permission to start the old project.
    current = yaml.safe_load((CURRENT_DDEV / "config.yaml").read_text())
    assert current["name"] == "personal-coding-platform"
    assert "hooks" in current
    assert "pcp-build-images.sh" in str(current["hooks"])
    legacy = (CURRENT_DDEV / "docker-compose.platform.yaml").read_text()
    assert "/config/projects.yml" in legacy
    assert "/var/run/docker.sock" in legacy
    assert "profiles/pcp-local" not in legacy


def test_pcp_draft_remains_inactive_and_unpromoted():
    projects = yaml.safe_load((ROOT / "config/projects.pcp-local.yml").read_text())
    baselines = yaml.safe_load((ROOT / "config/project-baselines.pcp-local.yml").read_text())
    assert set(projects["projects"]) == {"pcp-local"}
    assert projects["projects"]["pcp-local"]["path"] is None
    assert projects["projects"]["pcp-local"]["registration_status"] == "draft"
    assert baselines["projects"]["pcp-local"] == {
        "active_revision": None, "revisions": {},
    }


def test_profile_paths_are_human_owner_protected():
    policy = runpy.run_path(str(ROOT / "scripts/check_project_doc_authority.py"))
    cls = policy["classify_path"]
    assert cls("profiles/pcp-local/.ddev/config.yaml") == "protected"
    assert cls("profiles/pcp-local/.ddev/docker-compose.platform.yaml") == "protected"


def test_no_host_runtime_or_deploy_side_effects():
    # Tests parse repository YAML only; no subprocess / Docker / DDEV calls.
    assert "ddev start" not in COMPOSE.read_text()
    assert "docker run" not in COMPOSE.read_text()
    assert "ddev start" not in CONFIG.read_text()
    assert "docker run" not in CONFIG.read_text()
