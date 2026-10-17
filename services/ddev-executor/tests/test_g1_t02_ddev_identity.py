"""T02-only fake Docker identity tests; never inspect the real host."""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app import g1_t02_ddev_identity as pilot
from app import main as executor

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
def snapshot(tmp_path):
    ws = tmp_path / ("a" * 32)
    ddev = ws / ".ddev"
    ddev.mkdir(parents=True)
    (ddev / "config.yaml").write_text(SEED, encoding="utf-8")
    (ddev / pilot.OVERRIDE_FILE).write_text(pilot.OVERRIDE, encoding="utf-8")
    (ddev / pilot.CACHE_FILE).write_text(pilot.CACHE_COMPOSE, encoding="utf-8")

    def container(name):
        return {
            "Name": "/" + name,
            "Config": {
                "Labels": {"com.ddev.site-name": pilot.NAME,
                           "com.ddev.approot": str(ws)},
                "Env": ["DDEV_PROJECT_TYPE=drupal11"],
            },
            "State": {"Running": True},
            "HostConfig": {"Privileged": False,
                           "PidMode": "", "NetworkMode": "default"},
            "NetworkSettings": {"Networks": {pilot.PRIVATE_NETWORK: {}}},
            "Mounts": [
                {"Source": str(ws), "Destination": "/var/www/html"},
                {"Type": "volume", "Name": pilot.PRIVATE_CACHE_NAME,
                 "Source": "/volumes/pilot-cache",
                 "Destination": "/mnt/ddev-global-cache"},
            ],
        }

    inventory = {
        pilot.WEB: container(pilot.WEB),
        pilot.DB: container(pilot.DB),
        pilot.PRIVATE_NETWORK: {
            "Name": pilot.PRIVATE_NETWORK, "Internal": True,
            "Containers": {
                "w": {"Name": pilot.WEB}, "d": {"Name": pilot.DB},
            },
        },
    }
    return ws, inventory


def test_seed_matches_exact_fixture_and_names_do_not_collide(snapshot, monkeypatch):
    ws, inventory = snapshot
    assert pilot._git_blob_sha(SEED.encode()) == pilot.SOURCE_DDEV_BLOB
    assert pilot.PROJECT_ID == "pcp-benchmark-g1-t02"
    assert pilot.NAME != pilot.DIRECT_NAME != "pcp-g1-codex-smoke"
    assert pilot.NAME != "pcp-g1-codex-pilot"
    assert pilot.PRIVATE_NETWORK != "pcp-g1-codex-pilot-private"
    assert pilot.PRIVATE_CACHE_NAME != "pcp-g1-pilot-cache"
    assert pilot.PRIVATE_NETWORK != "pcp-g1-codex-smoke-private"
    assert pilot.PRIVATE_CACHE_NAME != "pcp-g1-smoke-cache"
    monkeypatch.setattr(pilot, "_inspect", lambda _kind, n: inventory[n])
    pilot.require_t02_workspace_identity(ws, prepared=True)
    pilot.require_g1_t02_isolated_ddev(ws)


