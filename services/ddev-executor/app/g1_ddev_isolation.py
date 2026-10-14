"""Runtime Docker attestation for the single disposable G1 DDEV fixture.

Read-only Docker inspect. Docker return payloads (including container Env) are
never emitted; failures expose fixed reason codes only. This is not startup.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

PROJECT_ID = "pcp-benchmark-g1-smoke"
DDEV_NAME = "pcp-g1-codex-smoke"
PRIVATE_NETWORK = "pcp-g1-codex-smoke-private"
WEB = "ddev-" + DDEV_NAME + "-web"
DB = "ddev-" + DDEV_NAME + "-db"
EXPECTED = frozenset({WEB, DB})
BLOCKED_ENV = frozenset({
    "PLATFORM_INTERNAL_TOKEN", "ROUTER_API_TOKEN", "RUNTIME_API_TOKEN",
    "GITHUB_DELIVERY_TOKEN", "ANTIGRAVITY_BRIDGE_TOKEN",
    "OPENAI_API_KEY", "GH_TOKEN", "GITHUB_TOKEN",
    "CODEX_HOME", "SSH_AUTH_SOCK",
})


class G1IsolationStop(RuntimeError):
    """Sanitized reason code; never includes Docker inspect or environment."""


def _inspect(kind: str, name: str) -> dict:
    try:
        proc = subprocess.run(
            ["docker", kind, "inspect", name],
            text=True, capture_output=True, timeout=12, check=False,
        )
        if proc.returncode != 0:
            raise G1IsolationStop("g1_docker_inspect_unavailable")
        value = json.loads(proc.stdout)
        if not isinstance(value, list) or len(value) != 1 or not isinstance(value[0], dict):
            raise ValueError()
        return value[0]
    except (OSError, subprocess.TimeoutExpired, ValueError, TypeError) as exc:
        raise G1IsolationStop("g1_docker_inspect_invalid") from exc


def require_g1_isolated_ddev(workspace: Path) -> None:
    """Only private internal network and exact, nonprivileged DDEV containers."""
    if workspace.is_symlink() or not workspace.is_dir():
        raise G1IsolationStop("g1_workspace_invalid")
    for name in (WEB, DB):
        item = _inspect("container", name)
        labels = (item.get("Config") or {}).get("Labels") or {}
        if (
            item.get("Name") != "/" + name
            or labels.get("com.ddev.site-name") != DDEV_NAME
            or labels.get("com.ddev.approot") != str(workspace)
            or (item.get("State") or {}).get("Running") is not True
        ):
            raise G1IsolationStop("g1_ddev_container_identity_invalid")
        host = item.get("HostConfig") or {}
        if (
            host.get("Privileged") is not False
            or host.get("PidMode") == "host"
            or host.get("NetworkMode") == "host"
        ):
            raise G1IsolationStop("g1_ddev_privileged_container_denied")
        networks = (item.get("NetworkSettings") or {}).get("Networks") or {}
        if set(networks) != {PRIVATE_NETWORK}:
            raise G1IsolationStop("g1_ddev_network_not_isolated")
        mounts = item.get("Mounts") or []
        if not isinstance(mounts, list):
            raise G1IsolationStop("g1_ddev_mount_metadata_invalid")
        for mount in mounts:
            if not isinstance(mount, dict):
                raise G1IsolationStop("g1_ddev_mount_metadata_invalid")
            origin = str(mount.get("Source") or "").lower()
            target = str(mount.get("Destination") or "").lower()
            if any(marker in origin or marker in target for marker in (
                "docker.sock", "ssh-agent", "/.ssh", "/run/secrets",
            )):
                raise G1IsolationStop("g1_ddev_sensitive_mount_denied")
        if name == WEB:
            variables = (item.get("Config") or {}).get("Env") or []
            if not isinstance(variables, list) or any(
                not isinstance(v, str) or v.split("=", 1)[0] in BLOCKED_ENV
                for v in variables
            ):
                raise G1IsolationStop("g1_ddev_privileged_environment_denied")

    net = _inspect("network", PRIVATE_NETWORK)
    if net.get("Name") != PRIVATE_NETWORK or net.get("Internal") is not True:
        raise G1IsolationStop("g1_private_network_not_internal")
    peers = (net.get("Containers") or {}).values()
    if {v.get("Name") for v in peers if isinstance(v, dict)} != EXPECTED:
        raise G1IsolationStop("g1_private_network_has_foreign_peers")
