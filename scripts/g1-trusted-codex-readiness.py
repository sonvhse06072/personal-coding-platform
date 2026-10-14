#!/usr/bin/env python3
"""One-pass READ-ONLY WSL admission for a *new* G1 disposable smoke fixture.

This does not clone, start Docker/DDEV, allocate tokens, dispatch jobs or call a
model. It never inspects another project's worktree, credentials or secrets.
Use only after synchronizing a CLEAN PCP source checkout to its reviewed main.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import subprocess
from typing import Any, Callable

SOURCE_ROOT = Path(__file__).resolve().parents[1]
SMOKE_ROOT_NAME = ".pcp-g1-smoke"
DDEV_NAME = "pcp-g1-codex-smoke"
WEB_CONTAINER = "ddev-" + DDEV_NAME + "-web"
FIXTURE_REF = "benchmark/g1-codex-smoke-v1"
FIXTURE_SHA = "d4f4a56713e95f85ecc08c02bb43a5b5105a86a3"
SHA = re.compile(r"[a-f0-9]{40}\Z")
VERSION = re.compile(r"\b[0-9]+\.[0-9]+\.[0-9]+\b")
GLOBAL_CONFIG = ".ddev/global_config.yaml"


class Stop(RuntimeError):
    """Bounded reason code and optionally safe fixture-only evidence."""

    def __init__(self, reason: str, **facts: Any) -> None:
        super().__init__(reason)
        self.facts = facts


def _run(argv: list[str]) -> subprocess.CompletedProcess[str]:
    """No shell, no mutating subcommands, no untrusted argv from the CLI."""
    try:
        return subprocess.run(
            argv, capture_output=True, text=True, timeout=20,
            check=False, stdin=subprocess.DEVNULL,
            env={**os.environ, "GIT_OPTIONAL_LOCKS": "0"},
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise Stop("readonly_probe_unavailable_or_timed_out") from exc


def _ok(
    runner: Callable[[list[str]], subprocess.CompletedProcess[str]],
    argv: list[str],
    code: str,
) -> str:
    result = runner(argv)
    if result.returncode:
        raise Stop(code)
    return str(result.stdout or "").strip()


def _docker_endpoint(
    runner: Callable[[list[str]], subprocess.CompletedProcess[str]],
) -> None:
    output = _ok(runner, ["docker", "context", "inspect"], "docker_context_unavailable")
    try:
        parsed = json.loads(output)
        endpoint = parsed[0]["Endpoints"]["docker"]["Host"]
        if not isinstance(parsed, list) or len(parsed) != 1:
            raise ValueError()
    except (ValueError, TypeError, KeyError, IndexError) as exc:
        raise Stop("docker_context_invalid") from exc
    if not isinstance(endpoint, str) or not endpoint.startswith("unix://"):
        raise Stop("docker_context_not_local_unix")
    override = os.getenv("DOCKER_HOST", "").strip()
    if override and override != endpoint:
        raise Stop("remote_docker_host_override")
    docker_data = _ok(
        runner, ["docker", "info", "--format", "{{json .}}"],
        "docker_engine_unreachable",
    )
    try:
        info = json.loads(docker_data)
        if not isinstance(info, dict) or not info.get("ServerVersion"):
            raise ValueError()
    except (ValueError, TypeError) as exc:
        raise Stop("docker_engine_metadata_invalid") from exc
    if "docker desktop" not in str(info.get("OperatingSystem", "")).lower():
        raise Stop("expected_docker_desktop_engine_missing")


def _ddev_projects(raw: str) -> list[dict[str, Any]]:
    """Recognize DDEV -j envelopes without displaying unrelated project data."""
    try:
        values = [json.loads(raw)]
    except json.JSONDecodeError:
        try:
            values = [json.loads(line) for line in raw.splitlines() if line.strip()]
        except json.JSONDecodeError as exc:
            raise Stop("ddev_registry_invalid_json") from exc
    found: list[list[dict[str, Any]]] = []
    for value in values:
        if not isinstance(value, dict):
            raise Stop("ddev_registry_invalid")
        if str(value.get("level") or "").lower() in ("error", "fatal"):
            raise Stop("ddev_registry_error")
        if "raw" not in value:
            continue
        projects = value["raw"]
        if isinstance(projects, dict):
            projects = projects.get("projects")
        if not isinstance(projects, list):
            raise Stop("ddev_registry_unknown_shape")
        found.append(projects)
    if len(found) != 1 or any(
        not isinstance(item, dict)
        or not isinstance(item.get("name"), str)
        or not isinstance(item.get("status"), str)
        for item in found[0]
    ):
        raise Stop("ddev_registry_ambiguous_or_invalid")
    names = [item["name"].strip().casefold() for item in found[0]]
    if any(not name for name in names) or len(names) != len(set(names)):
        raise Stop("ddev_registry_duplicate_or_empty_name")
    return found[0]


def _docker_inventory_rows(
    runner: Callable[[list[str]], subprocess.CompletedProcess[str]],
    kind: str,
    argv: list[str],
) -> list[dict[str, Any]]:
    """Use successful Docker list results, never localized inspect error text."""
    raw = _ok(runner, argv, f"docker_{kind}_inventory_unavailable")
    rows: list[dict[str, Any]] = []
    for line in raw.splitlines():
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise Stop(f"docker_{kind}_inventory_invalid") from exc
        name = row.get("Names", row.get("Name")) if isinstance(row, dict) else None
        if not isinstance(name, str) or not isinstance(row.get("Labels", ""), str):
            raise Stop(f"docker_{kind}_inventory_invalid")
        rows.append(row)
    if kind == "network" and not rows:
        # A functioning local Docker engine normally lists bridge/host/none.
        raise Stop("docker_network_inventory_empty")
    return rows


def _fixture_inventory(
    runner: Callable[[list[str]], subprocess.CompletedProcess[str]],
) -> dict[str, Any]:
    """Check stopped/running containers plus labeled/renamed fixture resources."""
    commands = {
        "container": ["docker", "container", "ls", "--all", "--format", "{{json .}}"],
        "volume": ["docker", "volume", "ls", "--format", "{{json .}}"],
        "network": ["docker", "network", "ls", "--format", "{{json .}}"],
    }
    counts: dict[str, int] = {}
    states: set[str] = set()
    for kind, argv in commands.items():
        rows = _docker_inventory_rows(runner, kind, argv)
        matched = [
            row for row in rows
            if any(
                marker in (row.get("Names", row.get("Name", "")) + " " + row.get("Labels", "")).lower()
                for marker in (DDEV_NAME, "pcp-benchmark-g1-smoke")
            )
        ]
        counts[kind] = len(matched)
        if kind == "container":
            for row in matched:
                state = row.get("State", "")
                states.add(
                    state.lower() if isinstance(state, str) and state.lower() in {
                        "running", "exited", "created", "paused", "restarting", "dead", "removing",
                    } else "unknown"
                )

    facts = {
        "fixture_container_count": counts["container"],
        "fixture_container_states": sorted(states),
        "fixture_volume_count": counts["volume"],
        "fixture_network_count": counts["network"],
    }
    if counts["container"]:
        raise Stop("disposable_containers_already_present", **facts)
    if counts["volume"] or counts["network"]:
        raise Stop("disposable_fixture_volume_or_network_already_present", **facts)
    return facts


def read_only_readiness(
    expected_pcp_sha: str,
    *,
    source_root: Path = SOURCE_ROOT,
    home: Path | None = None,
    runner: Callable[[list[str]], subprocess.CompletedProcess[str]] = _run,
) -> dict[str, Any]:
    """Pass means source/host ready to PREPARE a fresh fixture, not to run Codex."""
    if not SHA.fullmatch(expected_pcp_sha):
        raise Stop("expected_pcp_sha_invalid")
    if os.geteuid() == 0:
        raise Stop("operator_must_be_unprivileged")
    home = home or Path.home()

    # This checks the operator's PCP source checkout only; no git pull/fetch.
    if _ok(runner, ["git", "-C", str(source_root), "rev-parse", "HEAD"],
           "pcp_source_unreadable") != expected_pcp_sha:
        raise Stop("pcp_source_head_stale")
    if _ok(runner, ["git", "-C", str(source_root), "status", "--porcelain"],
           "pcp_status_unavailable"):
        raise Stop("pcp_source_dirty")

    target = home / SMOKE_ROOT_NAME
    if target.exists() or target.is_symlink():
        raise Stop("disposable_target_already_present")
    _docker_endpoint(runner)
    inventory = _fixture_inventory(runner)

    _ok(runner, ["ddev", "--version"], "ddev_cli_unavailable")
    raw = _ok(runner, ["ddev", "list", "-j"], "ddev_registry_unavailable")
    projects = _ddev_projects(raw)
    if any(item["name"].strip().casefold() == DDEV_NAME for item in projects):
        raise Stop("ddev_fixture_name_collision")
    _ok(runner, ["codex", "--version"], "codex_cli_unavailable")
    output = _ok(runner, ["codex", "mcp", "--help"], "codex_mcp_subcommand_unavailable")
    if not output or "mcp" not in output.lower():
        raise Stop("codex_mcp_capability_unverified")

    global_config = home / GLOBAL_CONFIG
    if global_config.is_symlink():
        raise Stop("global_ddev_config_symlink")
    if global_config.exists():
        try:
            if not global_config.is_file() or global_config.stat().st_size > 262144:
                raise Stop("global_ddev_config_unbounded")
            text = global_config.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            raise Stop("global_ddev_config_unreadable") from exc
        if re.search(r"(?m)^\s*hooks\s*:", text):
            raise Stop("global_ddev_hooks_unreviewed")

    return {
        "status": "PASS_HOST_PREFLIGHT_NO_ACTIVATION",
        "pcp_head_verified": True,
        "fixture_source_commit": FIXTURE_SHA,
        "fixture_ref": FIXTURE_REF,
        "docker_local_desktop": True,
        "disposable_docker_resources_absent_including_stopped": True,
        "fixture_inventory": inventory,
        "disposable_root_unoccupied": True,
        "disposable_writer_or_runtime_lease": "NOT_PROVEN_NO_JOB_DISPATCH",
        "ddev_fixture_name_unoccupied": True,
        "codex_mcp_cli_detected": True,
        "other_registered_ddev_project_count": len(projects),
        "existing_projects_inspected_or_modified": False,
        "actual_ddev_web_socket_and_egress": "NOT_YET_PROVEN",
        "real_mcp_http_phase": "NOT_TESTED",
        "next_gate": "DEDICATED_FIXTURE_SETUP_AND_WEB_CONTAINER_ISOLATION",
        "docker_ddev_git_mutations": 0,
        "model_calls": 0,
        "granted_new_credentials": False,
        "ready_to_dispatch_new_job": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expected-pcp-sha", required=True)
    args = parser.parse_args()
    try:
        result = read_only_readiness(args.expected_pcp_sha)
        code = 0
    except Stop as exc:
        result = {
            "status": "STOP",
            "blocker": str(exc),
            "docker_ddev_git_mutations": 0,
            "model_calls": 0,
            "ready_to_dispatch_new_job": False,
        }
        result.update(exc.facts)
        code = 2
    print(json.dumps(result, indent=2, sort_keys=True))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
