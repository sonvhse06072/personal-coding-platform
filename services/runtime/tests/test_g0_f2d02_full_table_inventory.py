"""F2d-02 read-only complete table inventory, without a real database.

No Runtime, Docker, credentials, model, GitHub API or host state is touched.
The final decision remains STOP even when all synthetic counts are zero.
"""
from __future__ import annotations

import re

import pytest

from app import (
    control_actions, job_status_publisher, plan_orchestrator,
    plan_progress_store, pm_bridge, pm_chat_review, pm_control,
    pm_late_review, pm_merge_audit, quota_telemetry, storage,
    telemetry_storage,
)
from app import fullpath_fresh_startup as f2


DDL_SOURCES = {
    "storage": storage.DDL,
    "plan_orchestrator": plan_orchestrator.ORCHESTRATOR_DDL,
    "plan_progress_store": plan_progress_store.DDL,
    "control_actions": control_actions.CONTROL_DDL,
    "telemetry_storage": telemetry_storage.TELEMETRY_DDL,
    "job_status_publisher": job_status_publisher.DDL,
    "pm_bridge": pm_bridge.BRIDGE_DDL,
    "pm_control": pm_control.CONTROL_DDL,
    "pm_late_review": pm_late_review.LATE_REVIEW_DDL,
    "pm_merge_audit": pm_merge_audit.PM_MERGE_AUDIT_DDL,
    "pm_chat_review": pm_chat_review.PM_CHAT_REVIEW_DDL,
    "quota_telemetry": quota_telemetry.DDL,
}
F2_URL = "postgresql://fullpath:private@fullpath-db:5432/fullpath"


def identity():
    return {
        "database_name": "fullpath", "database_role": "fullpath",
        "is_superuser": "off", "peer_session_count": 0,
        "user_function_count": 0,
    }


def relations():
    return [
        {
            "schema_name": "public", "table_name": name,
            "relation_kind": "r",
        }
        for name in sorted(f2.POST_SCHEMA_TABLES)
    ]


class Cursor:
    def __init__(self, *, one=None, many=None):
        self.one = one
        self.many = many

    def fetchone(self):
        return self.one

    def fetchall(self):
        return self.many


class FakeConnection:
    def __init__(self, *, metadata=None, observed=None, counts=None):
        self.metadata = identity() if metadata is None else metadata
        self.observed = relations() if observed is None else observed
        self.counts = (
            {name: 0 for name in f2.POST_SCHEMA_TABLES}
            if counts is None else counts
        )
        self.queries = []

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def execute(self, query):
        self.queries.append(query)
        if query == f2.POST_SCHEMA_READ_ONLY_TXN:
            return Cursor()
        if query == f2.POST_SCHEMA_IDENTITY_SQL:
            return Cursor(one=self.metadata)
        if query == f2.POST_SCHEMA_RELATIONS_SQL:
            return Cursor(many=self.observed)
        prefix = 'SELECT COUNT(*) AS row_count FROM public."'
        if query.startswith(prefix) and query.endswith('"'):
            name = query[len(prefix):-1]
            assert name in f2.POST_SCHEMA_TABLES
            assert query == f'{prefix}{name}"'
            return Cursor(one={"row_count": self.counts.get(name)})
        raise AssertionError("Non-read-only or unreviewed SQL attempted: " + query[:120])


def test_complete_manifest_matches_all_reviewed_runtime_ddl_sources():
    assert set(DDL_SOURCES) == set(f2.POST_SCHEMA_TABLE_SOURCES)
    assert len(f2.POST_SCHEMA_TABLES) == 25
    source_names = []
    for source, sql in DDL_SOURCES.items():
        declared = re.findall(
            r"\bCREATE TABLE IF NOT EXISTS\s+(cp_[a-z0-9_]+)\s*\(",
            sql,
        )
        assert len(declared) == len(set(declared))
        assert set(declared) == set(f2.POST_SCHEMA_TABLE_SOURCES[source])
        source_names.extend(declared)
    assert len(source_names) == len(set(source_names))
    assert set(source_names) == f2.POST_SCHEMA_TABLES
    # Existing "DDL" strings are NOT safe schema-only migration scripts.
    assert "INSERT INTO cp_plan_progress_meta" in plan_progress_store.DDL
    assert "UPDATE cp_control_actions" in control_actions.CONTROL_DDL


def test_full_readonly_inventory_uses_one_snapshot_and_only_static_selects():
    conn = FakeConnection()
    called = []
    observed = f2.read_only_post_schema_table_snapshot(
        database_url=F2_URL,
        connect=lambda: (called.append("connected"), conn)[1],
    )
    assert called == ["connected"]
    assert observed["table_counts"] == {name: 0 for name in f2.POST_SCHEMA_TABLES}
    assert observed["observed_tables"] == sorted(f2.POST_SCHEMA_TABLES)
    assert conn.queries[:3] == [
        f2.POST_SCHEMA_READ_ONLY_TXN,
        f2.POST_SCHEMA_IDENTITY_SQL,
        f2.POST_SCHEMA_RELATIONS_SQL,
    ]
    assert len(conn.queries) == 3 + 25
    assert all(q.startswith("SELECT COUNT(*) AS row_count FROM public.")
               for q in conn.queries[3:])
    verdict = f2.assess_post_schema_table_snapshot(observed)
    assert verdict["source_snapshot_valid"] is True
    assert verdict["runtime_table_count"] == 25
    assert verdict["status"] == "STOP"
    assert verdict["full_runtime_start_allowed"] is False
    assert verdict["ready_to_dispatch"] is False
    assert verdict["bootstrap_phase_evidence_independently_verified"] is False
    assert verdict["non_table_schema_objects_and_privileges_verified"] is False
    assert verdict["new_resource_volume_and_single_writer_verified"] is False
    assert verdict["model_calls_this_command"] == 0
    assert verdict["new_resources_created"] == 0


