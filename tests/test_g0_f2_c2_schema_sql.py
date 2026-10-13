"""F2 C2 real-schema SQL bundle — no Docker, DB or model use in CI."""
from __future__ import annotations

from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/g0-f2-c2-schema-sql.py"
SPEC = importlib.util.spec_from_file_location("f2_c2_schema_sql", SCRIPT)
schema = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(schema)


def test_actual_reviewed_runtime_sql_is_bundleable_without_imports_or_io():
    bundle, counts = schema.bundle()
    assert counts == {
        "tables": 25, "indexes": 24, "alters": 22, "quarantined_dml": 3,
    }
    assert bundle.startswith("-- C2 ONLY:")
    assert bundle.endswith("COMMIT;\n")
    assert len(schema.reviewed_statements(*_inputs())[0]) == 71
    assert "UPDATE cp_control_actions SET generation_fingerprint" not in bundle
    assert "INSERT INTO cp_plan_progress_meta(singleton)" not in bundle
    assert "UPDATE cp_pm_control_events SET updated_at" not in bundle
    assert "UPDATE cp_execution_plans" not in bundle
    assert "cancel_all_antigravity_runs" not in bundle
    assert "GRANT SELECT, INSERT, UPDATE, DELETE" in bundle
    assert "GRANT USAGE, SELECT ON ALL SEQUENCES" in bundle
    assert "DO $f2_guard$" in bundle
    assert "RANDOM" not in bundle
    assert bundle.count("CREATE TABLE IF NOT EXISTS cp_") == 25


def _inputs():
    sources, pin, tables = schema.pinned_inputs()
    return sources, pin, tables


def test_cli_check_only_emits_counts_and_cannot_contact_host():
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--check"], cwd=ROOT,
        check=True, text=True, capture_output=True,
    )
    data = json.loads(result.stdout)
    assert data["status"] == "SOURCE_READY_NOT_APPLIED"
    assert data["database_writes"] == 0
    assert data["activation_authorized"] is False
    assert data["statements"] == 71
    assert len(data["sha256"]) == 64
    assert "CREATE TABLE" not in result.stdout


def test_pinned_sources_and_schema_allowlist_are_complete():
    sources, pins, tables = _inputs()
    assert list(sources) == list(pins) == list(schema.SOURCE_FIELDS)
    assert len(pins) == 12
    assert len(tables) == 25
    assert "cp_jobs" in tables and "cp_plan_work_orders" in tables


@pytest.mark.parametrize("module", list(schema.SOURCE_FIELDS))
def test_any_source_drift_rejected_before_any_sql_output(module):
    sources, pins, tables = _inputs()
    sources[module] += "\n"
    with pytest.raises(schema.C2Stop, match="pinned_sql_digest_mismatch"):
        schema.reviewed_statements(sources, pins, tables)


@pytest.mark.parametrize("unsafe", [
    "UPDATE cp_jobs SET status='completed';",
    "DELETE FROM cp_jobs;",
    "DROP TABLE cp_jobs;",
    "CREATE ROLE foreign SUPERUSER;",
    "GRANT ALL ON ALL TABLES IN SCHEMA public TO fullpath;",
])
def test_unapproved_extra_sql_rejected_even_before_manifest_counts(unsafe):
    sources, pins, tables = _inputs()
    sources["storage"] += unsafe
    # Existing SHA pins force STOP before even classifying this statement.
    with pytest.raises(schema.C2Stop, match="pinned_sql_digest_mismatch"):
        schema.reviewed_statements(sources, pins, tables)


def test_duplicate_source_paths_or_missing_tables_fail_closed():
    sources, pins, tables = _inputs()
    with pytest.raises(schema.C2Stop):
        schema.reviewed_statements(sources, pins, tables - {"cp_jobs"})
    with pytest.raises(schema.C2Stop):
        schema.reviewed_statements(sources, {**pins, "foreign": "a" * 64}, tables)


def test_emitted_sql_has_no_secret_runtime_connection_or_non_f2_command():
    text, _ = schema.bundle()
    assert "GITHUB_DELIVERY_TOKEN" not in text
    assert "POSTGRES_PASSWORD" not in text
    assert "/var/run/docker.sock" not in text
    assert "docker " not in text
    assert "/home/sonvh/chonhac" not in text
    assert "CREATE ROLE " not in text
    assert text.count("BEGIN;") == 1 and text.count("COMMIT;") == 1
