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

# This is exact OWNER-APPROVED source metadata, not an activation signal.
# Retain the old empty v1 candidate only for source-only backward compatibility.
V2_BRANCH = "benchmark/fullpath-v2"
V2_INACTIVE_BASELINE = {
    "active_revision": None,
    "revisions": {
        "f2-c1-window-v2-2026-10-12": {
            "status": "approved",
            "source_commit": "3165b76d44b738c4709c3ca74f87297ff66dd397",
            "authority": [
                {"path": "README.md", "authority": "human_owner_protected"},
                {"path": "docs/F2-T01.md", "authority": "human_owner_protected"},
                {"path": ".github/workflows/validation.yml", "authority": "human_owner_protected"},
                {"path": "composer.json", "authority": "human_owner_protected"},
                {"path": "composer.lock", "authority": "human_owner_protected"},
                {"path": "web/modules/custom/pcp_f2_fixture/src/WindowOverlapDetector.php", "authority": "mutable_execution"},
                {"path": "web/modules/custom/pcp_f2_fixture/tests/src/Unit/WindowOverlapDetectorTest.php", "authority": "mutable_execution"},
                {"path": "web/modules/custom/pcp_f2_fixture/tests/src/Kernel/WindowOverlapServiceTest.php", "authority": "mutable_execution"},
            ],
            "references": {
                "goals": [{"path": "README.md"}],
                "non_goals": [{"path": "README.md"}],
                "requirements": [{"path": "docs/F2-T01.md"}],
                "architecture_constraints": [{"path": "README.md"}],
                "quality_policy": [
                    {"path": "README.md"},
                    {"path": ".github/workflows/validation.yml"},
                ],
                "security_policy": [
                    {"path": "README.md"},
                    {"path": ".github/workflows/validation.yml"},
                ],
                "budget_policy": [{"path": "docs/F2-T01.md"}],
                "roadmap_frame": [{"path": "docs/F2-T01.md"}],
            },
        },
    },
}


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
        and config.get("base_branch") in {"benchmark/fullpath", V2_BRANCH}
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
    # An approved source frame is not an ACTIVE baseline or F2 startup.
    # v1 has no revision; only the exact Owner-approved v2 metadata is accepted
    # when paired with its new branch. Neither may access DB/host operations.
    checks["reviewed_source_frame_is_inactive"] = bool(
        isinstance(config, dict)
        and (
            (config.get("base_branch") == "benchmark/fullpath"
             and record == {"active_revision": None, "revisions": {}})
            or (config.get("base_branch") == V2_BRANCH
                and record == V2_INACTIVE_BASELINE)
        )
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


# F2d-02: inspected from the twelve existing Runtime DDL declarations.
# This is a source-pinned TABLE contract, NOT an approved complete migration or
# object manifest (sequences, indexes, triggers, function grants are separate).
# Tests compare every name against the actual SQL strings and fail on drift.
POST_SCHEMA_TABLE_SOURCES = {
    "storage": (
        "cp_jobs", "cp_project_leases", "cp_job_previews", "cp_job_events",
        "cp_execution_plans",
    ),
    "plan_orchestrator": (
        "cp_plan_orchestrator_meta", "cp_plan_orchestrations",
        "cp_plan_work_orders", "cp_plan_work_order_checkpoints",
        "cp_notification_outbox",
    ),
    "plan_progress_store": (
        "cp_plan_progress_meta", "cp_plan_progress_handoffs",
    ),
    "control_actions": ("cp_control_actions",),
    "telemetry_storage": (
        "cp_task_telemetry", "cp_attention_events", "cp_continuity_proposals",
    ),
    "job_status_publisher": ("cp_job_status_handoffs",),
    "pm_bridge": ("cp_pm_bridge_events",),
    "pm_control": ("cp_pm_control_events",),
    "pm_late_review": (
        "cp_pm_late_review_attempts", "cp_pm_late_review_attestations",
    ),
    "pm_merge_audit": ("cp_pm_merge_audit",),
    "pm_chat_review": ("cp_pm_chat_review_attestations",),
    "quota_telemetry": ("cp_quota_snapshots", "cp_quota_collectors"),
}
POST_SCHEMA_TABLES = frozenset(
    name for tables in POST_SCHEMA_TABLE_SOURCES.values() for name in tables
)

# Future explicitly authorized, F2-only, read-only evidence collector.
# The single repeatable-read snapshot prevents cross-statement row count drift.
# This is not called by Runtime startup, Compose, or any production endpoint.
POST_SCHEMA_READ_ONLY_TXN = (
    "SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY"
)
POST_SCHEMA_IDENTITY_SQL = """
SELECT current_database() AS database_name,
       current_user AS database_role,
       current_setting('is_superuser') AS is_superuser,
       (SELECT COUNT(*) FROM pg_catalog.pg_stat_activity
        WHERE datname = current_database() AND pid <> pg_backend_pid())
         AS peer_session_count,
       (SELECT COUNT(*) FROM pg_catalog.pg_proc p
        JOIN pg_catalog.pg_namespace n ON n.oid = p.pronamespace
        WHERE n.nspname !~ '^pg_'
          AND n.nspname <> 'information_schema') AS user_function_count
"""
POST_SCHEMA_RELATIONS_SQL = """
SELECT n.nspname AS schema_name, c.relname AS table_name,
       c.relkind AS relation_kind
FROM pg_catalog.pg_class c
JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
WHERE n.nspname !~ '^pg_'
  AND n.nspname <> 'information_schema'
  AND c.relkind IN ('r', 'p', 'f', 'v', 'm')
ORDER BY n.nspname, c.relname
"""


def _post_schema_identity_valid(row: Any) -> bool:
    return (
        isinstance(row, Mapping)
        and row.get("database_name") == "fullpath"
        and row.get("database_role") == "fullpath"
        and row.get("is_superuser") == "off"
        and type(row.get("peer_session_count")) is int
        and row["peer_session_count"] == 0
        and type(row.get("user_function_count")) is int
        and row["user_function_count"] == 0
    )


def _post_schema_table_names(rows: Any) -> set[str] | None:
    """Fail closed for any missing/extra/duplicated/non-public base table.

    Views, materialized views, partitioned or foreign relations are denied.
    PostgreSQL sequences and indexes remain a distinct, unproven object gate.
    """
    if not isinstance(rows, (list, tuple)):
        return None
    names: set[str] = set()
    for row in rows:
        if (
            not isinstance(row, Mapping)
            or row.get("schema_name") != "public"
            or row.get("relation_kind") != "r"
            or not isinstance(row.get("table_name"), str)
        ):
            return None
        name = row["table_name"]
        if name not in POST_SCHEMA_TABLES or name in names:
            return None
        names.add(name)
    return names if names == POST_SCHEMA_TABLES else None


def read_only_post_schema_table_snapshot(
    *, database_url: str, connect: Callable[[], Any],
) -> dict[str, Any]:
    """F2-only, future owner-scoped read-only inventory; never bootstrap.

    The supplied connection must belong to an independently attested NEW F2
    database. String inspection of a DSN alone is not resource ownership proof.
    All SQL uses static, reviewed table names; no caller-provided identifiers.
    """
    if not _database_uri(database_url):
        raise RuntimeError("fullpath_f2_post_schema_database_uri_not_owned")
    with connect() as conn:
        conn.execute(POST_SCHEMA_READ_ONLY_TXN)
        identity = conn.execute(POST_SCHEMA_IDENTITY_SQL).fetchone()
        if not _post_schema_identity_valid(identity):
            raise RuntimeError("fullpath_f2_post_schema_identity_not_trusted")
        relations = conn.execute(POST_SCHEMA_RELATIONS_SQL).fetchall()
        if _post_schema_table_names(relations) is None:
            # Do not issue a single per-table query against a foreign schema.
            raise RuntimeError("fullpath_f2_post_schema_table_manifest_mismatch")
        counts: dict[str, int] = {}
        for name in sorted(POST_SCHEMA_TABLES):
            # Static identifier (only [a-z0-9_] names from code manifest).
            row = conn.execute(
                f'SELECT COUNT(*) AS row_count FROM public."{name}"'
            ).fetchone()
            if (
                not isinstance(row, Mapping)
                or type(row.get("row_count")) is not int
                or row["row_count"] < 0
            ):
                raise RuntimeError("fullpath_f2_post_schema_row_count_unreadable")
            counts[name] = row["row_count"]
    return {
        "database_name": identity["database_name"],
        "database_role": identity["database_role"],
        "is_superuser": identity["is_superuser"],
        "peer_session_count": identity["peer_session_count"],
        "user_function_count": identity["user_function_count"],
        "observed_tables": sorted(POST_SCHEMA_TABLES),
        "table_counts": counts,
    }


def assess_post_schema_table_snapshot(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    """Source-shape check only: even a perfect catalog NEVER grants startup."""
    source = snapshot if isinstance(snapshot, Mapping) else {}
    actual = source.get("observed_tables")
    counts = source.get("table_counts")
    checks = {
        "dedicated_unprivileged_f2_identity": _post_schema_identity_valid(source),
        "exact_public_runtime_base_tables": (
            isinstance(actual, list)
            and len(actual) == len(POST_SCHEMA_TABLES)
            and all(isinstance(name, str) for name in actual)
            and len(actual) == len(set(actual))
            and set(actual) == POST_SCHEMA_TABLES
        ),
        "every_runtime_table_empty": (
            isinstance(counts, Mapping)
            and set(counts) == POST_SCHEMA_TABLES
            and all(type(value) is int and value == 0 for value in counts.values())
        ),
    }
    return {
        "status": "STOP",
        "phase": "g0_f2d02_full_post_schema_table_inventory_source_only",
        "source_snapshot_valid": all(checks.values()),
        "checks": checks,
        "runtime_table_count": len(POST_SCHEMA_TABLES),
        "new_resources_created": 0,
        "model_calls_this_command": 0,
        "bootstrap_phase_evidence_independently_verified": False,
        "non_table_schema_objects_and_privileges_verified": False,
        "new_resource_volume_and_single_writer_verified": False,
        "full_runtime_start_allowed": False,
        "ready_to_dispatch": False,
        "blockers": (
            [f"invalid_{key}" for key, good in checks.items() if not good]
            + [
                "schema_migration_and_role_grants_not_approved_or_executed",
                "non_table_indexes_sequences_functions_and_grants_not_attested",
                "independent_new_db_volume_and_ownership_not_attested",
                "safe_normal_runtime_without_host_global_effects_not_proven",
                "fixture_provider_egress_ci_and_owner_activation_missing",
            ]
        ),
    }
