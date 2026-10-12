"""F2d-03 pinned source-only schema audit; no real PostgreSQL or migration.

The audit refuses new/modified SQL instead of dynamically relaxing bootstrap
rules. Synthetic success NEVER authorizes any operational action.
"""
from __future__ import annotations

from copy import deepcopy
import inspect

import pytest

from app import fullpath_schema_bootstrap_source as audit
from app import (
    control_actions, plan_orchestrator, plan_progress_store, pm_control, storage,
)


def test_reviewed_schema_and_dml_are_completely_accounted_for():
    sources = audit.current_ddl_sources()
    before = deepcopy(sources)
    result = audit.assess_schema_bootstrap_source(sources)
    assert len(sources) == len(audit.SCHEMA_SOURCE_ORDER) == 12
    assert set(sources) == set(audit.SOURCE_DDL_SHA256)
    assert set(sources) == set(audit.POST_SCHEMA_TABLE_SOURCES)
    assert result["source_contract_valid"] is True
    assert all(result["checks"].values())
    assert result["audit_reason"] == "pinned_schema_shape_pass"
    assert result["statement_counts"] == {
        "tables": 25,
        "indexes": 24,
        "alters": 22,
        "quarantined_dml": 3,
    }
    assert result["would_install_schema"] is False
    assert result["executable_sql_generated"] is False
    assert result["status"] == "STOP"
    assert result["startup_authorized"] is False
    assert result["ready_to_dispatch"] is False
    assert result["fresh_bootstrap_role_or_schema_grants_verified"] is False
    assert result["safe_scoped_normal_engine_boot_proven"] is False
    assert result["new_resources_created"] == 0
    assert result["model_calls_this_command"] == 0
    assert sources == before


def test_pin_is_complete_and_each_sha_has_exact_64_lower_hex_chars():
    assert len(audit.SOURCE_DDL_SHA256) == 12
    assert len(set(audit.SOURCE_DDL_SHA256.values())) == 12
    assert all(len(h) == 64 and h == h.lower() and
               all(c in "0123456789abcdef" for c in h)
               for h in audit.SOURCE_DDL_SHA256.values())
    assert audit.SCHEMA_SOURCE_ORDER[0] == "storage"
    assert audit.SCHEMA_SOURCE_ORDER.index("plan_orchestrator") < (
        audit.SCHEMA_SOURCE_ORDER.index("plan_progress_store")
    )


@pytest.mark.parametrize("source_name", audit.SCHEMA_SOURCE_ORDER)
def test_any_upstream_ddl_drift_requires_new_source_review(source_name):
    sources = audit.current_ddl_sources()
    sources[source_name] += "\n"
    out = audit.assess_schema_bootstrap_source(sources)
    assert out["status"] == "STOP"
    assert out["source_contract_valid"] is False
    assert out["audit_reason"] == "source_sql_digest_mismatch"
    assert out["executable_sql_generated"] is False


@pytest.mark.parametrize("mutation", [
    lambda s: s.pop("storage"),
    lambda s: s.update(foreign_schema="CREATE TABLE cp_foreign ()"),
    lambda s: s.update(plan_orchestrator=0),
    lambda s: s.update(storage=None),
])
def test_missing_extra_or_nonstring_sql_fails_closed(mutation):
    sources = audit.current_ddl_sources()
    mutation(sources)
    out = audit.assess_schema_bootstrap_source(sources)
    assert out["source_contract_valid"] is False
    assert out["status"] == "STOP"
    assert out["startup_authorized"] is False


@pytest.mark.parametrize("extra_sql", [
    "UPDATE cp_jobs SET status='completed'",
    "INSERT INTO cp_jobs VALUES ('not-fresh')",
    "DROP TABLE cp_jobs",
    "DELETE FROM cp_jobs",
    "GRANT ALL ON ALL TABLES IN SCHEMA public TO fullpath",
    "CREATE ROLE root SUPERUSER",
    "CREATE TABLE IF NOT EXISTS cp_foreign (id INT)",
    "CREATE INDEX IF NOT EXISTS cp_unreviewed ON cp_jobs(status)",
])
def test_unapproved_mutating_or_schema_sql_is_not_silently_accepted(extra_sql):
    sources = audit.current_ddl_sources()
    sources["storage"] += extra_sql + ";"
    out = audit.assess_schema_bootstrap_source(sources)
    assert out["source_contract_valid"] is False
    assert out["status"] == "STOP"
    assert out["would_install_schema"] is False


def test_all_three_original_dml_entries_are_quarantined_and_not_backfilled():
    assert set(audit.QUARANTINED_FRESH_DML) == {
        "plan_progress_store", "control_actions", "pm_control",
    }
    assert len({sql for statements in audit.QUARANTINED_FRESH_DML.values()
                for sql in statements}) == 3
    assert "UPDATE cp_control_actions" in control_actions.CONTROL_DDL
    assert "UPDATE cp_pm_control_events" in pm_control.CONTROL_DDL
    assert "INSERT INTO cp_plan_progress_meta" in plan_progress_store.DDL
    # Legacy Storage.init and PlanOrchestratorStore.ensure still have durable
    # update/insert side effects that must not be called by fresh F2 bootstrap.
    assert "UPDATE cp_execution_plans" in inspect.getsource(
        storage.Storage._reconcile_legacy_planning_on_connection
    )
    assert "_reconcile_legacy_planning_on_connection" in inspect.getsource(
        storage.Storage.init
    )
    assert "INSERT INTO cp_plan_orchestrator_meta" in inspect.getsource(
        plan_orchestrator.PlanOrchestratorStore.ensure
    )


@pytest.mark.parametrize("override", [
    None, [], {}, {"storage": "CREATE TABLE cp_jobs();"},
])
def test_malformed_synthetic_source_never_becomes_boot_permission(override):
    out = audit.assess_schema_bootstrap_source(override)
    # None uses the approved constants; others fail the manifest.
    assert out["status"] == "STOP"
    assert out["startup_authorized"] is False
    assert out["ready_to_dispatch"] is False
    assert out["fresh_bootstrap_role_or_schema_grants_verified"] is False
    assert out["post_schema_indexes_sequences_triggers_grants_verified"] is False
    assert out["f2_volume_and_single_writer_verified"] is False
    assert out["new_resources_created"] == 0


def test_audit_never_opens_database_or_changes_legacy_runtime(monkeypatch):
    monkeypatch.setattr(
        storage.Storage, "connect",
        lambda *_a, **_kw: pytest.fail("source audit connected to a database"),
    )
    monkeypatch.setattr(
        storage.Storage, "init",
        lambda *_a, **_kw: pytest.fail("source audit ran legacy init"),
    )
    out = audit.assess_schema_bootstrap_source()
    assert out["status"] == "STOP"
    assert out["source_contract_valid"] is True
    assert "executable_sql_generated" in out
    assert not hasattr(audit, "apply_migration")
    assert not hasattr(audit, "bootstrap")
    assert not hasattr(audit, "execute_sql")
