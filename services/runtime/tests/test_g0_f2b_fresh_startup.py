"""F2b safe-start feasibility: read-only fresh database and no host side effects.

All external dependencies are synthetic. No Docker, provider, PostgreSQL,
filesystem mutations, Antigravity or existing PCP/Chợ Nhạc environment.
"""
from __future__ import annotations

import asyncio
from copy import deepcopy

import pytest

from app import fullpath_fixture_safety as parked
from app import fullpath_fresh_startup as future
from app.engine_core import RuntimeEngineCore
from app.plan_orchestrator import PlanOrchestrator as CoreOrchestrator
from app.orchestrator_merge import PlanOrchestrator as MergeOrchestrator
from app.orchestrator_notifications import PlanOrchestrator as NotificationOrchestrator
from test_g0_fullpath_source_gate import candidate


def pristine():
    return {
        "database_name": "fullpath",
        "database_role": "fullpath",
        "is_superuser": "off",
        "user_relation_count": 0,
        "user_function_count": 0,
        "peer_session_count": 0,
    }


class FakeCursor:
    def __init__(self, row):
        self.row = deepcopy(row)

    def fetchone(self):
        return deepcopy(self.row)


class FakeConnection:
    def __init__(self, row=None):
        self.row = pristine() if row is None else row
        self.queries = []

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def execute(self, query):
        self.queries.append(query)
        if query == "SET TRANSACTION READ ONLY":
            return FakeCursor(None)
        if query == future.READ_ONLY_SNAPSHOT_SQL:
            return FakeCursor(self.row)
        raise AssertionError("inspector must not execute SQL other than read only")


def test_catalog_preflight_reads_only_and_never_creates_tables():
    conn = FakeConnection()
    result = future.read_only_fresh_database_snapshot(
        database_url="postgresql://fullpath:private@fullpath-db:5432/fullpath",
        connect=lambda: conn,
    )
    assert result == pristine()
    assert conn.queries == [
        "SET TRANSACTION READ ONLY", future.READ_ONLY_SNAPSHOT_SQL,
    ]
    sql = "\n".join(conn.queries).upper()
    assert "CREATE TABLE" not in sql
    assert "UPDATE CP_" not in sql
    assert "DROP TABLE" not in sql
    assert "CANCEL" not in sql


@pytest.mark.parametrize("url", [
    "postgresql://db:pw@db:5432/db",
    "postgresql://fullpath:pw@fullpath-db:5432/legacy",
    "postgresql://superuser:pw@fullpath-db:5432/fullpath",
    "postgresql://fullpath:pw@fullpath-db:5433/fullpath",
    "postgresql://fullpath:pw@fullpath-db:5432/fullpath?schema=public",
    "postgresql://fullpath:pw@localhost:5432/fullpath",
    "sqlite:///tmp/legacy.db",
    "",
])
def test_readonly_catalog_refuses_non_f2_dsn_before_open(url):
    calls = []
    def connect():
        calls.append("opened")
        raise AssertionError("must not open a foreign DB")
    with pytest.raises(RuntimeError, match="not_owned"):
        future.read_only_fresh_database_snapshot(
            database_url=url, connect=connect,
        )
    assert calls == []


def test_clean_nonprivileged_snapshot_still_is_not_startup_permission():
    _, projects, baselines = candidate()
    before = deepcopy((projects, baselines))
    result = future.assess_fresh_fullpath_startup(
        pristine(), projects, baselines,
    )
    assert result["status"] == "STOP"
    assert result["checks"]["dedicated_fresh_database_and_unprivileged_role"]
    assert result["checks"]["pristine_database_objects_and_no_peer_connections"]
    assert result["checks"]["one_isolated_fixture_no_direct_or_ddev"]
    # In the current F2a source proposal, a new independent seed is NOT
    # approved, therefore this specific check is intentionally false until
    # the F2b inputs are the actual parked project-baselines doc.
    assert result["full_runtime_start_allowed"] is False
    assert result["model_calls_this_command"] == 0
    assert result["new_resources_created"] == 0
    assert all(result["effects_that_must_be_absent"].values())
    assert (projects, baselines) == before


