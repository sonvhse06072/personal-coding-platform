"""G1 pilot admission: negative identity, DDEV boundary, secrets; NO Docker."""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app import g1_pilot_ddev_identity as pilot
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
    assert pilot.PROJECT_ID == "pcp-benchmark-g1-pilot"
    assert pilot.NAME != pilot.DIRECT_NAME != "pcp-g1-codex-smoke"
    assert pilot.PRIVATE_NETWORK != "pcp-g1-codex-smoke-private"
    assert pilot.PRIVATE_CACHE_NAME != "pcp-g1-smoke-cache"
    monkeypatch.setattr(pilot, "_inspect", lambda _kind, n: inventory[n])
    pilot.require_pilot_workspace_identity(ws, prepared=True)
    pilot.require_g1_pilot_isolated_ddev(ws)


@pytest.mark.parametrize("change,code", [
    ("seed_changed", "g1_pilot_seed_sha_mismatch"),
    ("name_changed", "g1_pilot_ddev_name_override_changed"),
    ("cache_changed", "g1_pilot_ddev_cache_override_changed"),
    ("name_missing", "g1_pilot_partial_override_denied"),
    ("both_missing", "g1_pilot_overrides_not_prepared"),
    ("foreign_config", "g1_pilot_unknown_ddev_override_denied"),
    ("foreign_compose", "g1_pilot_unknown_ddev_override_denied"),
    ("hooks", "g1_pilot_ddev_commands_denied"),
    ("symlink", "g1_pilot_ddev_symlink_denied"),
    ("shared_network", "g1_pilot_ddev_network_not_isolated"),
    ("wrong_owner", "g1_pilot_container_identity_invalid"),
    ("privileged", "g1_pilot_privileged_mode_denied"),
    ("docker_socket", "g1_pilot_sensitive_mount_denied"),
    ("ssh_agent", "g1_pilot_sensitive_mount_denied"),
    ("shared_cache", "g1_pilot_cache_not_isolated"),
    ("foreign_env", "g1_pilot_privileged_environment_denied"),
    ("stopped", "g1_pilot_container_identity_invalid"),
    ("public_network", "g1_pilot_network_not_internal"),
    ("foreign_peer", "g1_pilot_network_has_foreign_peer"),
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
        pilot.require_g1_pilot_isolated_ddev(ws)


def test_executor_acquires_pilot_without_dynamic_override(snapshot, monkeypatch):
    ws, _ = snapshot
    monkeypatch.setenv("PCP_G1_PILOT_IDENTITY_ENABLED", "owner-approved")
    for filename in (pilot.OVERRIDE_FILE, pilot.CACHE_FILE):
        (ws / ".ddev" / filename).unlink()
    assert executor._reconcile_workspace_ddev_identity(
        ws, "a" * 32, project_id=pilot.PROJECT_ID,
    ) is None
    assert not (ws / ".ddev/config.coding-platform.yaml").exists()
    (ws / ".ddev" / pilot.OVERRIDE_FILE).write_text(
        pilot.OVERRIDE, encoding="utf-8")
    (ws / ".ddev" / pilot.CACHE_FILE).write_text(
        pilot.CACHE_COMPOSE, encoding="utf-8")
    assert executor._reconcile_workspace_ddev_identity(
        ws, "a" * 32, project_id=pilot.PROJECT_ID,
    ) is None
    monkeypatch.setenv("PCP_G1_PILOT_IDENTITY_ENABLED", "")
    with pytest.raises(HTTPException, match="identity gate is OFF"):
        executor._reconcile_workspace_ddev_identity(
            ws, "a" * 32, project_id=pilot.PROJECT_ID,
        )


def test_phase_checks_isolation_before_any_ddev_start(snapshot, monkeypatch):
    ws, _ = snapshot
    monkeypatch.setenv("PCP_G1_PILOT_IDENTITY_ENABLED", "owner-approved")
    monkeypatch.setattr(executor, "project", lambda _id: {
        "ddev": {"enabled": True, "preflight": []},
        "runtime": {"workspace_mode": "isolated_clone"},
    })
    monkeypatch.setattr(executor, "_validate_workspace", lambda *_a, **_kw: ws)
    monkeypatch.setattr(executor, "_workspace_instance_mode",
                        lambda *_a, **_kw: "isolated_clone")
    monkeypatch.setattr(executor, "_reconcile_workspace_ddev_identity",
                        lambda *_a, **_kw: None)
    monkeypatch.setattr(executor, "run_tracked", lambda *_a, **_kw:
                        pytest.fail("Pilot must not implicitly start DDEV"))
    calls = []
    monkeypatch.setattr(executor, "require_g1_pilot_isolated_ddev",
                        lambda path: calls.append(path))
    result = executor.phase(executor.PhaseRequest(
        job_id="a" * 32, project_id=pilot.PROJECT_ID,
        workspace=str(ws), phase="preflight",
    ))
    assert result.passed is True
    assert calls == [ws]
    monkeypatch.setattr(executor, "require_g1_pilot_isolated_ddev",
                        lambda _path: (_ for _ in ()).throw(
                            pilot.G1IsolationStop("no pilot DDEV yet")))
    with pytest.raises(HTTPException, match="no pilot DDEV yet"):
        executor.phase(executor.PhaseRequest(
            job_id="a" * 32, project_id=pilot.PROJECT_ID,
            workspace=str(ws), phase="preflight",
        ))