@pytest.mark.parametrize("dsn", [
    "postgresql://postgres:p@db:5432/pcp",
    "postgresql://fullpath:p@localhost:5432/fullpath",
    "postgresql://fullpath:p@fullpath-db:5432/legacy",
    "postgresql://fullpath:p@fullpath-db:5433/fullpath",
    "postgresql://fullpath:p@fullpath-db:5432/fullpath?sslmode=disable",
    "sqlite:///tmp/old.db", "",
])
def test_foreign_database_is_denied_before_connect(dsn):
    called = []
    with pytest.raises(RuntimeError, match="not_owned"):
        f2.read_only_post_schema_table_snapshot(
            database_url=dsn, connect=lambda: called.append("connected"),
        )
    assert called == []


@pytest.mark.parametrize("key,value", [
    ("database_name", "pcp"), ("database_role", "postgres"),
    ("is_superuser", "on"), ("is_superuser", False),
    ("peer_session_count", 1), ("peer_session_count", "0"),
    ("user_function_count", 1), ("user_function_count", None),
])
def test_wrong_identity_denied_before_any_catalog_or_count(key, value):
    data = identity()
    data[key] = value
    conn = FakeConnection(metadata=data)
    with pytest.raises(RuntimeError, match="identity_not_trusted"):
        f2.read_only_post_schema_table_snapshot(
            database_url=F2_URL, connect=lambda: conn,
        )
    assert conn.queries == [
        f2.POST_SCHEMA_READ_ONLY_TXN, f2.POST_SCHEMA_IDENTITY_SQL,
    ]


@pytest.mark.parametrize("operation", [
    lambda rows: rows.pop(),
    lambda rows: rows.append({**rows[0], "table_name": "cp_foreign_job"}),
    lambda rows: rows.append(dict(rows[0])),
    lambda rows: rows[0].update(schema_name="private"),
    lambda rows: rows[0].update(relation_kind="v"),
    lambda rows: rows[0].update(relation_kind="p"),
])
def test_missing_foreign_duplicate_nonpublic_or_view_denied_before_count(operation):
    rows = relations()
    operation(rows)
    conn = FakeConnection(observed=rows)
    with pytest.raises(RuntimeError, match="table_manifest_mismatch"):
        f2.read_only_post_schema_table_snapshot(
            database_url=F2_URL, connect=lambda: conn,
        )
    assert conn.queries == [
        f2.POST_SCHEMA_READ_ONLY_TXN,
        f2.POST_SCHEMA_IDENTITY_SQL,
        f2.POST_SCHEMA_RELATIONS_SQL,
    ]


@pytest.mark.parametrize("value", [1, -1, "0", True, None])
def test_nonempty_or_untyped_checkpoint_table_never_qualifies(value):
    counts = {name: 0 for name in f2.POST_SCHEMA_TABLES}
    counts["cp_plan_work_order_checkpoints"] = value
    conn = FakeConnection(counts=counts)
    if type(value) is not int or value < 0:
        with pytest.raises(RuntimeError, match="row_count_unreadable"):
            f2.read_only_post_schema_table_snapshot(
                database_url=F2_URL, connect=lambda: conn,
            )
    else:
        snapshot = f2.read_only_post_schema_table_snapshot(
            database_url=F2_URL, connect=lambda: conn,
        )
        verdict = f2.assess_post_schema_table_snapshot(snapshot)
        assert verdict["source_snapshot_valid"] is False
        assert verdict["checks"]["every_runtime_table_empty"] is False
        assert verdict["status"] == "STOP"


@pytest.mark.parametrize("change", [
    lambda x: x["observed_tables"].append("cp_foreign_job"),
    lambda x: x["observed_tables"].pop(),
    lambda x: x["table_counts"].pop("cp_job_events"),
    lambda x: x["table_counts"].update(cp_pm_merge_audit=1),
    lambda x: x["table_counts"].update(cp_jobs=False),
    lambda x: x.update(database_role="fullpath_bootstrap_admin"),
    lambda x: x.update(peer_session_count=1),
])
def test_pure_assessor_fails_closed_on_partial_or_foreign_report(change):
    snapshot = {
        **identity(),
        "observed_tables": sorted(f2.POST_SCHEMA_TABLES),
        "table_counts": {name: 0 for name in f2.POST_SCHEMA_TABLES},
    }
    change(snapshot)
    result = f2.assess_post_schema_table_snapshot(snapshot)
    assert result["status"] == "STOP"
    assert result["source_snapshot_valid"] is False
    assert result["ready_to_dispatch"] is False
