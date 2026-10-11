#!/usr/bin/env python3
"""G0-only ChatGPT device authentication and direct-CLI parity operator.

No WorkOrder dispatch, fixture branch mutation, model inference, delivery,
DDEV, host Codex, Antigravity or legacy PCP operation is performed here.

  preflight --expected-sha SHA  # read only
  prepare --expected-sha SHA    # make fresh private G0 auth directories only
  status --expected-sha SHA     # metadata only; never reads cached token bytes
  login-pcp --expected-sha SHA  # interactive device login, local WSL terminal
  login-direct --expected-sha SHA

Device URL and one-time code are shown only to the Owner's local terminal.
Never paste the output of a login command into chat or GitHub.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import sys

import yaml


ROOT = Path(__file__).resolve().parents[1]
OPERATOR = ROOT / "scripts/g0-inspection-operator.py"
UPGRADER = ROOT / "scripts/g0-inspection-source-upgrade.py"
DEPLOYED_SHA = "b60824e65af3db99f1aaff144310f14989d16896"
CLI_VERSION = "0.160.0"
OVERLAY = ROOT / "deploy/g0/compose.provider-auth.candidate.yml"
PROFILE = "owner-gated-g0-auth"
G0_AUTH_SERVICES = ("auth_pcp", "auth_direct")
G0_DIRECT_SERVICE = "direct"
G0_AUTH_DIRS = {
    "pcp": "/home/coder/.codex-g0",
    "direct": "/home/coder/.codex-direct",
}
G0_AUTH_NETWORKS = {
    "pcp": "pcp-g0d01-provider-pcp",
    "direct": "pcp-g0d01-provider-direct",
}
AUTH_CONFIG = 'cli_auth_credentials_store = "file"\nforced_login_method = "chatgpt"\n'
AUTHORIZED_STATUS = {"preflight", "prepared", "device_login_attempted"}


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError("G0-only source module unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


g0 = _load_module("g0_inspection_operator", OPERATOR)
upgrader = _load_module("g0_source_upgrade", UPGRADER)


def _root() -> Path:
    return Path.home() / ".pcp-g0d01"


def _auth_root() -> Path:
    return _root() / "provider"


def _auth_dir(arm: str) -> Path:
    if arm not in G0_AUTH_DIRS:
        raise g0.GateError("g0_unknown_auth_arm")
    return _auth_root() / arm


def _direct_workspace() -> Path:
    return _root() / "arms/direct/workspace"


def _check_private_existing(path: Path, *, directory: bool) -> None:
    if path.is_symlink() or (not path.is_dir() if directory else not path.is_file()):
        raise g0.GateError("g0_private_auth_path_invalid")
    if path.stat().st_mode & 0o077:
        raise g0.GateError("g0_auth_permissions_not_private")


def _check_config(arm: str) -> bool:
    directory = _auth_dir(arm)
    _check_private_existing(directory, directory=True)
    cfg = directory / "config.toml"
    _check_private_existing(cfg, directory=False)
    if cfg.read_text(encoding="utf-8") != AUTH_CONFIG:
        raise g0.GateError("g0_auth_config_drift")
    auth = directory / "auth.json"
    if auth.exists() or auth.is_symlink():
        _check_private_existing(auth, directory=False)
        return True
    return False


def _validate_overlay() -> None:
    if OVERLAY.is_symlink() or not OVERLAY.is_file():
        raise g0.GateError("g0_auth_compose_overlay_not_frozen")
    document = yaml.safe_load(OVERLAY.read_text(encoding="utf-8"))
    if not isinstance(document, dict) or set(document) != {
        "x-g0-provider-contract", "services", "networks",
    }:
        raise g0.GateError("g0_auth_compose_envelope_changed")
    contract = document["x-g0-provider-contract"]
    if contract != {
        "status": "parked",
        "provider_login_method": "chatgpt-device-auth",
        "g0_runtime_activation": False,
        "git_delivery": False,
        "g0d_t01_dispatch": False,
        "shared_host_codex_auth_used": False,
        "network_domain_allowlist_verified": False,
    }:
        raise g0.GateError("g0_auth_contract_broadened")
    services = document["services"]
    if not isinstance(services, dict) or set(services) != {*G0_AUTH_SERVICES, G0_DIRECT_SERVICE}:
        raise g0.GateError("g0_auth_services_not_exact")
    networks = document["networks"]
    if networks != {
        "g0-provider-pcp": {"name": G0_AUTH_NETWORKS["pcp"], "internal": False},
        "g0-provider-direct": {"name": G0_AUTH_NETWORKS["direct"], "internal": False},
    }:
        raise g0.GateError("g0_auth_networks_not_exact")

    expected = {
        "auth_pcp": ("pcp", [PROFILE], False),
        "auth_direct": ("direct", [PROFILE], False),
        "direct": ("direct", ["owner-gated-g0-direct"], True),
    }
    for name, (arm, profile, has_workspace) in expected.items():
        svc = services[name]
        if (
            svc.get("profiles") != profile
            or svc.get("restart") != "no"
            or svc.get("pull_policy") != "never"
            or svc.get("read_only") is not True
            or svc.get("cap_drop") != ["ALL"]
            or svc.get("security_opt") != ["no-new-privileges:true"]
            or svc.get("entrypoint") != ["codex"]
            or svc.get("command") != ["--version"]
            or svc.get("networks") != [f"g0-provider-{arm}"]
            or svc.get("user") !=
                "${PCP_G0_UID:?g0_nonroot_uid_required}:${PCP_G0_GID:?g0_nonroot_gid_required}"
            or svc.get("image") !=
                "${PCP_G0_RUNTIME_IMAGE:?exact_deployed_g0_runtime_image_required}"
            or svc.get("environment") != {
                "HOME": "/home/coder", "CODEX_HOME": G0_AUTH_DIRS[arm],
            }
        ):
            raise g0.GateError("g0_auth_service_broadened")
        prohibited = {
            "build", "ports", "privileged", "devices", "cap_add",
            "network_mode", "pid", "ipc", "env_file", "secrets",
            "depends_on", "volumes_from", "extra_hosts", "links",
        }
        if prohibited & set(svc):
            raise g0.GateError("g0_auth_service_privilege_added")
        mounts = svc.get("volumes")
        wanted = [{
            "type": "bind",
            "source": (
                "${PCP_G0_AUTH_PCP_DIR:?new_separate_pcp_auth_dir_required}"
                if arm == "pcp" else
                "${PCP_G0_AUTH_DIRECT_DIR:?new_separate_direct_auth_dir_required}"
            ),
            "target": G0_AUTH_DIRS[arm],
            "bind": {"create_host_path": False},
        }]
        if has_workspace:
            wanted.append({
                "type": "bind",
                "source": "${PCP_G0_DIRECT_WORKSPACE_DIR:?independent_frozen_fixture_workspace_required}",
                "target": "/g0/direct-workspace",
                "bind": {"create_host_path": False},
            })
            if svc.get("working_dir") != "/g0/direct-workspace":
                raise g0.GateError("g0_direct_working_directory_not_exact")
        if mounts != wanted:
            raise g0.GateError("g0_auth_mount_scope_changed")
        if not svc.get("tmpfs") or svc.get("pids_limit") != 128:
            raise g0.GateError("g0_auth_process_bounds_missing")
        if svc.get("mem_limit") != ("1024m" if has_workspace else "512m"):
            raise g0.GateError("g0_auth_mem_limit_changed")


def _context(repo: Path, fixture: Path, expected_sha: str, *,
             require_prepared: bool) -> tuple[dict[str, str], dict]:
    if not g0.SOURCE_SHA.fullmatch(expected_sha):
        raise g0.GateError("g0_exact_expected_sha_required")
    g0.require_local_docker_context()
    g0.require_exact_repo(repo, g0.EXPECTED_REPO, "main", expected_sha)
    g0.require_exact_repo(fixture, g0.EXPECTED_FIXTURE, "benchmark/pcp", g0.SEED)
    g0.guard_source(repo, fixture)
    _validate_overlay()
    deployed, password, workspaces = g0.read_private_state(Path.home())
    if deployed != DEPLOYED_SHA:
        raise g0.GateError("g0_expected_inspection_revision_mismatch")
    upgrader._verify_g0_resources(deployed)
    upgrader._require_empty_g0_job_store()
    if upgrader._codex_cli_version() != CLI_VERSION:
        raise g0.GateError("g0_codex_cli_version_changed")

    image_tag = g0.resource_names(deployed)["runtime"]
    if g0.inspect("container", g0.NAMES["runtime"]).get("Image") != g0.inspect(
        "image", image_tag
    ).get("Id"):
        raise g0.GateError("g0_runtime_image_identity_changed")

    for name in G0_AUTH_NETWORKS.values():
        if g0.exists("network", name):
            network = g0.inspect("network", name)
            labels = network.get("Labels") or {}
            if (
                labels.get("com.docker.compose.project") != g0.PROJECT
                or network.get("Internal") is not False
            ):
                raise g0.GateError("g0_auth_network_collision_or_ownership")
    if require_prepared:
        _check_private_existing(_auth_root(), directory=True)
        for arm in G0_AUTH_DIRS:
            _check_config(arm)
        _check_private_existing(_direct_workspace(), directory=True)
    else:
        for candidate in (
            _auth_root(), _auth_dir("pcp"), _auth_dir("direct"),
            _direct_workspace(),
        ):
            if candidate.exists() or candidate.is_symlink():
                raise g0.GateError("g0_auth_profile_already_prepared")
    env = g0.compose_env(repo, fixture, workspaces, deployed, password)
    env.update({
        "PCP_G0_AUTH_PCP_DIR": str(_auth_dir("pcp")),
        "PCP_G0_AUTH_DIRECT_DIR": str(_auth_dir("direct")),
        "PCP_G0_DIRECT_WORKSPACE_DIR": str(_direct_workspace()),
    })
    return env, {
        "project": g0.PROJECT,
        "deployed_source_sha": deployed,
        "installed_codex_cli_version": CLI_VERSION,
        "provider_login": "chatgpt-device-auth",
        "separate_auth_roots": True,
        "g0_runtime_mode": "inspect",
        "g0_executor_mode": "health_only",
        "network_domain_allowlist_verified": False,
        "network_enabled_for_running_g0_runtime": False,
        "credentials_reused_from_host_codex": False,
        "model_calls": 0,
        "ready_to_dispatch_g0d_t01": False,
    }


def _compose(repo: Path) -> list[str]:
    return [
        "docker", "compose", "-p", g0.PROJECT,
        "-f", str(repo / "deploy/g0/compose.candidate.yml"),
        "-f", str(OVERLAY), "--profile", PROFILE,
    ]


def preflight(repo: Path, fixture: Path, sha: str) -> dict:
    env, report = _context(repo, fixture, sha, require_prepared=False)
    g0.run(_compose(repo) + ["config", "--quiet"],
           env=env, label="g0_auth_compose_source_check", timeout=30)
    return {"status": "PASS", "phase": "g0_auth_preflight", **report}


def prepare(repo: Path, fixture: Path, sha: str) -> dict:
    preflight(repo, fixture, sha)
    root = _root()
    _check_private_existing(root, directory=True)
    # No existing CODEX_HOME/session/cache is copied or inspected.
    (_auth_root()).mkdir(mode=0o700)
    for arm in G0_AUTH_DIRS:
        folder = _auth_dir(arm)
        folder.mkdir(mode=0o700)
        config = folder / "config.toml"
        fd = os.open(config, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(AUTH_CONFIG)
    arms = _root() / "arms"
    if arms.exists() or arms.is_symlink():
        raise g0.GateError("g0_direct_workspace_owner_collision")
    arms.mkdir(mode=0o700)
    direct = arms / "direct"
    direct.mkdir(mode=0o700)
    _direct_workspace().mkdir(mode=0o700)
    # Do not clone or advance benchmark branches at this stage.
    return {
        "status": "PASS", "phase": "g0_auth_profiles_prepared",
        "profile_names": sorted(G0_AUTH_DIRS),
        "provider_login_required": True,
        "network_started": False,
        "model_calls": 0, "ready_to_dispatch_g0d_t01": False,
    }


def status(repo: Path, fixture: Path, sha: str) -> dict:
    env, report = _context(repo, fixture, sha, require_prepared=True)
    g0.run(_compose(repo) + ["config", "--quiet"],
           env=env, label="g0_auth_compose_prepared_check", timeout=30)
    return {
        "status": "PASS", "phase": "g0_auth_local_state",
        **report,
        "pcp_cached_auth_present": _check_config("pcp"),
        "direct_cached_auth_present": _check_config("direct"),
    }


def device_login(repo: Path, fixture: Path, sha: str, arm: str) -> dict:
    if arm not in G0_AUTH_DIRS:
        raise g0.GateError("g0_unknown_login_arm")
    env, report = _context(repo, fixture, sha, require_prepared=True)
    g0.run(_compose(repo) + ["config", "--quiet"],
           env=env, label="g0_login_compose_config", timeout=30)
    # Interactive output intentionally stays only on Owner's local WSL terminal.
    # Never capture or return OAuth URLs/codes or auth contents through GitHub.
    command = _compose(repo) + [
        "run", "--rm", "--no-deps", f"auth_{arm}",
        "login", "--device-auth",
    ]
    result = subprocess.run(command, env=env, timeout=900, check=False)
    if result.returncode:
        raise g0.GateError("g0_device_login_not_completed")
    return {
        "status": "PASS", "phase": "g0_device_login_completed",
        "arm": arm, "credential_value_recorded": False,
        "model_calls": 0, "ready_to_dispatch_g0d_t01": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "mode", choices=("preflight", "prepare", "status", "login-pcp", "login-direct"),
    )
    parser.add_argument("--expected-sha", default="")
    args = parser.parse_args()
    repo = Path.home() / "personal-coding-platform-v1"
    fixture = Path.home() / "pcp-g0-fixtures/pcp-g0-drupal-fixture"
    try:
        if args.mode == "preflight":
            result = preflight(repo, fixture, args.expected_sha)
        elif args.mode == "prepare":
            result = prepare(repo, fixture, args.expected_sha)
        elif args.mode == "status":
            result = status(repo, fixture, args.expected_sha)
        else:
            arm = args.mode.removeprefix("login-")
            result = device_login(repo, fixture, args.expected_sha, arm)
    except (g0.GateError, OSError, ValueError, TypeError, KeyError,
            subprocess.TimeoutExpired, yaml.YAMLError) as exc:
        reason = (str(exc) if isinstance(exc, g0.GateError)
                  else "g0_auth_local_preflight_or_interactive_error")
        print(json.dumps({
            "status": "STOP", "phase": args.mode,
            "reason": reason, "do_not_retry_blindly": True,
            "ready_to_dispatch_g0d_t01": False,
        }, sort_keys=True))
        return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
