#!/usr/bin/env python3
"""G0 fixture-only protected execution activation; no job/model dispatch.

Source preparation is not an operational permission. The Human Owner must
separately approve mounting the dedicated G0 auth profile, provider egress,
G0-only Runtime/Executor mode transition and private internal API tokens.

preflight --expected-sha SHA : read-only; no provider call
activate --expected-sha SHA --owner-approved-activate : Owner only, G0-only
status --expected-sha SHA : read-only
restore --expected-sha SHA --owner-approved-activate : Owner only, G0-only

The legacy PCP Runtime, Chợ Nhạc, host Codex, DDEV, historic jobs/leases and
GitHub fixture branches are explicitly out of scope.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
from pathlib import Path
import secrets

import yaml


ROOT = Path(__file__).resolve().parents[1]
AUTH_FILE = ROOT / "scripts/g0-codex-auth-operator.py"
FORENSICS_FILE = ROOT / "scripts/g0-direct-parity-timeout-forensics.py"
OVERLAY = ROOT / "deploy/g0/compose.fixture-execution.candidate.yml"
TOKENS_FILE = "fixture-execution-tokens.json"
JOURNAL_FILE = "fixture-execution-activation.json"
SERVICES = ("executor", "runtime")


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError("G0 activation source module unavailable")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


auth = _load("g0_auth_for_fixture_activation", AUTH_FILE)
forensics = _load("g0_direct_forensics_for_fixture_activation", FORENSICS_FILE)
g0 = auth.g0


def _private(name: str) -> Path:
    root = Path.home() / ".pcp-g0d01"
    auth._check_private_existing(root, directory=True)
    return root / name


def _validate_overlay() -> None:
    if OVERLAY.is_symlink() or not OVERLAY.is_file():
        raise g0.GateError("g0_execution_overlay_missing_or_symlink")
    try:
        doc = yaml.safe_load(OVERLAY.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise g0.GateError("g0_execution_overlay_invalid_yaml") from exc
    if not isinstance(doc, dict) or set(doc) != {
        "x-g0-execution-contract", "services", "networks",
    }:
        raise g0.GateError("g0_execution_overlay_envelope_changed")
    if doc["x-g0-execution-contract"] != {
        "status": "owner-activation-pending",
        "scope": "pcp-g0-drupal-fixture",
        "only_services_recreated": list(SERVICES),
        "automatic_dispatch": False,
        "github_delivery_enabled": False,
        "ddev_enabled": False,
        "global_codex_used": False,
        "domain_egress_restricted": False,
    }:
        raise g0.GateError("g0_execution_contract_broadened")
    if doc["networks"] != {"g0-provider-pcp": {
        "name": auth.G0_AUTH_NETWORKS["pcp"], "internal": False,
    }}:
        raise g0.GateError("g0_execution_network_broadened")
    services = doc["services"]
    internal = "${PCP_G0_INTERNAL_TOKEN:?private_g0_internal_token_required}"
    if not isinstance(services, dict) or set(services) != set(SERVICES):
        raise g0.GateError("g0_execution_service_scope_broadened")
    if services["executor"] != {"environment": {
        "PCP_G0_EXECUTION_ENABLED": "owner-approved",
        "PLATFORM_INTERNAL_TOKEN": internal,
    }}:
        raise g0.GateError("g0_execution_executor_config_broadened")
    runtime = services["runtime"]
    if (
        not isinstance(runtime, dict)
        or set(runtime) != {"read_only", "environment", "volumes", "networks"}
        or runtime["read_only"] is not True
        or runtime["networks"] != ["g0-private", "g0-provider-pcp"]
    ):
        raise g0.GateError("g0_execution_runtime_config_broadened")
    if runtime["environment"] != {
        "PCP_RUNTIME_STARTUP_MODE": "g0_fixture_run",
        "PCP_G0_EXECUTION_ENABLED": "owner-approved",
        "PCP_G0_DELIVERY_ENABLED": "",
        "PCP_G0_MODEL_ID": "gpt-6-luna",
        "PCP_G0_REASONING_EFFORT": "medium",
        "PCP_G0_CODEX_CLI_VERSION": "0.160.0",
        "PCP_G0_CODEX_HOME": "/home/coder/.codex-g0",
        "CODEX_HOME": "/home/coder/.codex-g0",
        "PLATFORM_INTERNAL_TOKEN": internal,
        "RUNTIME_API_TOKEN":
            "${PCP_G0_RUNTIME_API_TOKEN:?private_g0_runtime_token_required}",
    }:
        raise g0.GateError("g0_execution_runtime_env_broadened")
    if runtime["volumes"] != [
        {
            "type": "bind",
            "source": "${PCP_G0_AUTH_PCP_DIR:?owner_only_g0_pcp_auth_required}",
            "target": "/home/coder/.codex-g0",
            "bind": {"create_host_path": False},
        },
        {
            "type": "tmpfs", "target": "/tmp",
            "tmpfs": {"size": 134217728},
        },
    ]:
        raise g0.GateError("g0_execution_runtime_mounts_broadened")


def _compose(repo: Path) -> list[str]:
    return [
        "docker", "compose", "-p", g0.PROJECT,
        "-f", str(repo / "deploy/g0/compose.candidate.yml"),
        "-f", str(auth.OVERLAY), "-f", str(OVERLAY),
        "--profile", g0.PROFILE,
    ]


def _compose_env(repo: Path, fixture: Path, *, internal: str, runtime: str):
    deployed, db_password, workspaces = g0.read_private_state(Path.home())
    if deployed != auth.DEPLOYED_SHA:
        raise g0.GateError("g0_execution_deployed_source_mismatch")
    env = g0.compose_env(repo, fixture, workspaces, deployed, db_password)
    env.update({
        "PCP_G0_AUTH_PCP_DIR": str(auth._auth_dir("pcp")),
        "PCP_G0_AUTH_DIRECT_DIR": str(auth._auth_dir("direct")),
        "PCP_G0_DIRECT_WORKSPACE_DIR": str(auth._direct_workspace()),
        "PCP_G0_INTERNAL_TOKEN": internal,
        "PCP_G0_RUNTIME_API_TOKEN": runtime,
    })
    return env


def _render(repo: Path, env: dict[str, str]) -> None:
    # Do not emit Compose output: it embeds G0 private tokens and DB password.
    raw = g0.run(
        _compose(repo) + ["config", "--format", "json"],
        env=env, label="g0_execution_compose_render", timeout=30,
    )
    try:
        services = json.loads(raw)["services"]
        runtime = services["runtime"]
        executor = services["executor"]
    except (ValueError, TypeError, KeyError) as exc:
        raise g0.GateError("g0_execution_rendered_compose_invalid") from exc
    if not isinstance(services, dict) or not {
        "runtime", "executor", "db", "router"
    }.issubset(services):
        raise g0.GateError("g0_execution_rendered_services_changed")
    if (
        set(runtime.get("networks") or {}) != {
            "g0-private", "g0-provider-pcp",
        } or set(executor.get("networks") or {}) != {"g0-private"}
        or runtime.get("read_only") is not True
        or any(v.get("ports") or v.get("privileged") or v.get("devices")
               or v.get("volumes_from") for v in (runtime, executor))
    ):
        raise g0.GateError("g0_execution_rendered_privileges_changed")
    expected = {
        "/g0/config/projects.yml",
        "/g0/config/project-baselines.yml",
        "/g0/config/models.yml",
        "/g0/workspaces", "/home/coder/.codex-g0", "/tmp",
    }
    mounts = runtime.get("volumes") or []
    if not isinstance(mounts, list) or len(mounts) != len(expected):
        raise g0.GateError("g0_execution_rendered_mount_count")
    by_target = {
        item.get("target"): item for item in mounts if isinstance(item, dict)
    }
    if (
        set(by_target) != expected
        or by_target["/home/coder/.codex-g0"].get("type") != "bind"
        or by_target["/home/coder/.codex-g0"].get("source")
            != str(auth._auth_dir("pcp"))
        or not auth._is_exact_rendered_tmpfs(by_target["/tmp"])
    ):
        raise g0.GateError("g0_execution_rendered_mount_identity")
    for service in (runtime, executor):
        for mount in service.get("volumes") or []:
            if not isinstance(mount, dict) or (
                mount.get("target") == "/var/run/docker.sock"
                or "/chonhac" in str(mount.get("source") or "")
            ):
                raise g0.GateError("g0_execution_foreign_mount")
    if any("GITHUB_DELIVERY_TOKEN" in (s.get("environment") or {})
           for s in (runtime, executor)):
        raise g0.GateError("g0_execution_no_github_delivery_tokens")


def _exclusive_create(path: Path, value: dict) -> None:
    if path.exists() or path.is_symlink():
        raise g0.GateError("g0_execution_artifact_already_exists")
    try:
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError as exc:
        raise g0.GateError("g0_execution_claim_already_exists") from exc
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        json.dump(value, handle, sort_keys=True)


def _verify_containers(mode: str, *, allow_partial: bool = False) -> None:
    for svc in SERVICES:
        data = g0.inspect("container", g0.NAMES[svc])
        labels = (data.get("Config") or {}).get("Labels") or {}
        networks = (data.get("NetworkSettings") or {}).get("Networks") or {}
        mounts = data.get("Mounts") or []
        state = data.get("State") or {}
        image = g0.inspect("image", g0.resource_names(auth.DEPLOYED_SHA)[svc])
        if (
            data.get("Name") != "/" + g0.NAMES[svc]
            or labels.get("com.docker.compose.project") != g0.PROJECT
            or labels.get("com.docker.compose.service") != svc
            or data.get("Image") != image.get("Id")
            or state.get("Running") is not True
            or any(
                not isinstance(m, dict) or
                m.get("Destination") == "/var/run/docker.sock" or
                "/chonhac" in str(m.get("Source") or "")
                for m in mounts
            )
        ):
            raise g0.GateError("g0_execution_container_identity_invalid")
        allowed_networks = {g0.NETWORK}
        if svc == "runtime":
            allowed_networks.add(auth.G0_AUTH_NETWORKS["pcp"])
        if (not set(networks).issubset(allowed_networks)
                or g0.NETWORK not in networks):
            raise g0.GateError("g0_execution_container_network_invalid")
        variables = {}
        for item in (data.get("Config") or {}).get("Env") or []:
            if "=" in item:
                key, value = item.split("=", 1)
                variables[key] = value
        if not allow_partial:
            wanted = (allowed_networks if svc == "runtime"
                      and mode == "g0_fixture_run" else {g0.NETWORK})
            if set(networks) != wanted:
                raise g0.GateError("g0_execution_container_network_mismatch")
            if svc == "runtime" and variables.get(
                "PCP_RUNTIME_STARTUP_MODE"
            ) != mode:
                raise g0.GateError("g0_execution_runtime_mode_mismatch")
            if mode == "g0_fixture_run":
                if variables.get("PCP_G0_EXECUTION_ENABLED") != "owner-approved":
                    raise g0.GateError("g0_execution_not_scoped")
                if variables.get("PCP_G0_DELIVERY_ENABLED") or (
                    svc == "runtime" and variables.get("CODEX_HOME")
                    != "/home/coder/.codex-g0"
                ):
                    raise g0.GateError("g0_execution_unexpected_env")


def _require_absent_files() -> None:
    for name in (TOKENS_FILE, JOURNAL_FILE):
        file = _private(name)
        if file.exists() or file.is_symlink():
            raise g0.GateError("g0_execution_already_claimed_no_retry")


def preflight(repo: Path, fixture: Path, sha: str) -> dict:
    if not g0.SOURCE_SHA.fullmatch(sha):
        raise g0.GateError("g0_exact_activation_source_sha_required")
    env, _ = auth._context(repo, fixture, sha, require_prepared=True)
    auth._verify_rendered_tmpfs_mounts(repo, env)
    _validate_overlay()
    parity = forensics.inspect(repo, fixture, sha)
    if parity.get("status") != "PASS" or parity.get(
        "direct_evidence", {}
    ).get("direct_turn_reconciled") is not True:
        raise g0.GateError("g0_model_parity_not_reconciled")
    if not auth._check_config("pcp") or not auth._check_config("direct"):
        raise g0.GateError("g0_separate_device_auth_missing")
    net = g0.inspect("network", auth.G0_AUTH_NETWORKS["pcp"])
    if (net.get("Containers") or {}) or net.get("Internal") is not False:
        raise g0.GateError("g0_provider_network_not_quiescent")
    g0.require_headroom(repo)
    _require_absent_files()
    render_env = _compose_env(
        repo, fixture, internal="PRECHECK_NOT_A_TOKEN",
        runtime="PRECHECK_NOT_A_TOKEN",
    )
    _render(repo, render_env)
    return {
        "status": "PASS", "phase": "g0_execution_activation_preflight",
        "project": g0.PROJECT, "source_sha": sha,
        "model_parity_reconciled": True,
        "protected_owner_activation_pending": True,
        "model_calls": 0, "ready_to_dispatch_g0d_t01": False,
    }


def activate(repo: Path, fixture: Path, sha: str, owner_approved: bool) -> dict:
    if not owner_approved:
        raise g0.GateError("g0_protected_activation_requires_owner")
    preflight(repo, fixture, sha)
    # One-time durable claim first; preserve partial state without blind retries.
    _exclusive_create(_private(JOURNAL_FILE), {
        "state": "claimed", "source_sha": sha, "services": list(SERVICES),
        "ready_to_dispatch_g0d_t01": False,
    })
    _exclusive_create(_private(TOKENS_FILE), {
        "internal": secrets.token_urlsafe(48),
        "runtime": secrets.token_urlsafe(48),
    })
    tokens = auth.upgrader._read_json_secure(_private(TOKENS_FILE))
    env = _compose_env(
        repo, fixture, internal=tokens["internal"], runtime=tokens["runtime"],
    )
    _render(repo, env)
    for svc in SERVICES:
        g0.run(
            _compose(repo) + [
                "up", "-d", "--no-deps", "--no-build", "--pull", "never",
                "--force-recreate", svc,
            ],
            env=env, label="g0_execution_activate_" + svc, timeout=120,
        )
    _verify_containers("g0_fixture_run")
    auth.upgrader._private_write(_private(JOURNAL_FILE), {
        "state": "activated", "source_sha": sha, "services": list(SERVICES),
        "ready_to_dispatch_g0d_t01": False,
    })
    return {
        "status": "PASS", "phase": "g0_fixture_execution_activated",
        "source_sha": sha, "services": list(SERVICES),
        "model_calls": 0, "github_delivery_enabled": False,
        "job_dispatched": False, "ready_to_dispatch_g0d_t01": False,
    }


def status(repo: Path, fixture: Path, sha: str) -> dict:
    g0.require_local_docker_context()
    g0.require_exact_repo(repo, g0.EXPECTED_REPO, "main", sha)
    g0.require_exact_repo(
        fixture, g0.EXPECTED_FIXTURE, "benchmark/pcp", g0.SEED
    )
    _validate_overlay()
    state = auth.upgrader._read_json_secure(_private(JOURNAL_FILE))
    if state.get("source_sha") != sha:
        raise g0.GateError("g0_activation_source_changed")
    if state.get("state") != "activated":
        return {
            "status": "STOP", "phase": "g0_execution_activation_status",
            "reason": "g0_activation_incomplete_preserve_journal",
            "journal_state": state.get("state"),
            "model_calls": 0, "ready_to_dispatch_g0d_t01": False,
        }
    _verify_containers("g0_fixture_run")
    return {
        "status": "PASS", "phase": "g0_execution_activation_status",
        "project": g0.PROJECT, "source_sha": sha,
        "github_delivery_enabled": False, "job_dispatched_by_operator": False,
        "ready_to_dispatch_g0d_t01": False,
    }


def _verify_restore_targets() -> None:
    """An interrupted scoped up may leave one G0 service absent or stopped.

    Restore may recreate ONLY those two G0 names, and never an occupied
    unrelated name. Do not require both services running after a partial up.
    """
    for svc in SERVICES:
        name = g0.NAMES[svc]
        if not g0.exists("container", name):
            continue
        data = g0.inspect("container", name)
        labels = (data.get("Config") or {}).get("Labels") or {}
        networks = (data.get("NetworkSettings") or {}).get("Networks") or {}
        mounts = data.get("Mounts") or []
        image = g0.inspect("image", g0.resource_names(auth.DEPLOYED_SHA)[svc])
        if (
            data.get("Name") != "/" + name
            or labels.get("com.docker.compose.project") != g0.PROJECT
            or labels.get("com.docker.compose.service") != svc
            or data.get("Image") != image.get("Id")
            or g0.NETWORK not in networks
            or not set(networks).issubset({
                g0.NETWORK, auth.G0_AUTH_NETWORKS["pcp"],
            })
            or any(
                not isinstance(m, dict)
                or m.get("Destination") == "/var/run/docker.sock"
                or "/chonhac" in str(m.get("Source") or "")
                for m in mounts
            )
        ):
            raise g0.GateError("g0_partial_restore_target_not_owned")


def restore(repo: Path, fixture: Path, sha: str, owner_approved: bool) -> dict:
    if not owner_approved:
        raise g0.GateError("g0_protected_restore_requires_owner")
    g0.require_local_docker_context()
    g0.require_exact_repo(repo, g0.EXPECTED_REPO, "main", sha)
    g0.require_exact_repo(
        fixture, g0.EXPECTED_FIXTURE, "benchmark/pcp", g0.SEED
    )
    journal = auth.upgrader._read_json_secure(_private(JOURNAL_FILE))
    if (journal.get("source_sha") != sha
            or journal.get("services") != list(SERVICES)
            or journal.get("state") not in {"claimed", "activated"}):
        raise g0.GateError("g0_restoration_journal_not_exact")
    auth.upgrader._require_empty_g0_job_store()
    _verify_restore_targets()
    deployed, password, workspaces = g0.read_private_state(Path.home())
    if deployed != auth.DEPLOYED_SHA:
        raise g0.GateError("g0_restoration_image_source_changed")
    env = g0.compose_env(repo, fixture, workspaces, deployed, password)
    for svc in SERVICES:
        g0.run(
            g0.compose_args(repo) + [
                "up", "-d", "--no-deps", "--no-build", "--pull", "never",
                "--force-recreate", svc,
            ],
            env=env, label="g0_execution_restore_" + svc, timeout=120,
        )
    auth.upgrader._verify_g0_resources(deployed)
    auth.upgrader._private_write(_private(JOURNAL_FILE), {
        "state": "restored", "source_sha": sha, "services": list(SERVICES),
        "ready_to_dispatch_g0d_t01": False,
    })
    return {
        "status": "PASS", "phase": "g0_fixture_inspection_restored",
        "source_sha": sha, "model_calls": 0, "database_recreated": False,
        "ready_to_dispatch_g0d_t01": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "mode", choices=("preflight", "activate", "status", "restore"),
    )
    parser.add_argument("--expected-sha", required=True)
    parser.add_argument("--owner-approved-activate", action="store_true")
    args = parser.parse_args()
    repo = Path.home() / "personal-coding-platform-v1"
    fixture = Path.home() / "pcp-g0-fixtures/pcp-g0-drupal-fixture"
    try:
        if args.mode == "preflight":
            result = preflight(repo, fixture, args.expected_sha)
        elif args.mode == "activate":
            result = activate(
                repo, fixture, args.expected_sha, args.owner_approved_activate,
            )
        elif args.mode == "status":
            result = status(repo, fixture, args.expected_sha)
        else:
            result = restore(
                repo, fixture, args.expected_sha, args.owner_approved_activate,
            )
    except (g0.GateError, OSError, ValueError, TypeError, KeyError,
            yaml.YAMLError) as exc:
        result = {
            "status": "STOP", "phase": args.mode,
            "reason": str(exc) if isinstance(exc, g0.GateError)
            else "g0_execution_activation_validation_error",
            "do_not_retry_blindly": True, "ready_to_dispatch_g0d_t01": False,
        }
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result.get("status") == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
