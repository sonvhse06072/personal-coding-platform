"""G1 DDEV live Docker isolation: all tests synthetic; no Docker or model calls."""
from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app import g1_ddev_isolation as isolation
from app import main as executor


@pytest.fixture
def snapshot(tmp_path):
    ws = tmp_path / ("a" * 32)
    ws.mkdir()
    def container(name):
        return {
            "Name": "/" + name,
            "Config": {
                "Labels": {
                    "com.ddev.site-name": isolation.DDEV_NAME,
                    "com.ddev.approot": str(ws),
                },
                "Env": ["DDEV_PROJECT_TYPE=drupal11"],
            },
            "State": {"Running": True},
            "HostConfig": {
                "Privileged": False, "PidMode": "", "NetworkMode": "default",
            },
            "NetworkSettings": {"Networks": {isolation.PRIVATE_NETWORK: {}}},
            "Mounts": [{"Source": str(ws), "Destination": "/var/www/html"}],
        }
    items = {
        isolation.WEB: container(isolation.WEB),
        isolation.DB: container(isolation.DB),
        isolation.PRIVATE_NETWORK: {
            "Name": isolation.PRIVATE_NETWORK,
            "Internal": True,
            "Containers": {
                "idweb": {"Name": isolation.WEB},
                "iddb": {"Name": isolation.DB},
            },
        },
    }
    return ws, items


def test_exact_running_private_ddev_is_admitted(snapshot, monkeypatch):
    ws, items = snapshot
    monkeypatch.setattr(isolation, "_inspect", lambda _kind, name: items[name])
    isolation.require_g1_isolated_ddev(ws)


@pytest.mark.parametrize("change,reason", [
    ("shared_network", "g1_ddev_network_not_isolated"),
    ("privileged", "g1_ddev_privileged_container_denied"),
    ("wrong_owner", "g1_ddev_container_identity_invalid"),
    ("docker_socket", "g1_ddev_sensitive_mount_denied"),
    ("ssh_agent", "g1_ddev_sensitive_mount_denied"),
    ("control_token", "g1_ddev_privileged_environment_denied"),
    ("stopped", "g1_ddev_container_identity_invalid"),
    ("non_internal", "g1_private_network_not_internal"),
    ("foreign_peer", "g1_private_network_has_foreign_peers"),
])
def test_cross_project_credentials_and_egress_fail_closed(
    snapshot, monkeypatch, change, reason,
):
    ws, items = snapshot
    web, net = items[isolation.WEB], items[isolation.PRIVATE_NETWORK]
    if change == "shared_network":
        web["NetworkSettings"]["Networks"]["ddev_default"] = {}
    elif change == "privileged":
        web["HostConfig"]["Privileged"] = True
    elif change == "wrong_owner":
        web["Config"]["Labels"]["com.ddev.approot"] = "/home/other"
    elif change == "docker_socket":
        web["Mounts"].append({
            "Source": "/var/run/docker.sock",
            "Destination": "/var/run/docker.sock",
        })
    elif change == "ssh_agent":
        web["Mounts"].append({
            "Source": "/some/ssh-agent/sock", "Destination": "/run/agent",
        })
    elif change == "control_token":
        web["Config"]["Env"].append("PLATFORM_INTERNAL_TOKEN=hidden-value")
    elif change == "stopped":
        web["State"]["Running"] = False
    elif change == "non_internal":
        net["Internal"] = False
    elif change == "foreign_peer":
        net["Containers"]["foreign"] = {"Name": "ddev-chonhac-web"}
    monkeypatch.setattr(isolation, "_inspect", lambda _kind, name: items[name])
    with pytest.raises(isolation.G1IsolationStop, match=reason):
        isolation.require_g1_isolated_ddev(ws)


def test_docker_inspect_errors_never_echo_secrets(monkeypatch):
    monkeypatch.setattr(isolation.subprocess, "run", lambda *_a, **_kw:
        SimpleNamespace(returncode=1, stdout="", stderr="TOKEN=secret"))
    with pytest.raises(isolation.G1IsolationStop) as exc:
        isolation._inspect("container", isolation.WEB)
    assert "secret" not in str(exc.value)