@pytest.mark.parametrize("change", [
    lambda x: x.update(database_name="g0"),
    lambda x: x.update(database_role="postgres"),
    lambda x: x.update(is_superuser="on"),
    lambda x: x.update(is_superuser=True),
    lambda x: x.update(user_relation_count=1),
    lambda x: x.update(user_function_count=1),
    lambda x: x.update(peer_session_count=1),
    lambda x: x.update(peer_session_count=False),
    lambda x: x.pop("peer_session_count"),
])
def test_prior_objects_superuser_sessions_or_invalid_snapshot_never_pass(change):
    _, projects, baselines = candidate()
    row = pristine()
    change(row)
    result = future.assess_fresh_fullpath_startup(row, projects, baselines)
    assert result["source_snapshot_valid"] is False
    assert result["status"] == "STOP"
    assert result["full_runtime_start_allowed"] is False


@pytest.mark.parametrize("alter", [
    lambda p, b: p["projects"].update({"chonhac": {}}),
    lambda p, b: p["projects"][parked.PROJECT_ID].update(
        {"path": "/home/example/chonhac"}
    ),
    lambda p, b: p["projects"][parked.PROJECT_ID]["runtime"].update(
        {"workspace_mode": "direct"}
    ),
    lambda p, b: p["projects"][parked.PROJECT_ID]["ddev"].update(
        {"enabled": True}
    ),
    lambda p, b: b["projects"].update({"legacy-pcp": {}}),
])
def test_foreign_registry_and_direct_workspace_denied(alter):
    _, projects, baselines = candidate()
    alter(projects, baselines)
    result = future.assess_fresh_fullpath_startup(
        pristine(), projects, baselines,
    )
    assert result["source_snapshot_valid"] is False
    assert result["status"] == "STOP"


def test_real_parked_f2_baseline_is_not_approved_yet():
    import yaml
    from pathlib import Path

    path = Path(__file__).resolve().parents[3]
    cfg = path / "config/fullpath-candidate"
    with (cfg / "projects.yml").open(encoding="utf-8") as f:
        projects = yaml.safe_load(f)
    with (cfg / "project-baselines.yml").open(encoding="utf-8") as f:
        baselines = yaml.safe_load(f)
    result = future.assess_fresh_fullpath_startup(
        pristine(), projects, baselines,
    )
    assert result["source_snapshot_valid"] is True
    assert result["status"] == "STOP"
    assert "fixture_approved_baseline_and_owner_activation_missing" in result["blockers"]


@pytest.mark.parametrize("layer,method", [
    (CoreOrchestrator, "start"),
    (CoreOrchestrator, "tick"),
    (CoreOrchestrator, "stop"),
    (MergeOrchestrator, "start"),
    (NotificationOrchestrator, "start"),
    (NotificationOrchestrator, "tick"),
    (RuntimeEngineCore, "stop"),
    (RuntimeEngineCore, "enqueue"),
])
def test_parked_f2_direct_lifecycle_entrypoints_have_zero_db_side_effects(
    monkeypatch, layer, method,
):
    monkeypatch.setenv("PCP_RUNTIME_STARTUP_MODE", "normal")
    monkeypatch.setenv("CODING_PROJECTS_ROOT", "/fullpath/sources")
    item = object.__new__(layer)
    async def run():
        fn = getattr(item, method)
        with pytest.raises(parked.FullPathCandidateNotReady, match="source-only"):
            if method == "enqueue":
                await fn("a"*32)
            else:
                await fn()
    asyncio.run(run())


def test_unparked_normal_legacy_identity_stays_unaffected(monkeypatch):
    monkeypatch.setenv("PCP_RUNTIME_STARTUP_MODE", "normal")
    monkeypatch.delenv("PCP_FULLPATH_SOURCE_ONLY", raising=False)
    monkeypatch.setenv("CODING_PROJECTS_ROOT", "/home/owner/legacy-projects")
    monkeypatch.setenv("PROJECTS_FILE", "/config/projects.yml")
    monkeypatch.setenv("CODEX_HOME", "/home/coder/.codex")
    monkeypatch.setenv("DATABASE_URL", "postgresql://db:pw@db:5432/db")
    parked.reject_parked_fullpath_side_effects()  # No exception.


def test_pure_source_assessment_has_no_implicit_db_inspection(monkeypatch):
    def forbidden():
        raise AssertionError("no connection factory may be invoked")
    _, projects, baselines = candidate()
    assert future.assess_fresh_fullpath_startup(
        pristine(), projects, baselines,
    )["status"] == "STOP"
    # The only real inspector entrypoint requires an explicit exact F2 URI
    # and trusted connection factory.
    with pytest.raises(RuntimeError, match="not_owned"):
        future.read_only_fresh_database_snapshot(
            database_url="postgresql://postgres@db:5432/postgres",
            connect=forbidden,
        )
