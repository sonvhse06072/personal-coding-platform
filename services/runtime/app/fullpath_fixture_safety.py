"""Fail-closed admission for a SOURCE-ONLY candidate of the normal PCP pipeline.

Never a second Runtime, alternative verifier or operational approval. The old
G0D-T01 database/journals and legacy PCP services are NOT eligible.
"""
from __future__ import annotations

from collections.abc import Mapping
import re
from typing import Any
from urllib.parse import urlsplit


MODE = "g0_fullpath_candidate"
PROJECT_ID = "pcp-g0-fullpath-fixture"
OLD_G0_SEED = "39ef13c25b24c4a1b43a720ae53419f479996ed2"
SOURCE_ONLY_BLOCKERS = (
    "hostless_required_verification_not_proven",
    "privileged_exact_sha_ci_delivery_not_proven",
    "new_fixture_and_operational_ownership_not_proven",
)
FIXED_ENV = {
    "PCP_RUNTIME_STARTUP_MODE": MODE,
    "CODING_PROJECTS_ROOT": "/fullpath/sources",
    "CODING_WORKSPACES_ROOT": "/fullpath/workspaces",
    "CODING_DIRECT_PROJECT_ROOT": "/fullpath/direct-disabled",
    "PROJECTS_FILE": "/fullpath/config/projects.yml",
    "PROJECT_BASELINES_FILE": "/fullpath/config/project-baselines.yml",
    "MODELS_FILE": "/fullpath/config/models.yml",
    "ROUTING_POLICY_FILE": "/fullpath/config/routing-policy.yml",
    "CODEX_HOME": "/home/coder/.codex-fullpath",
}
FORBIDDEN_PRESENT = (
    "ANTIGRAVITY_BRIDGE_URL",
    "ANTIGRAVITY_BRIDGE_TOKEN",
    "GITHUB_DELIVERY_TOKEN",
    "PCP_G0_EXECUTION_ENABLED",
    "PCP_G0_DELIVERY_ENABLED",
    "PCP_G0_CODEX_HOME",
)


class FullPathCandidateNotReady(RuntimeError):
    """Source proposal must never start the normal durable Runtime lifecycle."""


def _service_uri(value: str, *, host: str, port: int) -> bool:
    try:
        uri = urlsplit(value)
        return (
            uri.scheme == "http"
            and uri.hostname == host
            and uri.port == port
            and uri.username is None
            and uri.password is None
            and uri.path in {"", "/"}
            and not uri.query and not uri.fragment
        )
    except ValueError:
        return False


def _database_uri(value: str) -> bool:
    try:
        uri = urlsplit(value)
        return (
            uri.scheme in {"postgres", "postgresql"}
            and uri.hostname == "fullpath-db"
            and uri.port == 5432
            and uri.username == "fullpath"
            and uri.path == "/fullpath"
            and uri.password not in {None, ""}
            and not uri.query and not uri.fragment
        )
    except ValueError:
        return False


def assess_source_contract(
    env: Mapping[str, str],
    projects_document: Mapping[str, Any],
    baselines_document: Mapping[str, Any],
    *,
    docker_socket_present: bool,
) -> dict[str, Any]:
    """Pure source assessment; NO DB, Docker, filesystem write or model call."""
    checks: dict[str, bool] = {}

    checks["dedicated_config_and_workspace_roots"] = all(
        env.get(k) == v for k, v in FIXED_ENV.items()
    )
    checks["dedicated_db_identity"] = _database_uri(
        env.get("DATABASE_URL", "")
    )
    checks["dedicated_router_identity"] = _service_uri(
        env.get("ROUTER_URL", ""), host="fullpath-router", port=8090
    )
    checks["dedicated_executor_identity"] = _service_uri(
        env.get("DDEV_EXECUTOR_URL", ""), host="fullpath-executor", port=8790
    )
    checks["no_host_privileged_or_old_g0_secrets"] = bool(
        not docker_socket_present
        and all(not env.get(name) for name in FORBIDDEN_PRESENT)
        and not env.get("PCP_FULLPATH_OPERATIONAL_ACTIVATION")
    )

    projects = projects_document.get("projects")
    project = (
        projects.get(PROJECT_ID)
        if isinstance(projects, dict) and set(projects) == {PROJECT_ID}
        else None
    )
    runtime = project.get("runtime") if isinstance(project, dict) else None
    autonomy = project.get("autonomy") if isinstance(project, dict) else None
    ddev = project.get("ddev") if isinstance(project, dict) else None
    checks["singleton_new_fixture_with_locked_workspace"] = bool(
        isinstance(project, dict)
        and project.get("path")
        == "${CODING_PROJECTS_ROOT}/pcp-g0-fullpath-fixture"
        and project.get("base_branch") == "benchmark/fullpath"
        and isinstance(runtime, dict)
        and runtime.get("workspace_mode") == "isolated_clone"
        and runtime.get("exclusive_project_lease") is False
        and runtime.get("developer_permission_mode", "bounded") == "bounded"
    )
    checks["no_unproven_delivery_or_ddev"] = bool(
        isinstance(autonomy, dict)
        and autonomy
        and all(value is False for value in autonomy.values())
        and isinstance(ddev, dict)
        and ddev.get("enabled") is False
    )

    baselines = baselines_document.get("projects")
    baseline = (
        baselines.get(PROJECT_ID)
        if isinstance(baselines, dict) and set(baselines) == {PROJECT_ID}
        else None
    )
    revision = (
        baseline.get("active_revision")
        if isinstance(baseline, dict) else None
    )
    revisions = (
        baseline.get("revisions")
        if isinstance(baseline, dict) else None
    )
    entry = (
        revisions.get(revision)
        if isinstance(revisions, dict) and isinstance(revision, str)
        and set(revisions) == {revision}
        else None
    )
    sha = entry.get("source_commit") if isinstance(entry, dict) else None
    checks["independent_approved_source_revision"] = bool(
        isinstance(revision, str)
        and re.fullmatch(r"[a-zA-Z0-9._-]{1,80}", revision)
        and isinstance(entry, dict)
        and entry.get("status") == "approved"
        and isinstance(sha, str)
        and re.fullmatch(r"[0-9a-f]{40}", sha)
        and sha != OLD_G0_SEED
    )

    blockers = [
        "contract_" + k for k, valid in checks.items() if not valid
    ] + list(SOURCE_ONLY_BLOCKERS)
    return {
        "status": "STOP",
        "phase": "g0_fullpath_candidate_source_gate",
        "project": PROJECT_ID,
        "candidate_source_contract_valid": all(checks.values()),
        "checks": checks,
        "blockers": blockers,
        "full_runtime_start_allowed": False,
        "real_verification_proven": False,
        "auto_delivery_proven": False,
        "model_calls_this_command": 0,
        "ready_to_dispatch": False,
    }


def refuse_source_only_startup() -> None:
    """Block BEFORE Storage.init, cancel-all, replay, leases or plan tick."""
    raise FullPathCandidateNotReady(
        "G0 full-path candidate is source-only: hostless verification, "
        "exact-SHA delivery and sandbox ownership are not yet proven"
    )