@pytest.mark.parametrize("change,code", [
    ("seed_changed", "g1_t02_seed_sha_mismatch"),
    ("name_changed", "g1_t02_ddev_name_override_changed"),
    ("cache_changed", "g1_t02_ddev_cache_override_changed"),
    ("name_missing", "g1_t02_partial_override_denied"),
    ("both_missing", "g1_t02_overrides_not_prepared"),
    ("foreign_config", "g1_t02_unknown_ddev_override_denied"),
    ("foreign_compose", "g1_t02_unknown_ddev_override_denied"),
    ("hooks", "g1_t02_ddev_commands_denied"),
    ("symlink", "g1_t02_ddev_symlink_denied"),
    ("shared_network", "g1_t02_ddev_network_not_isolated"),
    ("wrong_owner", "g1_t02_container_identity_invalid"),
    ("privileged", "g1_t02_privileged_mode_denied"),
    ("docker_socket", "g1_t02_sensitive_mount_denied"),
    ("ssh_agent", "g1_t02_sensitive_mount_denied"),
    ("shared_cache", "g1_t02_cache_not_isolated"),
    ("foreign_env", "g1_t02_privileged_environment_denied"),
    ("stopped", "g1_t02_container_identity_invalid"),
    ("public_network", "g1_t02_network_not_internal"),
    ("foreign_peer", "g1_t02_network_has_foreign_peer"),
])
def test_pilot_fail_closed_for_changed_files_docker_identity(
    snapshot, monkeypatch, change, code,
):
    ws, inv = snapshot
    ddev = ws / ".ddev"
    web = inv[pilot.WEB]
    if change == "seed_changed":
        (ddev / "config.yaml").write_text(SEED + "# foreign", encoding="utf-8")
    elif change == "name_changed":
        (ddev / pilot.OVERRIDE_FILE).write_text(
            "override_config: true\nname: chonhac\n", encoding="utf-8")
    elif change == "cache_changed":
        (ddev / pilot.CACHE_FILE).write_text("services: {}\n", encoding="utf-8")
    elif change == "name_missing":
        (ddev / pilot.OVERRIDE_FILE).unlink()
    elif change == "both_missing":
        (ddev / pilot.OVERRIDE_FILE).unlink()
        (ddev / pilot.CACHE_FILE).unlink()
    elif change == "foreign_config":
        (ddev / "config.coding-platform.yaml").write_text(
            "name: chonhac\n", encoding="utf-8")
    elif change == "foreign_compose":
        (ddev / "docker-compose.host-mount.yaml").write_text(
            "services: {}\n", encoding="utf-8")
    elif change == "hooks":
        (ddev / "commands").mkdir()
    elif change == "symlink":
        (ddev / "shortcut").symlink_to(ddev / "config.yaml")
    elif change == "shared_network":
        web["NetworkSettings"]["Networks"]["ddev_default"] = {}
    elif change == "wrong_owner":
        web["Config"]["Labels"]["com.ddev.approot"] = "/home/other"
    elif change == "privileged":
        web["HostConfig"]["Privileged"] = True
    elif change == "docker_socket":
        web["Mounts"].append({"Source": "/var/run/docker.sock",
                              "Destination": "/var/run/docker.sock"})
    elif change == "ssh_agent":
        web["Mounts"].append({"Source": "/run/ssh-agent/socket",
                              "Destination": "/run/socket"})
    elif change == "shared_cache":
        web["Mounts"][1]["Name"] = "ddev-global-cache"
    elif change == "foreign_env":
        web["Config"]["Env"].append("GITHUB_TOKEN=never-exposed")
    elif change == "stopped":
        web["State"]["Running"] = False
    elif change == "public_network":
        inv[pilot.PRIVATE_NETWORK]["Internal"] = False
    elif change == "foreign_peer":
        inv[pilot.PRIVATE_NETWORK]["Containers"]["alien"] = {
            "Name": "ddev-chonhac-web",
        }
    monkeypatch.setattr(pilot, "_inspect", lambda _kind, n: inv[n])
    with pytest.raises(pilot.G1IsolationStop, match=code):
        pilot.require_g1_t02_isolated_ddev(ws)




def test_t02_executor_default_off_and_does_not_rewrite_fixture(snapshot, monkeypatch):
    ws, _ = snapshot
    monkeypatch.delenv("PCP_G1_T02_IDENTITY_ENABLED", raising=False)
    with pytest.raises(HTTPException, match="G1 T02 identity gate is OFF"):
        executor._reconcile_workspace_ddev_identity(
            ws, "a" * 32, project_id=pilot.PROJECT_ID)
    monkeypatch.setenv("PCP_G1_T02_IDENTITY_ENABLED", "owner-approved")
    assert executor._reconcile_workspace_ddev_identity(
        ws, "a" * 32, project_id=pilot.PROJECT_ID) is None
    assert not (ws / ".ddev/config.coding-platform.yaml").exists()


def test_t02_executor_phase_attests_before_any_ddev_start(snapshot, monkeypatch):
    ws, _ = snapshot
    monkeypatch.setenv("PCP_G1_T02_IDENTITY_ENABLED", "owner-approved")
    monkeypatch.setattr(executor, "project", lambda _: {
        "ddev": {"enabled": True, "preflight": []},
        "runtime": {"workspace_mode": "isolated_clone"},
    })
    monkeypatch.setattr(executor, "_validate_workspace", lambda *a, **kw: ws)
    monkeypatch.setattr(executor, "_workspace_instance_mode",
                        lambda *a, **kw: "isolated_clone")
    monkeypatch.setattr(executor, "run_tracked",
                        lambda *a, **kw: pytest.fail("DDEV must not start"))
    calls = []
    monkeypatch.setattr(executor, "require_g1_t02_isolated_ddev",
                        lambda p: calls.append(p))
    task = executor.PhaseRequest(
        job_id="a" * 32, project_id=pilot.PROJECT_ID,
        workspace=str(ws), phase="preflight")
    assert executor.phase(task).passed is True
    assert calls == [ws]
    monkeypatch.setattr(executor, "require_g1_t02_isolated_ddev",
                        lambda _: (_ for _ in ()).throw(
                            pilot.G1IsolationStop("not_isolated")))
    with pytest.raises(HTTPException, match="not_isolated"):
        executor.phase(task)
    monkeypatch.delenv("PCP_G1_T02_IDENTITY_ENABLED")
    with pytest.raises(HTTPException, match="identity gate is OFF"):
        executor.phase(task)


