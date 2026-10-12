"""F2d-03: SOURCE-ONLY audit of a possible fresh F2 schema bootstrap.

This module cannot create a database, run migration SQL, grant roles, authorize
Runtime startup, or call a provider. It intentionally returns STOP forever.
Existing legacy init/ensure methods are NOT safe for fresh F2 bootstrap.
"""
from __future__ import annotations

from collections.abc import Mapping
from hashlib import sha256
import re
from typing import Any

from . import (
    control_actions, job_status_publisher, plan_orchestrator,
    plan_progress_store, pm_bridge, pm_chat_review, pm_control,
    pm_late_review, pm_merge_audit, quota_telemetry, storage,
    telemetry_storage,
)
from .fullpath_fresh_startup import POST_SCHEMA_TABLE_SOURCES, POST_SCHEMA_TABLES


# Source-exact SHA256 of the twelve original DDL string values on PCP main
# cc1833271a5ff16869bd8a9ebd3e22045c847e5f, NOT of the entire Python files.
# Any SQL drift requires a newly reviewed source contract. These are NOT
# approval signatures, migration authorization, or runtime ownership proof.
SOURCE_DDL_SHA256 = {
    "storage": "154f0dfa1f9c465bcdd8035714507dbfa5e403d51893e47aaae81fb0022f1dc4",
    "plan_orchestrator": "0222d3df20b97ba9db7b810b4318d0d82102b0be896c689635879fe543a2655f",
    "telemetry_storage": "526c649bd06297dc5a609da387491f5cc5345d1f3dd2c915fa6e43483aa3b699",
    "control_actions": "d3c0308fdce50e0b95061056b65e7ed20d75cba60241d443dc82e106a9c03033",
    "plan_progress_store": "0170283f050a0a767f18aebd00b709afd5393f2f7c35bd070a7b9174ae87167d",
    "job_status_publisher": "ad7b98ad937bee289aeaf6c4f654c0afe0410b1075004b802ce8bd514c165994",
    "pm_bridge": "043924ff1cba6eac0081b22ef8de9ba38216b94d6194570c1227a1cd295a8df0",
    "pm_control": "f62ce92247e85b5b4d56bc5d954e8394992d5a162e22050fb2fd28ccf99b1680",
    "pm_late_review": "459a4679500e6df055e8ad156ba34facaa7987e753a28cdc492a3960a80e7c42",
    "pm_merge_audit": "190294b3414832edae134020ab8116b3bde6f68b351abd3c1e809f4bf335f255",
    "pm_chat_review": "41431d3ae74a59ce127e1d99753566b33ef70e6b24ebe195aaa45f490b41169d",
    "quota_telemetry": "fa835751597b4b148282fb51bcde5ae1984f7d221e6c4f884eb9ac11d8fdf041",
}
# Dependency order is deliberately explicit. Storage precedes all FKs to jobs;
# the plan-work-order parent precedes its checkpoint table.
SCHEMA_SOURCE_ORDER = tuple(SOURCE_DDL_SHA256)

# Only these exact DML statements are excluded from the hypothetical FRESH
# schema-only phase. Historical upgrades cannot safely omit backfill DML.
# The names/SQL are pinned by SOURCE_DDL_SHA256 before this list is considered.
QUARANTINED_FRESH_DML = {
    "control_actions": frozenset({
        "UPDATE cp_control_actions SET generation_fingerprint=state_fingerprint WHERE generation_fingerprint IS NULL",
    }),
    "plan_progress_store": frozenset({
        "INSERT INTO cp_plan_progress_meta(singleton) VALUES (TRUE) ON CONFLICT DO NOTHING",
    }),
    "pm_control": frozenset({
        "UPDATE cp_pm_control_events SET updated_at=created_at WHERE updated_at IS NULL",
    }),
}


def current_ddl_sources() -> dict[str, str]:
    """Read Python constants only; no filesystem, DB, SQL execution or I/O."""
    return {
        "storage": storage.DDL,
        "plan_orchestrator": plan_orchestrator.ORCHESTRATOR_DDL,
        "telemetry_storage": telemetry_storage.TELEMETRY_DDL,
        "control_actions": control_actions.CONTROL_DDL,
        "plan_progress_store": plan_progress_store.DDL,
        "job_status_publisher": job_status_publisher.DDL,
        "pm_bridge": pm_bridge.BRIDGE_DDL,
        "pm_control": pm_control.CONTROL_DDL,
        "pm_late_review": pm_late_review.LATE_REVIEW_DDL,
        "pm_merge_audit": pm_merge_audit.PM_MERGE_AUDIT_DDL,
        "pm_chat_review": pm_chat_review.PM_CHAT_REVIEW_DDL,
        "quota_telemetry": quota_telemetry.DDL,
    }


def _normalize(stmt: str) -> str:
    return " ".join(stmt.split())


