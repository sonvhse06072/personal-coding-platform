"""C3A source path: existing Engine worker, isolated F2 PG role, no legacy boot.

Not an operational authorization. The shipped source-only Compose is /bin/false
and F2 candidate config remains inactive and write-disabled until a distinct
C3B host/resource/credential admission. Never run Storage.init() here.
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import os
from pathlib import Path
from typing import Any

from .fullpath_fixture_safety import (
    FIXED_ENV, PROJECT_ID, _database_uri, _service_uri,
)
from .fullpath_fresh_startup import (
    V2_BRANCH, V2_INACTIVE_BASELINE,
    read_only_post_schema_table_snapshot, assess_post_schema_table_snapshot,
)


F2_WORKER_MODE = "g0_fullpath_worker"
F2_V2_REVISION = "f2-c1-window-v2-2026-10-12"
F2_V2_SEED = "3165b76d44b738c4709c3ca74f87297ff66dd397"


class F2WorkerNotReady(RuntimeError):
    """No worker, DB mutation, job or host operation is permitted."""


@dataclass(frozen=True)
class F2WorkerReady:
    project_id: str
    source_commit: str
    database_name: str


def require_f2_worker_environment(env: Mapping[str, str]) -> None:
    """Pure, exact F2 identity check BEFORE a database is opened."""
    if env.get("PCP_RUNTIME_STARTUP_MODE") != F2_WORKER_MODE or (
        env.get("PCP_F2_WORKER_ONLY_ENABLED") != "owner-approved"
    ):
        raise F2WorkerNotReady("F2 worker-only activation is not authorized")
    if any(
        env.get(k) != v for k, v in FIXED_ENV.items()
        if k != "PCP_RUNTIME_STARTUP_MODE"
    ):
        raise F2WorkerNotReady("F2 worker roots/config identity mismatch")
    if not _database_uri(env.get("DATABASE_URL", "")):
        raise F2WorkerNotReady("F2 worker database/app role identity mismatch")
    if not _service_uri(
        env.get("ROUTER_URL", ""), host="fullpath-router", port=8090
    ) or not _service_uri(
        env.get("DDEV_EXECUTOR_URL", ""), host="fullpath-executor", port=8790
    ):
        raise F2WorkerNotReady("F2 worker router/executor identity mismatch")
    if Path("/var/run/docker.sock").exists() or any(
        env.get(k) for k in (
            "GITHUB_DELIVERY_TOKEN", "ANTIGRAVITY_BRIDGE_TOKEN",
            "ANTIGRAVITY_BRIDGE_URL", "PCP_G0_EXECUTION_ENABLED",
            "PCP_G0_DELIVERY_ENABLED", "PCP_FULLPATH_SOURCE_ONLY",
            "PCP_FULLPATH_OPERATIONAL_ACTIVATION",
        )
    ):
        raise F2WorkerNotReady("F2 worker has legacy/privileged capability")


def require_f2_worker_registry(
    projects: Mapping[str, Any], baselines: Mapping[str, Any],
) -> None:
    """The unchanged inactive C1 registries must always STOP."""
    records = projects.get("projects") if isinstance(projects, Mapping) else None
    if not isinstance(records, dict) or set(records) != {PROJECT_ID}:
        raise F2WorkerNotReady("F2 worker fixture registry not singleton")
    cfg = records[PROJECT_ID]
    if not isinstance(cfg, dict) or (
        cfg.get("path") != "${CODING_PROJECTS_ROOT}/pcp-g0-fullpath-fixture"
        or cfg.get("base_branch") != V2_BRANCH
        or not isinstance(cfg.get("runtime"), dict)
        or cfg["runtime"].get("workspace_mode") != "isolated_clone"
        or cfg["runtime"].get("exclusive_project_lease") is not False
        or not isinstance(cfg.get("ddev"), dict)
        or cfg["ddev"].get("enabled") is not False
        or not isinstance(cfg.get("autonomy"), dict)
        or not all(cfg["autonomy"].get(k) is True for k in (
            "allow_commit", "allow_push_ai_branch", "allow_create_pr",
        ))
        or cfg["autonomy"].get("allow_auto_merge_low_risk") is not False
        or cfg["autonomy"].get("allow_production_deploy") is not False
    ):
        raise F2WorkerNotReady("F2 worker registry still PARKED or broadened")

    baseline_records = baselines.get("projects") if isinstance(baselines, Mapping) else None
    frame = (
        baseline_records.get(PROJECT_ID)
        if isinstance(baseline_records, dict) and set(baseline_records) == {PROJECT_ID}
        else None
    )
    if not isinstance(frame, dict) or (
        frame.get("active_revision") != F2_V2_REVISION
        or frame.get("revisions") != V2_INACTIVE_BASELINE["revisions"]
        or frame["revisions"][F2_V2_REVISION]["source_commit"] != F2_V2_SEED
    ):
        raise F2WorkerNotReady("F2 v2 approved baseline not separately activated")


def attest_f2_worker_database(
    *, storage: Any, env: Mapping[str, str],
    projects: Mapping[str, Any], baselines: Mapping[str, Any],
) -> F2WorkerReady:
    """Only read an isolated exact DB AFTER environment/authority gates pass."""
    require_f2_worker_environment(env)
    require_f2_worker_registry(projects, baselines)
    if getattr(storage, "dsn", None) != env["DATABASE_URL"]:
        raise F2WorkerNotReady("F2 storage DSN differs from gated database identity")
    snapshot = read_only_post_schema_table_snapshot(
        database_url=env["DATABASE_URL"], connect=storage.connect,
    )
    if assess_post_schema_table_snapshot(snapshot)["source_snapshot_valid"] is not True:
        raise F2WorkerNotReady("F2 DB lacks exact 25 empty tables/role/exclusivity")
    return F2WorkerReady(
        project_id=PROJECT_ID, source_commit=F2_V2_SEED,
        database_name="fullpath",
    )


def f2_direct_intake_route_allowed(method: str, path: str) -> bool:
    """No planner, telemetry, PM Bridge, model admin or global cancellation."""
    if method == "GET" and path == "/health":
        return True
    if method == "POST" and path == "/v1/jobs":
        return True
    if method == "GET" and path.startswith("/v1/jobs/"):
        import re
        return re.fullmatch(r"/v1/jobs/[0-9a-f]{32}", path) is not None
    return False
