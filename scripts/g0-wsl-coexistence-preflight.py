#!/usr/bin/env python3
"""Read-only, best-effort audit of PCP fixture coexistence on the Owner's WSL.

Never starts/stops Docker/DDEV, fetches repositories, reads another project's
files, invokes a model, or modifies the local PCP/fixture worktrees. This report
is diagnostic evidence ONLY, not an execution-authorization or security proof.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import subprocess
import sys
from typing import Any

FIXTURE_NAME = "pcp-g0-drupal-fixture"
FIXTURE_SEED = "39ef13c25b24c4a1b43a720ae53419f479996ed2"
RUNTIME_PIN = "0.160.0"
STOPPED = frozenset({"stopped", "exited"})


def parse_ddev_json(raw: str) -> list[dict[str, Any]]:
    """Read actual DDEV 1.25.x -j envelopes; reject ambiguous/malformed data."""
    raw = raw.strip()
    if not raw:
        raise ValueError("ddev_registry_empty_response")
    try:
        single = json.loads(raw)
    except json.JSONDecodeError:
        try:
            envelopes = [json.loads(row) for row in raw.splitlines() if row.strip()]
        except json.JSONDecodeError as exc:
            raise ValueError("ddev_registry_invalid_json") from exc
    else:
        envelopes = [single]
    if not envelopes or any(not isinstance(item, dict) for item in envelopes):
        raise ValueError("ddev_registry_invalid_envelope")

    results = []
    for item in envelopes:
        if str(item.get("level", "")).lower() in {"error", "fatal"}:
            raise ValueError("ddev_registry_error_envelope")
        if "raw" not in item:
            continue  # Non-result informational envelope, not evidence.
        data = item["raw"]
        if isinstance(data, dict) and isinstance(data.get("projects"), list):
            data = data["projects"]  # Legacy representation.
        if not isinstance(data, list):
            raise ValueError("ddev_registry_unknown_shape")
        results.append(data)
    if len(results) != 1:
        raise ValueError("ddev_registry_ambiguous_results")

    seen: set[str] = set()
    for project in results[0]:
        if not isinstance(project, dict):
            raise ValueError("ddev_registry_invalid_project")
        name = project.get("name")
        status = project.get("status")
        if not isinstance(name, str) or not name.strip():
            raise ValueError("ddev_registry_missing_project_name")
        if not isinstance(status, str) or not status.strip():
            raise ValueError("ddev_registry_missing_project_status")
        normalized = name.strip().casefold()
        if normalized in seen:
            raise ValueError("ddev_registry_duplicate_project_name")
        seen.add(normalized)
    return results[0]


def summarize_registry(projects: list[dict[str, Any]]) -> dict[str, Any]:
    """Do not expose the names, locations, URLs or metadata of other projects."""
    registered = {p["name"].strip().casefold() for p in projects}
    active_count = sum(
        p["status"].strip().lower() not in STOPPED and
        p["name"].strip().casefold() != "router"
        for p in projects
    )
    return {
        "registered_project_count": len(projects),
        "other_active_project_count": active_count,
        "fixture_project_name_collision": FIXTURE_NAME.casefold() in registered,
        # Normal DDEV multi-project coexistence is not blocked just because an
        # unrelated project is running. Start/stop is separately authorized.
        "unrelated_active_projects_are_not_automatic_collision": True,
        "shared_router_indirect_impact_not_ruled_out": True,
    }


def read_command(argv: list[str], *, cwd: Path | None = None) -> tuple[str | None, str | None]:
    """Only allow these narrowly read-only probes, no shell or env echo."""
    safe = (
        argv in (["ddev", "list", "-j"], ["ddev", "--version"], ["codex", "--version"])
        or (
            len(argv) == 5
            and argv[0] == "git" and argv[1] == "-C"
            and argv[3:] in (
                ["rev-parse", "HEAD"],
                ["status", "--porcelain=v1"],
            )
        )
    )
    if not safe:
        raise ValueError("unsupported_read_only_command")
    try:
        p = subprocess.run(
            argv, cwd=str(cwd) if cwd else None, timeout=20,
            text=True, capture_output=True, check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None, "command_unavailable_or_timeout"
    if p.returncode:
        # Do not echo stderr: it may contain host/private paths.
        return None, "command_failed"
    return p.stdout.strip(), None


def git_summary(path: Path) -> dict[str, Any]:
    if path.is_symlink():
        return {"exists": True, "git_readable": False, "blocker": "symlink_path"}
    if not path.is_dir():
        return {"exists": False, "git_readable": False, "blocker": "not_present"}
    head, err1 = read_command(["git", "-C", str(path), "rev-parse", "HEAD"])
    dirty, err2 = read_command(["git", "-C", str(path), "status", "--porcelain=v1"])
    if err1 or err2 or not re.fullmatch(r"[a-f0-9]{40}", head or ""):
        return {"exists": True, "git_readable": False, "blocker": "git_probe_failed"}
    return {
        "exists": True, "git_readable": True, "head_sha": head,
        "clean": dirty == "",
    }


def evaluate(
    *, ddev_json: str, local_pcp: dict[str, Any], local_fixture: dict[str, Any],
    host_cli: str | None, ddev_version: str | None,
) -> dict[str, Any]:
    projects = parse_ddev_json(ddev_json)
    registry = summarize_registry(projects)
    reasons: list[str] = []
    if registry["fixture_project_name_collision"]:
        reasons.append("fixture_ddev_name_occupied_check_ownership")
    if not local_pcp.get("git_readable", False):
        reasons.append("pcp_checkout_not_observed")
    if not local_fixture.get("git_readable", False):
        reasons.append("fixture_source_not_observed")
    elif local_fixture.get("head_sha") != FIXTURE_SEED:
        reasons.append("fixture_local_head_not_frozen_seed")
    if host_cli is None:
        reasons.append("host_codex_cli_unavailable")
    elif not re.search(r"(?<![0-9])" + re.escape(RUNTIME_PIN) + r"(?![0-9])", host_cli):
        reasons.append("host_cli_differs_from_runtime_source_pin")
    if ddev_version is None:
        reasons.append("ddev_version_unavailable")

    return {
        "schema_version": 1,
        "mode": "read_only_shared_wsl_coexistence_inventory",
        "fixture_source_seed": FIXTURE_SEED,
        "runtime_source_pin": RUNTIME_PIN,
        "host_codex_cli_version": (
            re.search(r"\b\d+\.\d+\.\d+\b", host_cli or "").group(0)
            if re.search(r"\b\d+\.\d+\.\d+\b", host_cli or "") else None
        ),
        "observed_ddev_version": (
            re.search(r"\d+\.\d+\.\d+", ddev_version or "").group(0)
            if re.search(r"\d+\.\d+\.\d+", ddev_version or "") else None
        ),
        "pcp_source": local_pcp,
        "fixture_source": local_fixture,
        "ddev_registry": registry,
        "blockers": reasons,
        "actual_runtime_binary_unverified": True,
        "model_and_effort_unverified": True,
        "lease_unverified": True,
        "port_resource_headroom_unverified": True,
        "shared_docker_router_still_used": True,
        "deployment_or_ddev_execution_performed": False,
        "ready_to_dispatch_g0d_t01": False,
        "controlled_comparable_pairs": 0,
    }


def main() -> int:
    home = Path.home()
    pcp = home / "personal-coding-platform-v1"
    fixture = home / "pcp-g0-fixtures" / FIXTURE_NAME
    # Read-only commands. Registry includes other project metadata internally,
    # but the report never prints other projects' names, paths or URLs.
    result, registry_error = read_command(["ddev", "list", "-j"])
    if registry_error or not result:
        print(json.dumps({
            "mode": "read_only_shared_wsl_coexistence_inventory",
            "status": "unknown",
            "blocker": "ddev_registry_cannot_be_verified",
            "ready_to_dispatch_g0d_t01": False,
        }, indent=2))
        return 2
    codex, _ = read_command(["codex", "--version"])
    ddev_version, _ = read_command(["ddev", "--version"])
    try:
        report = evaluate(
            ddev_json=result, local_pcp=git_summary(pcp),
            local_fixture=git_summary(fixture),
            host_cli=codex, ddev_version=ddev_version,
        )
    except (ValueError, KeyError, TypeError):
        print(json.dumps({
            "mode": "read_only_shared_wsl_coexistence_inventory",
            "status": "unknown", "blocker": "ddev_registry_invalid_or_ambiguous",
            "ready_to_dispatch_g0d_t01": False,
        }, indent=2))
        return 2
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
