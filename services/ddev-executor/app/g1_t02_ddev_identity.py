"""Exact, default-off G1-T02 pilot DDEV identity; never starts Docker.

Separate from the accepted G1 smoke identity. Operator-created overrides are
strictly byte-pinned and rechecked at every developer-phase admission; the
model cannot alter the DDEV topology even if Git locally excludes overrides.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

from .g1_ddev_isolation import BLOCKED_ENV, G1IsolationStop, _inspect

PROJECT_ID = "pcp-benchmark-g1-t02"
SOURCE_SHA = "d4f4a56713e95f85ecc08c02bb43a5b5105a86a3"
SOURCE_DDEV_BLOB = "7a3e97a2a35fc8e67b67021365e7e91c448b52c9"
NAME = "pcp-g1-codex-t02"
DIRECT_NAME = "pcp-g1-codex-t02-direct"
PRIVATE_NETWORK = "pcp-g1-codex-t02-private"
PRIVATE_CACHE_NAME = "pcp-g1-t02-cache"
WEB = f"ddev-{NAME}-web"
DB = f"ddev-{NAME}-db"
OVERRIDE_FILE = "config.g1-t02.yaml"
OVERRIDE = "override_config: true\nname: pcp-g1-codex-t02\n"
CACHE_FILE = "docker-compose.g1-t02.yaml"
CACHE_COMPOSE = (
    "# G1-T02 private DDEV cache; never model editable.\n"
    "services:\n"
    "  web:\n"
    "    volumes:\n"
    "      - g1-t02-private-cache:/mnt/ddev-global-cache\n"
    "  db:\n"
    "    volumes:\n"
    "      - g1-t02-private-cache:/mnt/ddev-global-cache\n"
    "volumes:\n"
    "  g1-t02-private-cache:\n"
    "    external: true\n"
    "    name: pcp-g1-t02-cache\n"
)


def _git_blob_sha(data: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(data)).encode("ascii") + b"\0" + data).hexdigest()


def require_t02_workspace_identity(workspace: Path, *, prepared: bool) -> None:
    """Immutable seed, no hooks/extras, and optional pre-operator state."""
    ddev = workspace / ".ddev"
    seed = ddev / "config.yaml"
    if (
        not workspace.is_dir() or workspace.is_symlink()
        or not ddev.is_dir() or ddev.is_symlink()
        or seed.is_symlink() or not seed.is_file()
    ):
        raise G1IsolationStop("g1_t02_seed_invalid")
    try:
        if _git_blob_sha(seed.read_bytes()) != SOURCE_DDEV_BLOB:
            raise G1IsolationStop("g1_t02_seed_sha_mismatch")
        if any(path.is_symlink() for path in ddev.rglob("*")):
            raise G1IsolationStop("g1_t02_ddev_symlink_denied")
        if (ddev / "commands").exists() or (ddev / "hooks").exists():
            raise G1IsolationStop("g1_t02_ddev_commands_denied")
        # Excluded files cannot be protected with git status alone. Permit only
        # these exact reviewed DDEV config/compose overrides, no other additions.
        configs = {p.name for p in ddev.glob("config*.y*ml")}
        composes = {p.name for p in ddev.glob("docker-compose*.y*ml")}
        allowed_configs = {"config.yaml", OVERRIDE_FILE}
        if configs - allowed_configs or composes - {CACHE_FILE}:
            raise G1IsolationStop("g1_t02_unknown_ddev_override_denied")
        name_override = ddev / OVERRIDE_FILE
        cache_override = ddev / CACHE_FILE
        if name_override.exists() != cache_override.exists():
            raise G1IsolationStop("g1_t02_partial_override_denied")
        if prepared and (not name_override.is_file() or not cache_override.is_file()):
            raise G1IsolationStop("g1_t02_overrides_not_prepared")
        if name_override.exists() and name_override.read_text(encoding="utf-8") != OVERRIDE:
            raise G1IsolationStop("g1_t02_ddev_name_override_changed")
        if cache_override.exists() and cache_override.read_text(encoding="utf-8") != CACHE_COMPOSE:
            raise G1IsolationStop("g1_t02_ddev_cache_override_changed")
    except (OSError, UnicodeError) as exc:
        raise G1IsolationStop("g1_t02_ddev_files_unreadable") from exc


def require_g1_t02_isolated_ddev(workspace: Path) -> None:
    """Admit only exact new G1 web/db on one private internal network/cache."""
    require_t02_workspace_identity(workspace, prepared=True)
    for name in (WEB, DB):
        item = _inspect("container", name)
        labels = (item.get("Config") or {}).get("Labels") or {}
        if (
            item.get("Name") != "/" + name
            or labels.get("com.ddev.site-name") != NAME
            or labels.get("com.ddev.approot") != str(workspace)
            or (item.get("State") or {}).get("Running") is not True
        ):
            raise G1IsolationStop("g1_t02_container_identity_invalid")
        host = item.get("HostConfig") or {}
        if (
            host.get("Privileged") is not False
            or host.get("PidMode") == "host"
            or host.get("NetworkMode") in {"host", "container"}
        ):
            raise G1IsolationStop("g1_t02_privileged_mode_denied")
        networks = (item.get("NetworkSettings") or {}).get("Networks") or {}
        if set(networks) != {PRIVATE_NETWORK}:
            raise G1IsolationStop("g1_t02_ddev_network_not_isolated")
        mounts = item.get("Mounts") or []
        if not isinstance(mounts, list) or any(not isinstance(m, dict) for m in mounts):
            raise G1IsolationStop("g1_t02_mount_metadata_invalid")
        cache = [m for m in mounts if m.get("Destination") == "/mnt/ddev-global-cache"]
        if len(cache) != 1 or cache[0].get("Name") != PRIVATE_CACHE_NAME:
            raise G1IsolationStop("g1_t02_cache_not_isolated")
        for mount in mounts:
            if mount.get("Name") == "ddev-global-cache":
                raise G1IsolationStop("g1_t02_global_cache_denied")
            text = (str(mount.get("Source") or "") + "|" +
                    str(mount.get("Destination") or "")).lower()
            if any(x in text for x in ("docker.sock", "ssh-agent", "/.ssh", "/run/secrets")):
                raise G1IsolationStop("g1_t02_sensitive_mount_denied")
        if name == WEB:
            env = (item.get("Config") or {}).get("Env") or []
            if not isinstance(env, list) or any(
                not isinstance(value, str) or value.split("=", 1)[0] in BLOCKED_ENV
                for value in env
            ):
                raise G1IsolationStop("g1_t02_privileged_environment_denied")
    network = _inspect("network", PRIVATE_NETWORK)
    if network.get("Name") != PRIVATE_NETWORK or network.get("Internal") is not True:
        raise G1IsolationStop("g1_t02_network_not_internal")
    peers = (network.get("Containers") or {}).values()
    if {v.get("Name") for v in peers if isinstance(v, dict)} != {WEB, DB}:
        raise G1IsolationStop("g1_t02_network_has_foreign_peer")