def test_workspace_acquisition_does_not_write_g1_ddev_override(
    snapshot, monkeypatch,
):
    ws, _ = snapshot
    ddev = ws / ".ddev"
    ddev.mkdir()
    conf = ddev / "config.yaml"
    conf.write_text("reviewed fixture placeholder", encoding="utf-8")
    monkeypatch.setattr(executor, "git", lambda *_a, **_kw:
        "7a3e97a2a35fc8e67b67021365e7e91c448b52c9")
    assert executor._reconcile_workspace_ddev_identity(
        ws, "a" * 32, project_id=isolation.PROJECT_ID,
    ) is None
    assert not (ddev / "config.coding-platform.yaml").exists()
    conf.unlink()
    with pytest.raises(HTTPException, match="immutable DDEV"):
        executor._reconcile_workspace_ddev_identity(
            ws, "a" * 32, project_id=isolation.PROJECT_ID,
        )


def test_existing_non_g1_workspaces_keep_dynamic_ddev_override(tmp_path):
    ws = tmp_path / "other"
    (ws / ".ddev").mkdir(parents=True)
    output = executor._reconcile_workspace_ddev_identity(
        ws, "b" * 32, project_id="pcp-validation-fixture",
    )
    assert output is not None
    assert "name: cp-bbbbbbbbbb" in output.read_text(encoding="utf-8")


def test_g1_preflight_refuses_to_bootstrap_ddev_before_attestation(
    snapshot, monkeypatch,
):
    ws, _ = snapshot
    project = {
        "runtime": {"workspace_mode": "isolated_clone"},
        "ddev": {"enabled": True, "preflight": []},
    }
    monkeypatch.setattr(executor, "project", lambda _id: project)
    monkeypatch.setattr(executor, "_validate_workspace", lambda *_a, **_kw: ws)
    monkeypatch.setattr(executor, "_workspace_instance_mode",
                        lambda *_a, **_kw: "isolated_clone")
    monkeypatch.setattr(executor, "git", lambda *_a, **_kw: "")
    monkeypatch.setattr(executor, "_reconcile_workspace_ddev_identity",
                        lambda *_a, **_kw: None)
    calls = []
    monkeypatch.setattr(executor, "run_tracked", lambda *_a, **_kw:
                        pytest.fail("G1 must never implicitly start DDEV"))
    monkeypatch.setattr(executor, "require_g1_isolated_ddev",
                        lambda _ws: calls.append("attested"))
    request = executor.PhaseRequest(
        job_id="a" * 32, project_id=isolation.PROJECT_ID,
        workspace=str(ws), phase="preflight",
    )
    answer = executor.phase(request)
    assert answer.passed is True
    assert calls == ["attested"]
    assert answer.infrastructure == []


def test_g1_preflight_missing_isolation_cannot_start_ddev(
    snapshot, monkeypatch,
):
    ws, _ = snapshot
    monkeypatch.setattr(executor, "project", lambda _id: {
        "ddev": {"enabled": True},
        "runtime": {"workspace_mode": "isolated_clone"},
    })
    monkeypatch.setattr(executor, "_validate_workspace", lambda *_a, **_kw: ws)
    monkeypatch.setattr(executor, "run_tracked", lambda *_a, **_kw:
                        pytest.fail("No DDEV start on missing isolation"))
    def deny(_workspace):
        raise isolation.G1IsolationStop("g1_ddev_network_not_isolated")
    monkeypatch.setattr(executor, "require_g1_isolated_ddev", deny)
    request = executor.PhaseRequest(
        job_id="a" * 32, project_id=isolation.PROJECT_ID,
        workspace=str(ws), phase="preflight",
    )
    with pytest.raises(HTTPException, match="g1_ddev_network_not_isolated"):
        executor.phase(request)
