#!/usr/bin/env python3
"""Guarded Owner-only G0 *inspection source* upgrade; never enables WorkOrders.

preflight --expected-sha SHA: only read PCP/G0 source, Docker metadata and CLI.
upgrade   --expected-sha SHA: rebuild G0 Runtime/Executor overlays OFFLINE, and
                            recreate ONLY those two G0 containers, in inspect.
status:                     read currently deployed G0 source and health.
rollback:                   restore exact previous G0 Runtime/Executor images.

This never activates Codex, provider egress, GitHub delivery, PM Bridge, DDEV,
legacy PCP Runtime or Chợ Nhạc. Stop on a mismatch; never retry blindly.
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
import tempfile

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/g0-inspection-operator.py"
SPEC = importlib.util.spec_from_file_location("g0_inspection_operator", SCRIPT)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("G0 inspection operator unavailable")
g0 = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(g0)

OLD_SOURCE = "e4cd2526fe97792b92ebf43460c8dbe8ba74bcf2"
TARGET_SERVICES = ("executor", "runtime")
JOURNAL = "source-upgrade.json"


def _safe_report(**items: object) -> dict[str, object]:
    return {
        "project": g0.PROJECT,
        "status": "PASS",
        "current_mode": "inspect",
        "ready_to_dispatch_g0d_t01": False,
        "model_calls": 0,
        **items,
    }


def _private_root() -> Path:
    return Path.home() / ".pcp-g0d01"


def _read_json_secure(path: Path) -> dict:
    root = _private_root()
    if (root.is_symlink() or not root.is_dir()
            or root.stat().st_mode & 0o077
            or path.parent != root or path.is_symlink() or not path.is_file()):
        raise g0.GateError("g0_private_journal_invalid")
    if path.stat().st_mode & 0o077:
        raise g0.GateError("g0_private_journal_permissions_unsafe")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise g0.GateError("g0_private_journal_unreadable") from exc
    if not isinstance(value, dict):
        raise g0.GateError("g0_private_journal_invalid")
    return value


def _private_write(path: Path, value: dict) -> None:
    root = _private_root()
    if root.is_symlink() or root.stat().st_mode & 0o077 or path.parent != root:
        raise g0.GateError("g0_private_root_unsafe")
    if path.exists() and path.is_symlink():
        raise g0.GateError("g0_private_symlink_denied")
    fd, name = tempfile.mkstemp(prefix=".g0-write-", dir=str(root))
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as out:
            json.dump(value, out, sort_keys=True)
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def _base_source_validation(repo: Path, fixture: Path, expected: str) -> None:
    if not g0.SOURCE_SHA.fullmatch(expected):
        raise g0.GateError("exact_source_sha_required")
    g0.require_local_docker_context()
    g0.require_exact_repo(repo, g0.EXPECTED_REPO, "main", expected)
    g0.require_exact_repo(fixture, g0.EXPECTED_FIXTURE, "benchmark/pcp", g0.SEED)
    g0.guard_source(repo, fixture)


EXPECTED_MOUNTS = {
    "db": {
        "/var/lib/postgresql/data": ("volume", False),
    },
    "router": {
        "/g0/config/models.yml": ("bind", True),
        "/g0/config/routing-policy.yml": ("bind", True),
        "/g0/config/projects.yml": ("bind", True),
    },
    "executor": {
        "/g0/config/projects.yml": ("bind", True),
        "/g0/sources/pcp-g0-fixtures/pcp-g0-drupal-fixture": ("bind", True),
        "/g0/workspaces": ("bind", False),
    },
    "runtime": {
        "/g0/config/projects.yml": ("bind", True),
        "/g0/config/project-baselines.yml": ("bind", True),
        "/g0/config/models.yml": ("bind", True),
        "/g0/workspaces": ("bind", False),
    },
}


def _verify_g0_resources(deployed: str) -> None:
    """Read only exact G0 resources; fail if any scope/ownership changed."""
    if not g0.SOURCE_SHA.fullmatch(deployed):
        raise g0.GateError("deployed_source_not_exact")
    for svc in g0.G0_SERVICES:
        name = g0.NAMES[svc]
        obj = g0.inspect("container", name)
        labels = (obj.get("Config") or {}).get("Labels") or {}
        if (labels.get("com.docker.compose.project") != g0.PROJECT or
                labels.get("com.docker.compose.service") != svc or
                (obj.get("State") or {}).get("Running") is not True):
            raise g0.GateError("g0_container_ownership_or_state_changed")
        network_names = set((obj.get("NetworkSettings") or {}).get("Networks") or {})
        if network_names != {g0.NETWORK}:
            raise g0.GateError("g0_network_scope_changed")
        host = obj.get("HostConfig") or {}
        if host.get("Privileged") is not False or host.get("PortBindings"):
            raise g0.GateError("g0_container_host_privilege_changed")
        actual = {}
        for mount in (obj.get("Mounts") or []):
            dest = mount.get("Destination")
            if not isinstance(dest, str) or dest in actual:
                raise g0.GateError("g0_mount_identity_ambiguous")
            actual[dest] = (
                mount.get("Type"), mount.get("RW") is False,
            )
            if dest == "/var/run/docker.sock":
                raise g0.GateError("g0_host_docker_socket_exposed")
            if (svc == "db" and dest == "/var/lib/postgresql/data"
                    and mount.get("Name") != g0.DATA_VOLUME):
                raise g0.GateError("g0_database_mount_name_mismatch")
        if actual != EXPECTED_MOUNTS[svc]:
            raise g0.GateError("g0_mount_scope_changed")
        config_env = (obj.get("Config") or {}).get("Env") or []
        items = dict(s.split("=", 1) for s in config_env if "=" in s)
        if svc == "runtime":
            if items.get("PCP_RUNTIME_STARTUP_MODE") != "inspect":
                raise g0.GateError("g0_runtime_mode_not_inspect")
        if svc == "executor":
            if items.get("PCP_EXECUTOR_PROJECT_SCOPE") != "pcp-g0-drupal-fixture":
                raise g0.GateError("g0_executor_scope_mismatch")
        if svc in TARGET_SERVICES:
            for forbidden in (
                "PCP_G0_EXECUTION_ENABLED", "PCP_G0_DELIVERY_ENABLED",
                "GITHUB_DELIVERY_TOKEN", "OPENAI_API_KEY", "ANTIGRAVITY_BRIDGE_TOKEN",
                "RUNTIME_API_TOKEN", "PLATFORM_INTERNAL_TOKEN",
            ):
                if items.get(forbidden):
                    raise g0.GateError("g0_live_credentials_or_capability_unexpected")
            tag = g0.resource_names(deployed)[svc]
            image = g0.inspect("image", tag)
            props = (image.get("Config") or {}).get("Labels") or {}
            if (obj.get("Image") != image.get("Id") or
                    props.get("org.opencontainers.image.revision") != deployed or
                    props.get("org.opencontainers.image.pcp.g0") != "inspection-only"):
                raise g0.GateError("g0_running_image_revision_mismatch")
    if g0.inspect("network", g0.NETWORK).get("Internal") is not True:
        raise g0.GateError("g0_network_no_longer_private")
    vol = g0.inspect("volume", g0.DATA_VOLUME)
    if (vol.get("Labels") or {}).get("com.docker.compose.project") != g0.PROJECT:
        raise g0.GateError("g0_database_volume_owner_changed")


def _require_empty_g0_job_store() -> None:
    """No job from this pilot may be interrupted by a source-only upgrade."""
    db = g0.NAMES["db"]
    cmd = ["docker", "exec", db, "psql", "-X", "-q", "-t", "-A",
           "-v", "ON_ERROR_STOP=1", "-U", "g0", "-d", "g0", "-c"]
    for table in (
        "cp_jobs", "cp_project_leases", "cp_execution_plans",
        "cp_plan_orchestrations", "cp_plan_work_orders",
    ):
        exists = g0.run(
            cmd + [f"SELECT to_regclass('public.{table}')"],
            label="g0_readonly_table_exists_" + table, timeout=20,
        ).strip()
        if not exists:
            continue
        count = g0.run(
            cmd + [f"SET default_transaction_read_only=on; SELECT COUNT(*) FROM {table}"],
            label="g0_readonly_table_count_" + table, timeout=25,
        ).splitlines()
        if not count or not count[-1].strip().isdigit() or int(count[-1]) != 0:
            raise g0.GateError("g0_durable_work_not_empty")


def _codex_cli_version() -> str:
    output = g0.run(
        ["docker", "exec", g0.NAMES["runtime"], "codex", "--version"],
        label="g0_cli_version", timeout=20,
    )
    match = re.fullmatch(r"codex-cli (\d+\.\d+\.\d+)", output)
    if match is None:
        raise g0.GateError("g0_codex_cli_version_unverified")
    return match.group(1)


def _owner_state() -> tuple[str, str, Path]:
    return g0.read_private_state(Path.home())


def preflight(repo: Path, fixture: Path, target: str) -> dict[str, object]:
    _base_source_validation(repo, fixture, target)
    deployed, _, _ = _owner_state()
    if deployed != OLD_SOURCE or target == deployed:
        raise g0.GateError("g0_source_upgrade_identity_unexpected")
    if (_private_root() / JOURNAL).exists():
        raise g0.GateError("g0_upgrade_journal_already_exists")
    _verify_g0_resources(deployed)
    _require_empty_g0_job_store()
    if not g0.exists("image", "postgres:17"):
        raise g0.GateError("g0_postgres_image_not_cached")
    for svc in TARGET_SERVICES:
        new_tag = g0.resource_names(target)[svc]
        if g0.exists("image", new_tag):
            raise g0.GateError("g0_new_image_tag_already_exists")
        base = g0.inspect("image", g0.BASE_IMAGES[svc])
        if not re.fullmatch(r"sha256:[0-9a-f]{64}", str(base.get("Id") or "")):
            raise g0.GateError("g0_cached_base_image_invalid")
    old_version = _codex_cli_version()
    return _safe_report(
        phase="preflight_inspection_source_upgrade",
        previous_source_sha=deployed,
        target_source_sha=target,
        installed_g0_codex_cli_version=old_version,
        source_upgrade_available=True,
        provider_credentials_activated=False,
        external_egress_activated=False,
        git_delivery_activated=False,
    )


def _build_target_images(repo: Path, sha: str) -> None:
    for svc in TARGET_SERVICES:
        base_id = g0.inspect("image", g0.BASE_IMAGES[svc])["Id"]
        alias = f"pcp-g0d01-base-{svc}:{base_id[7:19]}"
        if g0.exists("image", alias):
            if g0.inspect("image", alias)["Id"] != base_id:
                raise g0.GateError("g0_base_alias_identity_conflict")
        else:
            g0.run(["docker", "tag", base_id, alias],
                   label="g0_upgrade_base_alias_" + svc)
        source = (
            f"FROM {alias}\n"
            "COPY app /app/app\n"
            f'LABEL org.opencontainers.image.revision="{sha}"\n'
            'LABEL org.opencontainers.image.pcp.g0="inspection-only"\n'
        )
        tag = g0.resource_names(sha)[svc]
        g0.run([
            "docker", "build", "--pull=false", "--network=none",
            "-f", "-", "-t", tag, str(repo / g0.SERVICE_CONTEXTS[svc]),
        ], stdin=source, timeout=180, label="g0_upgrade_build_" + svc)
        meta = (g0.inspect("image", tag).get("Config") or {}).get("Labels") or {}
        if (meta.get("org.opencontainers.image.revision") != sha or
                meta.get("org.opencontainers.image.pcp.g0") != "inspection-only"):
            raise g0.GateError("g0_upgrade_image_provenance_failed")


def _compose_environment(repo: Path, fixture: Path, sha: str,
                         password: str, workspace: Path) -> dict[str, str]:
    env = g0.compose_env(repo, fixture, workspace, sha, password)
    # This upgrade cannot recreate the unchanged Router or the database.
    env["PCP_G0_ROUTER_IMAGE"] = g0.resource_names(OLD_SOURCE)["router"]
    return env


def _up_one(repo: Path, env: dict[str, str], service: str) -> None:
    if service not in TARGET_SERVICES:
        raise g0.GateError("g0_upgrade_service_not_in_scope")
    g0.run(
        g0.compose_args(repo) +
        ["up", "-d", "--no-deps", "--no-build", "--pull", "never",
         "--force-recreate", service],
        env=env, label="g0_only_upgrade_" + service, timeout=110,
    )


def upgrade(repo: Path, fixture: Path, sha: str) -> dict[str, object]:
    report = preflight(repo, fixture, sha)
    previous, password, workspace = _owner_state()
    journal = _private_root() / JOURNAL
    _private_write(journal, {
        "old_sha": previous, "target_sha": sha, "state": "started",
    })
    _build_target_images(repo, sha)
    _base_source_validation(repo, fixture, sha)
    _verify_g0_resources(previous)
    _require_empty_g0_job_store()
    env = _compose_environment(repo, fixture, sha, password, workspace)
    g0.run(g0.compose_args(repo) + ["config", "--quiet"],
           env=env, label="g0_upgrade_compose_config")
    for svc in TARGET_SERVICES:
        _up_one(repo, env, svc)
    _verify_g0_resources(sha)
    # Use the existing authoritative negative HTTP probes; no job dispatch.
    g0.verify_inspection(repo, env)
    version = _codex_cli_version()
    _private_write(_private_root() / "owner-state.json", {
        "source_sha": sha, "password": password,
    })
    _private_write(journal, {
        "old_sha": previous, "target_sha": sha, "state": "complete",
    })
    return _safe_report(
        phase="inspection_source_upgrade",
        previous_source_sha=previous, target_source_sha=sha,
        installed_g0_codex_cli_version=version,
        upgraded_services=list(TARGET_SERVICES),
        database_recreated=False, router_recreated=False,
        credentials_added=False, external_egress_added=False,
        next_gate="separate_provider_and_delivery_authorization",
    )


def rollback(repo: Path, fixture: Path) -> dict[str, object]:
    journal = _read_json_secure(_private_root() / JOURNAL)
    old, new = journal.get("old_sha"), journal.get("target_sha")
    if (old != OLD_SOURCE or not isinstance(new, str)
            or not g0.SOURCE_SHA.fullmatch(new)
            or journal.get("state") not in {"started", "complete"}):
        raise g0.GateError("g0_upgrade_rollback_journal_untrusted")
    g0.require_local_docker_context()
    _, password, workspace = _owner_state()
    if (g0.inspect("network", g0.NETWORK).get("Internal") is not True
            or (g0.inspect("volume", g0.DATA_VOLUME).get("Labels") or {})
            .get("com.docker.compose.project") != g0.PROJECT):
        raise g0.GateError("g0_rollback_network_or_volume_not_owned")
    _require_empty_g0_job_store()
    # A partial failure may have upgraded, stopped, or removed one target.
    # Absence is allowed only for these two exact names; Compose recreates it.
    for svc in TARGET_SERVICES:
        if not g0.exists("container", g0.NAMES[svc]):
            continue
        obj = g0.inspect("container", g0.NAMES[svc])
        labels = (obj.get("Config") or {}).get("Labels") or {}
        if (labels.get("com.docker.compose.project") != g0.PROJECT
                or labels.get("com.docker.compose.service") != svc):
            raise g0.GateError("g0_rollback_container_not_owned")
        state = (obj.get("State") or {}).get("Status")
        if state not in {"running", "exited", "created"}:
            raise g0.GateError("g0_rollback_container_state_unexpected")
        recognized = False
        for candidate in (old, new):
            tag = g0.resource_names(candidate)[svc]
            if g0.exists("image", tag) and (
                obj.get("Image") == g0.inspect("image", tag).get("Id")
            ):
                recognized = True
                break
        if not recognized:
            raise g0.GateError("g0_rollback_container_image_unknown")
    env = _compose_environment(repo, fixture, old, password, workspace)
    for svc in TARGET_SERVICES:
        _up_one(repo, env, svc)
    _verify_g0_resources(old)
    g0.verify_inspection(repo, env)
    _private_write(_private_root() / "owner-state.json", {
        "source_sha": old, "password": password,
    })
    _private_write(journal, {
        "old_sha": old, "target_sha": new, "state": "rolled_back",
    })
    return _safe_report(phase="inspection_source_rollback",
                        source_sha=old, original_db_preserved=True)


def status(repo: Path, fixture: Path) -> dict[str, object]:
    g0.require_local_docker_context()
    current, password, workspace = _owner_state()
    _verify_g0_resources(current)
    _require_empty_g0_job_store()
    env = _compose_environment(repo, fixture, current, password, workspace)
    g0.verify_inspection(repo, env)
    return _safe_report(
        phase="inspection_source_status", deployed_source_sha=current,
        installed_g0_codex_cli_version=_codex_cli_version(),
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("preflight", "upgrade", "status", "rollback"))
    parser.add_argument("--expected-sha", default="")
    args = parser.parse_args()
    repo = Path.home() / "personal-coding-platform-v1"
    fixture = Path.home() / "pcp-g0-fixtures/pcp-g0-drupal-fixture"
    try:
        if args.mode == "preflight":
            result = preflight(repo, fixture, args.expected_sha)
        elif args.mode == "upgrade":
            result = upgrade(repo, fixture, args.expected_sha)
        elif args.mode == "status":
            result = status(repo, fixture)
        else:
            result = rollback(repo, fixture)
    except (g0.GateError, OSError, KeyError, TypeError, ValueError) as exc:
        reason = (str(exc) if isinstance(exc, g0.GateError)
                  else "unexpected_local_identity_or_runtime_error")
        print(json.dumps({
            "status": "STOP", "phase": args.mode, "reason": reason,
            "do_not_retry_blindly": True,
            "ready_to_dispatch_g0d_t01": False,
        }, sort_keys=True))
        return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
