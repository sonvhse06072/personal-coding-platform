"""Source-only feasibility of a fresh, least-privilege F2 PostgreSQL boot.

Never starts the normal PCP Runtime, mutates a database, authenticates a model,
cancels host agents, dispatches queued work or grants operational approval.

The optional SQL inspector is READ-ONLY and must be invoked only by a separately
authorized future F2 resource-owner preflight; CI tests use fake connections.
A good snapshot is evidence for a later decision, never startup authority.
"""
from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from .fullpath_fixture_safety import PROJECT_ID, _database_uri


READ_ONLY_SNAPSHOT_SQL = """
SELECT
  current_database() AS database_name,
  current_user AS database_role,
  current_setting('is_superuser') AS is_superuser,
  (SELECT COUNT(*) FROM pg_catalog.pg_class c
   JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
   WHERE n.nspname !~ '^pg_'
     AND n.nspname <> 'information_schema'
     AND c.relkind IN ('r','p','v','m','S','f')) AS user_relation_count,
  (SELECT COUNT(*) FROM pg_catalog.pg_proc p
   JOIN pg_catalog.pg_namespace n ON n.oid = p.pronamespace
   WHERE n.nspname !~ '^pg_'
     AND n.nspname <> 'information_schema') AS user_function_count,
  (SELECT COUNT(*) FROM pg_catalog.pg_stat_activity
   WHERE datname = current_database()
     AND pid <> pg_backend_pid()) AS peer_session_count
"""


def read_only_fresh_database_snapshot(
    *,
    database_url: str,
    connect: Callable[[], Any],
) -> dict[str, Any]:
    """Read catalog metadata with transaction-local READ ONLY before ANY query.

    No DDL, schema migration, write or job replay. The caller supplies a
    verified F2-only connection factory; never call on legacy/G0 databases.
    """
    if not _database_uri(database_url):
        raise RuntimeError("fullpath_f2_database_uri_not_owned")
    with connect() as conn:
        conn.execute("SET TRANSACTION READ ONLY")
        row = conn.execute(READ_ONLY_SNAPSHOT_SQL).fetchone()
    if not isinstance(row, Mapping):
        raise RuntimeError("fullpath_f2_database_catalog_unreadable")
    return {
        key: row.get(key) for key in (
            "database_name", "database_role", "is_superuser",
            "user_relation_count", "user_function_count",
            "peer_session_count",
        )
    }


def assess_fresh_fullpath_startup(
    snapshot: Mapping[str, Any],
    projects: Mapping[str, Any],
    baselines: Mapping[str, Any],
) -> dict[str, Any]:
    """Decide whether source evidence is coherent; never approve a live boot.

    Even an empty, non-superuser DB has no attested resource ownership, single
    writer, image digest or provider-egress policy. It is NOT sufficient to
    release the parked F2 runtime or skip any prior CI/PM gates.
    """
    checks: dict[str, bool] = {}
    checks["dedicated_fresh_database_and_unprivileged_role"] = (
        snapshot.get("database_name") == "fullpath"
        and snapshot.get("database_role") == "fullpath"
        and snapshot.get("is_superuser") == "off"
    )
    checks["pristine_database_objects_and_no_peer_connections"] = all(
        type(snapshot.get(key)) is int and snapshot[key] == 0
        for key in (
            "user_relation_count", "user_function_count",
            "peer_session_count",
        )
    )
    registered = projects.get("projects")
    config = (
        registered.get(PROJECT_ID)
        if isinstance(registered, dict) and set(registered) == {PROJECT_ID}
        else None
    )
    runtime = config.get("runtime") if isinstance(config, dict) else None
    ddev = config.get("ddev") if isinstance(config, dict) else None
    checks["one_isolated_fixture_no_direct_or_ddev"] = bool(
        isinstance(config, dict)
        and config.get("path")
        == "${CODING_PROJECTS_ROOT}/pcp-g0-fullpath-fixture"
        and config.get("base_branch") == "benchmark/fullpath"
        and isinstance(runtime, dict)
        and runtime.get("workspace_mode") == "isolated_clone"
        and runtime.get("exclusive_project_lease") is False
        and isinstance(ddev, dict)
        and ddev.get("enabled") is False
    )
    active = baselines.get("projects")
    record = (
        active.get(PROJECT_ID)
        if isinstance(active, dict) and set(active) == {PROJECT_ID}
        else None
    )
    # F2a source intentionally has no approved baseline. A future source-only
    # assessment must NOT invent an approved SHA from G0D-T01.
    checks["original_source_still_not_approved"] = bool(
        isinstance(record, dict)
        and record.get("active_revision") is None
        and record.get("revisions") == {}
    )
    source_valid = all(checks.values())
    blockers = [
        "source_" + name for name, passed in checks.items() if not passed
    ] + [
        "fresh_volume_and_single_writer_not_attested",
        "separate_host_antigravity_cancel_not_yet_eliminated",
        "scope_safe_normal_engine_and_orchestrator_not_wired",
        "oci_images_provider_egress_and_privileged_delivery_not_verified",
        "fixture_approved_baseline_and_owner_activation_missing",
    ]
    return {
        "status": "STOP",
        "phase": "g0_f2b_fresh_db_startup_source_assessment",
        "source_snapshot_valid": source_valid,
        "checks": checks,
        "blockers": blockers,
        "effects_that_must_be_absent": {
            "global_antigravity_cancel_all": True,
            "foreign_job_replay": True,
            "foreign_executor_cancel": True,
            "legacy_project_lease_reconciliation": True,
            "unsupervised_plan_tick": True,
        },
        "full_runtime_start_allowed": False,
        "model_calls_this_command": 0,
        "new_resources_created": 0,
    }
