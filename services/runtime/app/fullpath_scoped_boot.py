"""F2c/F2d source-only first-boot decisions for the existing PCP RuntimeEngine.

This is an admission/effect *plan*, not an executable startup token. It cannot
release the parked F2 Compose, create a database, schedule work or call a model.
An independently verified resource-owner gate must precede any real bootstrap.
"""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .fullpath_fixture_safety import (
    PROJECT_ID, parked_fullpath_environment,
)
from .fullpath_fresh_startup import assess_fresh_fullpath_startup


# These are durable resource families, not a list of data to delete/replay.
# A first boot that finds ANY existing row is not a clean F2 cohort.
FRESH_INVENTORY = (
    "jobs",
    "execution_plans",
    "plan_orchestrations",
    "work_orders",
    "project_leases",
    "previews",
    "pending_controls",
    "notifications",
    "provider_runs",
)

# Negative behavioral contract for the first *direct-intake* vertical slice.
# Do not fabricate an orchestration plan merely to claim full-product parity.
FORBIDDEN_STARTUP_EFFECTS = (
    "cancel_all_antigravity_runs",
    "replay_queued_jobs",
    "interrupt_or_cancel_existing_jobs",
    "reconcile_legacy_project_leases",
    "restore_or_retire_existing_previews",
    "plan_orchestrator_tick_or_recovery",
    "provider_model_dispatch",
    "foreign_project_git_or_ddev_action",
)


def assess_scoped_fresh_boot(
    *,
    environment: Mapping[str, str],
    database_snapshot: Mapping[str, Any],
    projects_document: Mapping[str, Any],
    baselines_document: Mapping[str, Any],
    inventory: Mapping[str, Any],
    post_schema_database_snapshot: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Return a deterministic source-only STOP with explicit negative proof.

    A pristine pre-schema catalog and a populated post-schema catalog CANNOT
    be the same snapshot. Inventory is meaningful only after the schema exists.
    Both snapshots are caller-provided source shapes, NOT independent proof of
    a live migration, resource ownership, role grants or exact schema objects.
    The function cannot authorize startup or call Postgres.
    """
    safe_env = environment if isinstance(environment, Mapping) else {}
    safe_db = database_snapshot if isinstance(database_snapshot, Mapping) else {}
    post_db = (
        post_schema_database_snapshot
        if isinstance(post_schema_database_snapshot, Mapping) else {}
    )
    safe_projects = projects_document if isinstance(projects_document, Mapping) else {}
    safe_baselines = baselines_document if isinstance(baselines_document, Mapping) else {}
    db = assess_fresh_fullpath_startup(
        safe_db, safe_projects, safe_baselines,
    )
    counts: dict[str, int | None] = {}
    safe_inventory = inventory if isinstance(inventory, Mapping) else {}
    for name in FRESH_INVENTORY:
        value = safe_inventory.get(name)
        counts[name] = (
            value if type(value) is int and value >= 0 else None
        )
    checks: dict[str, bool] = {
        "parked_f2_identity": (
            safe_env.get("PCP_FULLPATH_SOURCE_ONLY") == "true"
            and safe_env.get("CODING_PROJECTS_ROOT") == "/fullpath/sources"
            and safe_env.get("CODING_WORKSPACES_ROOT") == "/fullpath/workspaces"
            and safe_env.get("CODEX_HOME") == "/home/coder/.codex-fullpath"
            and safe_env.get("PCP_RUNTIME_STARTUP_MODE")
            in {"g0_fullpath_candidate", "normal"}
            and parked_fullpath_environment(safe_env)
        ),
        "fresh_non_superuser_catalog": (
            db.get("source_snapshot_valid") is True
            and db.get("checks", {}).get(
                "dedicated_fresh_database_and_unprivileged_role"
            ) is True
            and db.get("checks", {}).get(
                "pristine_database_objects_and_no_peer_connections"
            ) is True
        ),
        "singleton_parked_fixture_only": (
            db.get("checks", {}).get(
                "one_isolated_fixture_no_direct_or_ddev"
            ) is True
            and db.get("checks", {}).get(
                "original_source_still_not_approved"
            ) is True
            and set(safe_projects.get("projects") or {}) == {PROJECT_ID}
            and set(safe_baselines.get("projects") or {}) == {PROJECT_ID}
        ),
        "post_schema_catalog_is_distinct_and_unprivileged": (
            post_db.get("database_name") == safe_db.get("database_name") == "fullpath"
            and post_db.get("database_role") == safe_db.get("database_role") == "fullpath"
            and post_db.get("is_superuser") == safe_db.get("is_superuser") == "off"
            # A real fresh DB has zero user relations before installation;
            # after installation it has tables. A synthetic inventory paired
            # with the *same* pristine catalog is not evidence of a boot.
            and type(safe_db.get("user_relation_count")) is int
            and safe_db["user_relation_count"] == 0
            and type(post_db.get("user_relation_count")) is int
            and post_db["user_relation_count"] > 0
            and type(post_db.get("user_function_count")) is int
            and post_db["user_function_count"] >= 0
            and type(post_db.get("peer_session_count")) is int
            and post_db["peer_session_count"] == 0
        ),
        "every_durable_family_known_and_empty": (
            isinstance(inventory, Mapping)
            and set(inventory) == set(FRESH_INVENTORY)
            and all(count == 0 for count in counts.values())
        ),
    }
    valid = all(checks.values())
    return {
        "status": "STOP",
        "phase": "g0_f2c_scoped_normal_startup_source_only",
        "project_id": PROJECT_ID,
        "source_contract_valid": valid,
        "checks": checks,
        "inventory_counts": counts,
        "pre_schema_user_relation_count": safe_db.get("user_relation_count"),
        "post_schema_user_relation_count": post_db.get("user_relation_count"),
        "bootstrap_phase_evidence_independently_verified": False,
        "post_schema_owned_object_allowlist_verified": False,
        "forbidden_effects": list(FORBIDDEN_STARTUP_EFFECTS),
        "proposed_direct_intake_worker_only": True,
        "proposed_planner_and_work_order_launch": False,
        "same_existing_runtime_engine": True,
        "startup_authorized": False,
        "ready_to_dispatch": False,
        "model_calls_this_command": 0,
        "new_resources_created": 0,
        "blockers": (
            [f"invalid_{name}" for name, good in checks.items() if not good]
            + [
                "fresh_db_inventory_only_synthetic_no_live_ownership_proof",
                "normal_engine_scoped_boot_not_operationally_authorized",
                "runtime_legacy_host_cancel_and_replay_not_enabled_in_f2",
                "new_approved_fixture_and_real_ci_delivery_credentials_missing",
                "oci_digest_provider_egress_and_single_writer_unverified",
                "two_stage_bootstrap_provenance_and_schema_allowlist_missing",
                "app_role_grants_and_schema_install_order_unverified",
            ]
        ),
    }
