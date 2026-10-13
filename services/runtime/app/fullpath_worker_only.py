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
    V2_BRANCH, V2_INACTIVE_BASELINE, POST_SCHEMA_TABLES,
    read_only_post_schema_table_snapshot, assess_post_schema_table_snapshot,
)


F2_WORKER_MODE = "g0_fullpath_worker"
F2_V2_REVISION = "f2-c1-window-v2-2026-10-12"
F2_V2_SEED = "3165b76d44b738c4709c3ca74f87297ff66dd397"
# One OWNER-ATTESTED blocked trial, not a general DB history/resume policy.
F2_REENTRY_JOB_ID = "88b9e0d8500147a9857621d18875a8e4"
F2_REENTRY_COUNTS = {
    "cp_jobs": 1,
    "cp_job_events": 9,
    "cp_task_telemetry": 1,
    "cp_continuity_proposals": 1,
}


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


def require_f2_exact_blocked_job(row: Any) -> None:
    """Pure guard for the ONE existing F2-T01 job; never clear its counters."""
    if not isinstance(row, Mapping):
        raise F2WorkerNotReady("F2 historical job is missing")
    result = row.get("result") or {}
    progress = row.get("progress") or {}
    checkpoint = row.get("checkpoint") or {}
    intake = checkpoint.get("canonical_intake") or {}
    route = row.get("route") or {}
    strategy = route.get("strategy") or {}
    executor = strategy.get("executor") or {}
    budget = strategy.get("budget") or {}
    attempts = progress.get("agent_attempts") or []
    if (
        row.get("id") != F2_REENTRY_JOB_ID
        or row.get("project_id") != PROJECT_ID
        or row.get("source_commit") != F2_V2_SEED
        or row.get("status") != "blocked"
        or row.get("branch") != "ai/88b9e0d85001"
        or row.get("workspace")
        != "/fullpath/workspaces/" + F2_REENTRY_JOB_ID
        or row.get("dry_run") is not False
        or row.get("error") is not None
        or not isinstance(result, Mapping)
        or result.get("reason") != "material_change_missing_without_model_fallback"
        or result.get("commit") or result.get("delivery")
        or not isinstance(intake, Mapping)
        or intake.get("mode") != "direct"
        or intake.get("bounded_direct") is not True
        or intake.get("decomposition_required") is not False
        or intake.get("baseline_revision") != F2_V2_REVISION
        or checkpoint.get("workspace_mode") != "isolated_clone"
        or checkpoint.get("orchestrator_launch")
        or not isinstance(progress, Mapping)
        or type(progress.get("model_calls")) is not int
        or progress["model_calls"] != 1
        or type(progress.get("iteration")) is not int
        or progress["iteration"] != 1
        or progress.get("changed_files") != 0
        or progress.get("last_agent_failure_kind") != "no_effect"
        or progress.get("agent_succeeded") is not False
        or progress.get("provider_failures")
        or not isinstance(attempts, list)
        or len(attempts) != 1
        or not isinstance(attempts[0], Mapping)
        or attempts[0].get("returncode") != 1
        or attempts[0].get("failure_kind") is not None
        or strategy.get("profile") != "fast"
        or strategy.get("planner") is not None
        or strategy.get("budget_mode") == "adaptive"
        or executor.get("id") != "codex_gpt6_luna"
        or executor.get("model") != "gpt-6-luna"
        or executor.get("reasoning_effort") != "medium"
        or budget.get("max_model_calls") != 2
        or budget.get("max_iterations") != 2
        or budget.get("max_wall_time_minutes") != 15
        or budget.get("max_changed_files") != 3
        or budget.get("max_model_failovers") != 0
        or budget.get("max_provider_failovers") != 0
    ):
        raise F2WorkerNotReady("F2 exact blocked-job recovery evidence mismatch")


def _attest_f2_blocked_reentry(storage: Any, snapshot: Mapping[str, Any]) -> None:
    """Read-only and fail-closed for ONE previously attested F2 data footprint."""
    expected = {name: 0 for name in POST_SCHEMA_TABLES}
    expected.update(F2_REENTRY_COUNTS)
    if (
        len(POST_SCHEMA_TABLES) != 25
        or snapshot.get("table_counts") != expected
        # Reuse the original strict schema/identity proof with only the
        # separately verified historical data-count dimension factored out.
        or assess_post_schema_table_snapshot({
            **snapshot, "table_counts": {name: 0 for name in POST_SCHEMA_TABLES},
        })["source_snapshot_valid"] is not True
    ):
        raise F2WorkerNotReady("F2 DB lacks exact 25 empty tables; re-entry manifest/count mismatch")

    with storage.connect() as conn:
        conn.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
        row = conn.execute(
            "SELECT * FROM public.cp_jobs WHERE id=%s",
            (F2_REENTRY_JOB_ID,),
        ).fetchone()
        require_f2_exact_blocked_job(row)
        for table, expected_count in F2_REENTRY_COUNTS.items():
            if table == "cp_jobs":
                continue
            # Constant reviewed identifiers only; every nonempty child record
            # must have this exact single job_id, never foreign/orphan data.
            count = conn.execute(
                f'SELECT COUNT(*) AS n FROM public."{table}" WHERE job_id=%s',
                (F2_REENTRY_JOB_ID,),
            ).fetchone()
            if not isinstance(count, Mapping) or count.get("n") != expected_count:
                raise F2WorkerNotReady("F2 re-entry foreign/orphan row detected")


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
        # A blocked F2-T01 is the only historical re-entry; no data reset,
        # replay, model invocation or job creation is performed at startup.
        _attest_f2_blocked_reentry(storage, snapshot)
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
    if method == "POST" and path == f"/v1/jobs/{F2_REENTRY_JOB_ID}/run":
        return True
    import re
    if method == "POST" and re.fullmatch(
        r"/v1/g0-fullpath/jobs/[0-9a-f]{32}/pm-review", path,
    ):
        # Never reveal a broader PM/plan/merge route. C3B must separately
        # configure reviewer identity + activate v2 + enable this gate.
        return os.getenv("PCP_FULLPATH_PM_FINALIZATION_ENABLED") == "owner-approved"
    if method == "GET" and path.startswith("/v1/jobs/"):
        return re.fullmatch(r"/v1/jobs/[0-9a-f]{32}", path) is not None
    return False
