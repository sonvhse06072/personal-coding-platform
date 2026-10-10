#!/usr/bin/env python3
"""Read-only PCP *container-specific* G0 source visibility / CLI probe.

Only the exact two PCP service containers are inspected. We do not ask Docker
to list, start, stop, restart or inspect unrelated projects. No Docker socket
is opened directly by this script; docker CLI may inspect PCP services only.
An optional 'docker exec' here runs bounded READ-ONLY printenv/codex/test
processes inside PCP (never a model inference or container lifecycle change).
This report never authorizes a job, DDEV or ProjectBaseline activation.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
from typing import Any

PCP_SITE = "personal-coding-platform"
EXECUTOR = "ddev-personal-coding-platform-ddev-executor"
RUNTIME = "ddev-personal-coding-platform-coding-runtime"
FIXTURE = "pcp-g0-drupal-fixture"
PROJECT_SUBPATH = ("pcp-g0-fixtures", FIXTURE)
SEED_SHA = "39ef13c25b24c4a1b43a720ae53419f479996ed2"
LOCK_SHA256 = "3a3d086be59571b43f05301ab099dc4d710a2ca1da0b25af60341d527f531f2b"
SOURCE_CODEX_PIN = "0.160.0"
FORMATS = {
    "name": "{{json .Name}}",
    "labels": "{{json .Config.Labels}}",
    "running": "{{json .State.Running}}",
    "mounts": "{{json .Mounts}}",
}


class SafeStop(Exception):
    """No unchecked command fallback or information-bearing error messages."""


def call(argv: list[str]) -> str:
    """Strict process allowlist. Errors never echo paths, stderr or env values."""
    safe = False
    if len(argv) == 5 and argv[:2] == ["docker", "inspect"]:
        safe = (
            argv[2] == "--format" and argv[3] in FORMATS.values()
            and argv[4] in (EXECUTOR, RUNTIME)
        )
    elif len(argv) == 5 and argv[:2] == ["docker", "exec"]:
        safe = (
            argv[2] == EXECUTOR and argv[3:] == ["printenv", "CODING_PROJECTS_ROOT"]
        ) or (
            argv[2] == RUNTIME and argv[3:] == ["codex", "--version"]
        )
    elif len(argv) == 6 and argv[:3] == ["docker", "exec", EXECUTOR]:
        # Do not accept an arbitrary absolute path, even for "test".
        # Only the single Owner-approved local fixture and its lock are in scope.
        only_fixture = Path.home() / PROJECT_SUBPATH[0] / PROJECT_SUBPATH[1]
        safe = argv[3] == "test" and (
            (argv[4] == "-d" and argv[5] == str(only_fixture))
            or (argv[4] == "-f" and argv[5] == str(only_fixture / "composer.lock"))
        )
    if not safe:
        raise SafeStop("unapproved_read_only_command")
    try:
        proc = subprocess.run(
            argv, text=True, capture_output=True, check=False, timeout=25,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise SafeStop("pcp_container_command_unavailable_or_timeout") from exc
    if proc.returncode:
        raise SafeStop("pcp_container_command_failed")
    return proc.stdout.strip()


def inspect_pcp_service(name: str) -> dict[str, Any]:
    """Request only Docker Name, Labels, Running and Mounts: NEVER Config.Env."""
    if name not in (EXECUTOR, RUNTIME):
        raise SafeStop("non_pcp_container_rejected")
    try:
        obj = {key: json.loads(call([
            "docker", "inspect", "--format", expression, name,
        ])) for key, expression in FORMATS.items()}
    except (ValueError, TypeError) as exc:
        raise SafeStop("pcp_inspect_metadata_unavailable") from exc
    if obj["name"] != "/" + name or obj["running"] is not True:
        raise SafeStop("pcp_container_identity_or_running_state_mismatch")
    labels = obj["labels"]
    if not isinstance(labels, dict) or not (
        labels.get("com.ddev.site-name") == PCP_SITE
        or labels.get("com.docker.compose.project") == "ddev-" + PCP_SITE
    ):
        raise SafeStop("pcp_container_ownership_labels_unverified")
    mounts = obj["mounts"]
    if not isinstance(mounts, list) or not all(isinstance(m, dict) for m in mounts):
        raise SafeStop("pcp_container_mount_metadata_invalid")
    return {"name": name, "mounts": mounts}


def registered_path(root: str) -> Path:
    """Validate the configured root without expanding shell or reading secrets."""
    if (
        not root or not root.startswith("/") or "\n" in root
        or "\0" in root or any(part in ("..", ".") for part in root.split("/"))
        or root in ("/", "/tmp", "/var/run", "/var/run/docker.sock")
    ):
        raise SafeStop("executor_configured_projects_root_invalid")
    return Path(root) / PROJECT_SUBPATH[0] / PROJECT_SUBPATH[1]


def assess_mounts(mounts: list[dict[str, Any]], root: str, fixture: Path) -> dict[str, bool]:
    """Compare live Executor mount destination against registered fixture path."""
    expected = registered_path(root)
    exact_project_root_bind = any(
        m.get("Type") == "bind" and m.get("Destination") == root
        for m in mounts
    )
    return {
        "fixture_path_matches_registered_project_root": expected == fixture,
        "executor_has_projects_root_bind": exact_project_root_bind,
        "eligible_for_read_only_fixture_visibility_check": (
            expected == fixture and exact_project_root_bind
        ),
    }


def version(raw: str) -> str | None:
    match = re.search(r"\b(\d+\.\d+\.\d+)\b", raw)
    return match.group(1) if match else None


def gib(value: int) -> float:
    return round(value / (1024**3), 2)


def resource_snapshot(fixture: Path) -> dict[str, Any]:
    """Read local host-wide Linux RAM and target filesystem free space only."""
    disk = shutil.disk_usage(fixture)
    mem_available_kib: int | None = None
    try:
        with open("/proc/meminfo", encoding="ascii") as handle:
            for line in handle:
                if line.startswith("MemAvailable:"):
                    mem_available_kib = int(line.split()[1])
                    break
    except (OSError, ValueError):
        pass
    return {
        "fixture_disk_free_gib": gib(disk.free),
        "wsl_mem_available_gib": (
            gib(mem_available_kib * 1024) if mem_available_kib is not None else None
        ),
        "logical_cpu_count": os.cpu_count(),
        "capacity_and_port_safety_not_proven": True,
    }


def local_fixture_proof(fixture: Path) -> dict[str, Any]:
    """No Git fetch or checkout; only hash the already verified fixture lock."""
    if fixture.is_symlink() or not fixture.is_dir():
        raise SafeStop("fixture_directory_missing_or_symlink")
    lock = fixture / "composer.lock"
    if lock.is_symlink() or not lock.is_file():
        raise SafeStop("fixture_lock_missing_or_symlink")
    if hashlib.sha256(lock.read_bytes()).hexdigest() != LOCK_SHA256:
        raise SafeStop("fixture_lock_checksum_mismatch")
    # Source SHA/clean checkout must be revalidated by the separate existing
    # read-only G0 WSL preflight; never assume that this lock proves Git HEAD.
    return {"fixture_lock_sha256_matches_frozen_seed": True}


def examine() -> dict[str, Any]:
    fixture = Path.home() / PROJECT_SUBPATH[0] / PROJECT_SUBPATH[1]
    proof = local_fixture_proof(fixture)
    report: dict[str, Any] = {
        "schema": "g0-pcp-wsl-runtime-and-mount-readonly-v1",
        "owner_fixture_lock": proof,
        "source_codex_pin": SOURCE_CODEX_PIN,
        "local_fixture_seed_expected": SEED_SHA,
        "mode": "read_only_pcp_specific_containers",
        "other_project_names_or_paths_exposed": False,
        "unrelated_container_inspection_performed": False,
        "docker_or_ddev_lifecycle_changed": False,
        "codex_inference_or_auth_performed": False,
        "pcp_runtime_deployed_source_unverified": True,
        "pcp_project_baseline_still_parked": True,
        "model_effort_and_provider_auth_unverified": True,
        "active_job_lease_unverified": True,
        "ddev_router_shared_side_effects_unverified": True,
        "port_collision_safety_unverified": True,
        "ready_to_dispatch_g0d_t01": False,
        "controlled_accepted_pairs": 0,
    }
    report["resources_observed_only"] = resource_snapshot(fixture)
    executor = inspect_pcp_service(EXECUTOR)
    runtime = inspect_pcp_service(RUNTIME)
    assert executor["name"] == EXECUTOR and runtime["name"] == RUNTIME
    try:
        root = call(["docker", "exec", EXECUTOR, "printenv", "CODING_PROJECTS_ROOT"])
    except SafeStop:
        report["executor_project_root_observed"] = False
        report["blockers"] = ["executor_projects_root_not_readable"]
        return report
    report["executor_project_root_observed"] = True
    visibility = assess_mounts(executor["mounts"], root, fixture)
    report["executor_mount_proof"] = visibility
    blockers = []
    if not visibility["fixture_path_matches_registered_project_root"]:
        blockers.append("fixture_checkout_outside_configured_project_root")
    if not visibility["executor_has_projects_root_bind"]:
        blockers.append("executor_projects_root_bind_unverified")
    if visibility["eligible_for_read_only_fixture_visibility_check"]:
        try:
            call(["docker", "exec", EXECUTOR, "test", "-d", str(fixture)])
            call(["docker", "exec", EXECUTOR, "test", "-f", str(fixture / "composer.lock")])
        except SafeStop:
            report["executor_fixture_visible"] = False
            blockers.append("executor_cannot_read_fixture_checkout")
        else:
            report["executor_fixture_visible"] = True
    else:
        report["executor_fixture_visible"] = False

    try:
        observed = call(["docker", "exec", RUNTIME, "codex", "--version"])
        actual = version(observed)
    except SafeStop:
        actual = None
    report["pcp_runtime_codex_cli_version"] = actual
    if actual is None:
        blockers.append("runtime_codex_cli_version_unavailable")
    elif actual != SOURCE_CODEX_PIN:
        blockers.append("runtime_codex_cli_differs_from_source_pin")
    # The host CLI may be 0.162.0; do not upgrade/downgrade it. If
    # Runtime is 0.160.0, normalize future direct arm with a PRIVATE binary.
    report["host_global_codex_unmodified"] = True
    report["blockers"] = blockers
    return report


def main() -> int:
    try:
        result = examine()
    except (SafeStop, OSError, ValueError, AssertionError) as exc:
        result = {
            "schema": "g0-pcp-wsl-runtime-and-mount-readonly-v1",
            "status": "STOPPED",
            "reason": (
                str(exc) if isinstance(exc, SafeStop) else "probe_unknown_failure"
            ),
            "ready_to_dispatch_g0d_t01": False,
            "docker_or_ddev_lifecycle_changed": False,
            "unrelated_container_inspection_performed": False,
        }
        print(json.dumps(result, indent=2, sort_keys=True))
        return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