def test_t02_executor_developer_phase_scope_and_autonomy_denied(snapshot, monkeypatch):
    import time
    ws, _ = snapshot
    job = "a" * 32
    command = ["ddev", "exec", "php", "vendor/bin/phpunit",
               "-c", "web/core/phpunit.xml.dist",
               "web/modules/custom/pcp_f2_fixture/tests/src/Unit"]
    cfg = {
        "base_branch": "benchmark/g1-codex-smoke-v1",
        "runtime": {"developer_permission_mode": "trusted_project",
                    "workspace_mode": "isolated_clone",
                    "exclusive_project_lease": False,
                    "branch_prefix": "ai", "pilot_identity": "g1-t02-pcp"},
        "ddev": {"enabled": True},
        "autonomy": {"allow_commit": False,
                     "allow_push_ai_branch": False,
                     "allow_create_pr": False,
                     "allow_auto_merge_low_risk": False,
                     "allow_production_deploy": False},
        "trusted_codex_tools": {"targeted_tests": [command]},
    }
    monkeypatch.setenv("CODING_WORKSPACES_ROOT", str(ws.parent))
    monkeypatch.setenv("PCP_TRUSTED_CODEX_BROKER_ENABLED", "owner-approved")
    monkeypatch.setenv("PCP_G1_T02_IDENTITY_ENABLED", "owner-approved")
    monkeypatch.setenv("PCP_TRUSTED_CODEX_PROJECT_ID", pilot.PROJECT_ID)
    monkeypatch.setenv("PCP_TRUSTED_CODEX_JOB_ID", job)
    monkeypatch.setenv("PCP_TRUSTED_CODEX_SOURCE_SHA", pilot.SOURCE_SHA)
    monkeypatch.setenv("PCP_TRUSTED_CODEX_DEV_TOKEN", "c" * 48)
    monkeypatch.setenv("PCP_TRUSTED_CODEX_DEADLINE_EPOCH",
                       str(int(time.time()) + 600))
    monkeypatch.setenv("PLATFORM_INTERNAL_TOKEN", "d" * 48)
    for key in ("PCP_EXECUTOR_PROJECT_SCOPE", "PCP_F2_GIT_ONLY_ENABLED",
                "PCP_G0_EXECUTION_ENABLED", "PCP_G0_DELIVERY_ENABLED"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setattr(executor, "load_projects",
                        lambda: {pilot.PROJECT_ID: cfg})
    monkeypatch.setattr(executor, "project", lambda _: cfg)
    monkeypatch.setattr(executor, "is_git_repo", lambda _: True)
    monkeypatch.setattr(executor, "git", lambda _ws, *args, **kwargs: (
        str(ws) if "--show-toplevel" in args else
        "ai/" + job[:12] if "--show-current" in args else
        "" if "--porcelain" in args else pilot.SOURCE_SHA
    ))
    monkeypatch.setattr(executor.subprocess, "run",
                        lambda *a, **kw: SimpleNamespace(
                            returncode=0, stdout="", stderr=""))
    seen = []
    monkeypatch.setattr(executor, "require_g1_t02_isolated_ddev",
                        lambda p: seen.append(p))
    payload = executor.TrustedCodexPhaseRequest(
        job_id=job, project_id=pilot.PROJECT_ID, workspace=str(ws),
        source_commit=pilot.SOURCE_SHA, phase="targeted_tests")
    path, commands = executor._trusted_dev_plan(payload)
    assert path == ws and commands == [command] and seen == [ws]
    cfg["autonomy"]["allow_create_pr"] = True
    with pytest.raises(HTTPException, match="G1 T02 identity admission denied"):
        executor._trusted_dev_plan(payload)
    cfg["autonomy"]["allow_create_pr"] = False
    monkeypatch.delenv("PCP_G1_T02_IDENTITY_ENABLED")
    with pytest.raises(HTTPException, match="G1 T02 identity admission denied"):
        executor._trusted_dev_plan(payload)