def _analyze_pinned_ddl(sources: Mapping[str, str]) -> dict[str, Any]:
    """Analyze reviewed SQL strings without returning executable statements.

    The exact full-string SHA gate must pass before a semicolon split is valid.
    No new SQL parser or untrusted DDL syntax is accepted by this audit.
    """
    if (
        not isinstance(sources, Mapping)
        or set(sources) != set(SOURCE_DDL_SHA256)
        or set(SOURCE_DDL_SHA256) != set(POST_SCHEMA_TABLE_SOURCES)
    ):
        return {"trusted": False, "reason": "source_module_set_mismatch"}
    for name in SCHEMA_SOURCE_ORDER:
        sql = sources.get(name)
        if (
            not isinstance(sql, str)
            or sha256(sql.encode("utf-8")).hexdigest() != SOURCE_DDL_SHA256[name]
        ):
            return {"trusted": False, "reason": "source_sql_digest_mismatch"}

    tables: set[str] = set()
    indexes: set[str] = set()
    counts = {"tables": 0, "indexes": 0, "alters": 0, "quarantined_dml": 0}
    quarantined: set[tuple[str, str]] = set()
    for source_name in SCHEMA_SOURCE_ORDER:
        sql = sources[source_name]
        # Pinned current inputs contain only bare SQL statements separated by
        # semicolons. If an unfamiliar source is introduced, fail closed.
        statements = [_normalize(x) for x in sql.split(";") if x.strip()]
        if not statements:
            return {"trusted": False, "reason": "source_sql_empty"}
        for stmt in statements:
            if "--" in stmt or "/*" in stmt or "*/" in stmt:
                return {"trusted": False, "reason": "source_sql_comments_not_reviewed"}
            if stmt in QUARANTINED_FRESH_DML.get(source_name, frozenset()):
                if (source_name, stmt) in quarantined:
                    return {"trusted": False, "reason": "duplicate_quarantined_dml"}
                quarantined.add((source_name, stmt))
                counts["quarantined_dml"] += 1
                continue
            table = re.match(
                r"^CREATE TABLE IF NOT EXISTS (cp_[a-z0-9_]+) \(",
                stmt,
            )
            index = re.match(
                r"^CREATE (?:UNIQUE )?INDEX IF NOT EXISTS (cp_[a-z0-9_]+) "
                r"ON (cp_[a-z0-9_]+)\(",
                stmt,
            )
            alter = re.match(
                r"^ALTER TABLE (cp_[a-z0-9_]+) "
                r"(?:ADD COLUMN IF NOT EXISTS [a-z_][a-z0-9_]* .+|"
                r"ALTER COLUMN [a-z_][a-z0-9_]* SET NOT NULL)$",
                stmt,
            )
            if table:
                name = table[1]
                if name in tables or name not in POST_SCHEMA_TABLES:
                    return {"trusted": False, "reason": "unknown_or_duplicate_table"}
                # All current foreign keys must reference an already installed
                # table. Do not depend on old schema state to satisfy them.
                refs = re.findall(r"\bREFERENCES (cp_[a-z0-9_]+)\s*\(", stmt)
                if any(ref not in tables for ref in refs):
                    return {"trusted": False, "reason": "foreign_key_out_of_order"}
                tables.add(name)
                counts["tables"] += 1
            elif index:
                name, owner = index.groups()
                if name in indexes or owner not in tables:
                    return {"trusted": False, "reason": "index_owner_or_duplicate"}
                indexes.add(name)
                counts["indexes"] += 1
            elif alter:
                if alter[1] not in tables:
                    return {"trusted": False, "reason": "alter_before_table"}
                counts["alters"] += 1
            else:
                return {"trusted": False, "reason": "unapproved_sql_statement"}
    expected_omitted = {
        (source, stmt)
        for source, entries in QUARANTINED_FRESH_DML.items()
        for stmt in entries
    }
    valid = (
        tables == POST_SCHEMA_TABLES
        and quarantined == expected_omitted
        and counts == {
            "tables": 25, "indexes": 24, "alters": 22, "quarantined_dml": 3,
        }
    )
    return {
        "trusted": valid,
        "reason": "pinned_schema_shape_pass" if valid else "schema_shape_mismatch",
        "counts": counts,
        "validated_tables": len(tables),
        "validated_index_declarations": len(indexes),
        # Nothing here proves actual PostgreSQL execution, permissions,
        # function/trigger/sequence catalog, order of normal init calls, etc.
    }


def assess_schema_bootstrap_source(
    sources: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Return SOURCE-ONLY evidence. It cannot activate or execute a migration."""
    parsed = _analyze_pinned_ddl(
        current_ddl_sources() if sources is None else sources
    )
    checks = {
        "pinned_ddl_and_static_schema_order": parsed.get("trusted") is True,
        "source_ddl_fresh_only_and_dml_quarantined": parsed.get("trusted") is True,
        "all_25_tables_and_24_index_declarations_accounted": (
            parsed.get("trusted") is True
            and parsed.get("validated_tables") == 25
            and parsed.get("validated_index_declarations") == 24
        ),
    }
    return {
        "status": "STOP",
        "phase": "g0_f2d03_schema_only_source_audit",
        "source_contract_valid": all(checks.values()),
        "checks": checks,
        "audit_reason": parsed.get("reason"),
        "statement_counts": parsed.get("counts"),
        "would_install_schema": False,
        "executable_sql_generated": False,
        "fresh_bootstrap_role_or_schema_grants_verified": False,
        "post_schema_indexes_sequences_triggers_grants_verified": False,
        "f2_volume_and_single_writer_verified": False,
        "safe_scoped_normal_engine_boot_proven": False,
        "startup_authorized": False,
        "ready_to_dispatch": False,
        "model_calls_this_command": 0,
        "new_resources_created": 0,
        "blockers": (
            [f"source_{key}" for key, good in checks.items() if not good]
            + [
                "independent_new_fixture_and_approved_baseline_missing",
                "fresh_database_volume_role_and_schema_installer_not_provisioned",
                "fresh_only_sql_would_need_separate_owner_approved_migration",
                "actual_indexes_sequences_triggers_grants_not_attested",
                "runtime_init_and_ensure_data_side_effects_not_isolated",
                "provider_egress_github_delivery_and_no_global_cancel_unproven",
                "independent_owner_operational_approval_missing",
            ]
        ),
    }
