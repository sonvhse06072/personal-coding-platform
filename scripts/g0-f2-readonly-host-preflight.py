#!/usr/bin/env python3
"""Bounded READ-ONLY Owner-WSL preflight of *future* PCP F2 Docker names.

Only exact F2 container/volume/network names and exact F2 compose label may
be queried. Never lists unrelated resources, reads Docker inspect payloads
into output, calls DDEV, starts containers, reads tokens or changes resources.

Usage:
  python3 scripts/g0-f2-readonly-host-preflight.py inspect --expected-sha <PCP_MAIN_SHA>

The result is always STOP, even if all names are absent. This preflight
provides real local noncollision evidence ONLY when executed on an approved
local Docker context. It does not authorize resource creation or F2 startup.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import subprocess
from typing import Any, Callable

PROJECT = "pcp-f2-fullpath"
ROOT = Path(__file__).resolve().parents[1]
SERVICES = ("fullpath-db", "fullpath-router", "fullpath-executor", "fullpath-runtime")
RESOURCES = {
    "container": tuple(f"{PROJECT}-{svc}-1" for svc in SERVICES),
    "volume": ("pcp-f2-fullpath-postgres-data",),
    "network": ("pcp-f2-fullpath-private", "pcp-f2-fullpath-provider"),
}
CONTAINER_LABEL_QUERY = (
    "docker", "container", "ls", "--all", "--quiet",
    "--filter", "label=com.docker.compose.project=" + PROJECT,
)
CONTEXT_QUERY = ("docker", "context", "inspect")
GIT_QUERY = ("git", "-C", str(ROOT), "rev-parse", "HEAD")
ALLOWED = frozenset(
    (("docker", kind, "inspect", name) for kind, names in RESOURCES.items()
     for name in names)
) | {CONTAINER_LABEL_QUERY, CONTEXT_QUERY, GIT_QUERY}
EXPECTED_SHA = re.compile(r"[0-9a-f]{40}\Z")
CONTAINER_ID = re.compile(r"[0-9a-f]{12,64}\Z")


class SafeStop(RuntimeError):
    """Do not proceed when the requested identity or read-only proof is unclear."""

    def __init__(
        self, blocker: str, *, kind: str | None = None,
        name: str | None = None, error_class: str | None = None,
    ) -> None:
        super().__init__(blocker)
        # Only constant, hardcoded F2 resource identities are surfaced.
        self.kind = kind
        self.name = name
        self.error_class = error_class


def _run(argv: tuple[str, ...]) -> subprocess.CompletedProcess[str]:
    if argv not in ALLOWED:
        raise SafeStop("command_outside_f2_readonly_allowlist")
    try:
        return subprocess.run(
            list(argv), text=True, capture_output=True, timeout=12,
            check=False, stdin=subprocess.DEVNULL,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise SafeStop("f2_readonly_command_unavailable_or_timeout") from exc


def _local_context(run: Callable[[tuple[str, ...]], Any]) -> None:
    proc = run(CONTEXT_QUERY)
    if proc.returncode:
        raise SafeStop("docker_context_inspection_failed")
    try:
        entries = json.loads(proc.stdout)
        endpoint = entries[0]["Endpoints"]["docker"]["Host"]
        if not isinstance(entries, list) or len(entries) != 1:
            raise ValueError()
    except (KeyError, IndexError, TypeError, ValueError) as exc:
        raise SafeStop("docker_context_metadata_invalid") from exc
    if not isinstance(endpoint, str) or not endpoint.startswith("unix://"):
        raise SafeStop("docker_context_not_local_unix")
    # A source-safe plan is not grounds to query a remote/shared Docker host.
    override = os.getenv("DOCKER_HOST", "").strip()
    if override and override != endpoint:
        raise SafeStop("docker_host_override_mismatch")


def _known_absence_response(
    kind: str, name: str, stderr: str, stdout: str,
) -> bool:
    """Accept exact Docker CLI missing-object evidence, never generic 404s.

    Docker prints differing formats depending on resource kind/version:
    'No such object: NAME', 'network NAME not found', or
    'get NAME: no such volume'. Only an exact F2 resource name matches.
    """
    if stdout.strip() not in {"", "[]"}:
        return False
    message = stderr.strip()
    if not message or len(message) > 350 or "\n" in message or "\r" in message:
        return False
    target = re.escape(name)
    patterns = [
        rf"(?:Error:|Error response from daemon:)\s*No such (?:object|{kind}):\s*{target}",
    ]
    if kind == "network":
        patterns.append(
            rf"Error response from daemon:\s*network {target} not found"
        )
    if kind == "volume":
        patterns.extend((
            rf"Error response from daemon:\s*get {target}: no such volume",
            rf"Error response from daemon:\s*volume {target} not found",
        ))
    return any(re.fullmatch(pattern, message, flags=re.IGNORECASE)
               for pattern in patterns)


def _present(
    run: Callable[[tuple[str, ...]], Any], kind: str, name: str,
) -> bool:
    proc = run(("docker", kind, "inspect", name))
    if proc.returncode == 0:
        try:
            data = json.loads(proc.stdout)
        except (TypeError, ValueError) as exc:
            raise SafeStop("f2_docker_metadata_invalid") from exc
        if not isinstance(data, list) or len(data) != 1:
            raise SafeStop("f2_docker_metadata_invalid")
        return True
    if proc.returncode != 1:
        raise SafeStop(
            "f2_docker_inspection_unexpected_status", kind=kind, name=name,
            error_class="unexpected_exit_code",
        )
    # A foreign, ambiguous, permission or daemon error must NEVER prove
    # absence. Report only the bounded F2 target, not Docker stderr.
    if not _known_absence_response(kind, name, str(proc.stderr or ""),
                                   str(proc.stdout or "")):
        raise SafeStop(
            "f2_docker_absence_not_proven", kind=kind, name=name,
            error_class="unrecognized_or_ambiguous_docker_error",
        )
    return False


def inspect(
    expected_sha: str, *, run: Callable[[tuple[str, ...]], Any] = _run,
) -> dict[str, Any]:
    """Only inspect exact F2 names; no model/DB/legacy PCP operations."""
    if not EXPECTED_SHA.fullmatch(expected_sha):
        raise SafeStop("expected_pcp_source_sha_invalid")
    git = run(GIT_QUERY)
    if git.returncode or git.stdout.strip() != expected_sha:
        raise SafeStop("pcp_source_head_mismatch")
    _local_context(run)

    existing = []
    for kind, names in RESOURCES.items():
        for name in names:
            if _present(run, kind, name):
                existing.append(kind + ":" + name)
    labeled = run(CONTAINER_LABEL_QUERY)
    if labeled.returncode:
        raise SafeStop("f2_container_label_query_failed")
    ids = [value.strip() for value in labeled.stdout.splitlines() if value.strip()]
    if any(not CONTAINER_ID.fullmatch(value) for value in ids):
        raise SafeStop("f2_container_label_query_invalid")
    if ids:
        existing.append("container:unexpected_f2_compose_label")
    return {
        "phase": "g0_f2_readonly_host_resource_noncollision",
        "status": "STOP",
        "source_head_verified": True,
        "local_unix_docker_context": True,
        "scanned_exact_f2_names": {k: list(v) for k, v in RESOURCES.items()},
        "f2_names_currently_unoccupied": not existing,
        "f2_collisions": existing,
        "independent_resource_owner_attested": False,
        "provider_egress_or_credentials_attested": False,
        "fixture_or_baseline_attested": False,
        "operational_activation_authorized": False,
        "model_calls": 0,
        "resource_mutations": 0,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("inspect",))
    parser.add_argument("--expected-sha", required=True)
    args = parser.parse_args()
    try:
        data = inspect(args.expected_sha)
        code = 0 if data["f2_names_currently_unoccupied"] else 2
    except SafeStop as exc:
        data = {
            "phase": "g0_f2_readonly_host_resource_noncollision",
            "status": "STOP",
            "blocker": str(exc),
            "operational_activation_authorized": False,
            "resource_mutations": 0,
            "model_calls": 0,
        }
        if exc.kind is not None and exc.name is not None:
            # Safe diagnostics from reviewed F2 constants only; never include
            # raw Docker output, local paths, environment or credentials.
            data["blocked_resource"] = {
                "kind": exc.kind, "name": exc.name,
            }
            data["docker_error_class"] = exc.error_class or "unknown"
        code = 2
    print(json.dumps(data, sort_keys=True, indent=2))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
