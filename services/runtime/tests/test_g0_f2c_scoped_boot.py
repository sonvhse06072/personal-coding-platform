"""F2c/F2d two-phase first-boot planning with legacy Runtime behavior parity.

Synthetic-only: no PostgreSQL, Docker, provider, production workspace or GitHub.
A source-valid cohort inventory NEVER activates the parked F2 Runtime.
"""
from __future__ import annotations

import asyncio
from copy import deepcopy

import pytest

from app import fullpath_scoped_boot as f2c
from app import engine_core
from app.engine_core import RuntimeEngineCore
from app.fullpath_fixture_safety import FullPathCandidateNotReady
from test_g0_fullpath_source_gate import candidate
from test_g0_f2b_fresh_startup import pristine


def inputs():
    env, projects, baseline = candidate()
    env["PCP_FULLPATH_SOURCE_ONLY"] = "true"
    # F2 source has no approved fixture seed or operational authority.
    baseline["projects"][f2c.PROJECT_ID] = {
        "active_revision": None, "revisions": {},
    }
    inventory = {key: 0 for key in f2c.FRESH_INVENTORY}
    return env, projects, baseline, inventory


_UNSET = object()


def post_schema_catalog():
    # Synthetic representation of an independently installed *fresh* schema.
    # Its number is NOT a real schema manifest or authorization evidence.
    catalog = pristine()
    catalog["user_relation_count"] = 12
    return catalog


def assess(
    env=None, projects=None, baseline=None, inventory=_UNSET, catalog=None,
    post_catalog=_UNSET,
):
    e, p, b, i = inputs()
    return f2c.assess_scoped_fresh_boot(
        environment=e if env is None else env,
        projects_document=p if projects is None else projects,
        baselines_document=b if baseline is None else baseline,
        inventory=i if inventory is _UNSET else inventory,
        database_snapshot=pristine() if catalog is None else catalog,
        post_schema_database_snapshot=(
            post_schema_catalog() if post_catalog is _UNSET else post_catalog
        ),
    )


def test_empty_f2_catalog_and_every_inventory_family_still_stop():
    env, projects, baseline, inventory = inputs()
    saved = deepcopy((env, projects, baseline, inventory))
    outcome = assess(env, projects, baseline, inventory)
    assert outcome["status"] == "STOP"
    assert outcome["source_contract_valid"] is True
    assert all(outcome["checks"].values())
    assert outcome["proposed_direct_intake_worker_only"] is True
    assert outcome["proposed_planner_and_work_order_launch"] is False
    assert outcome["same_existing_runtime_engine"] is True
    assert outcome["startup_authorized"] is False
    assert outcome["ready_to_dispatch"] is False
    assert outcome["model_calls_this_command"] == 0
    assert outcome["new_resources_created"] == 0
    assert outcome["forbidden_effects"] == list(f2c.FORBIDDEN_STARTUP_EFFECTS)
    assert len(outcome["inventory_counts"]) == len(f2c.FRESH_INVENTORY)
    assert outcome["pre_schema_user_relation_count"] == 0
    assert outcome["post_schema_user_relation_count"] == 12
    assert outcome["bootstrap_phase_evidence_independently_verified"] is False
    assert outcome["post_schema_owned_object_allowlist_verified"] is False
    assert "two_stage_bootstrap_provenance_and_schema_allowlist_missing" in outcome["blockers"]
    assert (env, projects, baseline, inventory) == saved


@pytest.mark.parametrize("post", [None, {}, pristine(), []])
def test_same_pristine_catalog_or_missing_post_schema_cannot_prove_f2d(post):
    outcome = assess(post_catalog=post)
    assert outcome["status"] == "STOP"
    assert outcome["checks"]["post_schema_catalog_is_distinct_and_unprivileged"] is False
    assert outcome["source_contract_valid"] is False
    assert outcome["startup_authorized"] is False


@pytest.mark.parametrize("field,value", [
    ("database_name", "legacy"), ("database_role", "postgres"),
    ("is_superuser", "on"), ("user_relation_count", 0),
    ("user_relation_count", True), ("user_relation_count", "12"),
    ("user_function_count", -1), ("user_function_count", False),
    ("peer_session_count", 1), ("peer_session_count", "0"),
])
def test_post_schema_identity_privilege_or_untrusted_values_fail_closed(field, value):
    post = post_schema_catalog()
    post[field] = value
    outcome = assess(post_catalog=post)
    assert outcome["status"] == "STOP"
    assert outcome["checks"]["post_schema_catalog_is_distinct_and_unprivileged"] is False
    assert outcome["source_contract_valid"] is False


@pytest.mark.parametrize("family", f2c.FRESH_INVENTORY)
def test_one_foreign_or_preexisting_durable_row_blocks_first_start(family):
    _, _, _, inventory = inputs()
    inventory[family] = 1
    result = assess(inventory=inventory)
    assert result["status"] == "STOP"
    assert result["source_contract_valid"] is False
    assert result["checks"]["every_durable_family_known_and_empty"] is False
    assert result["inventory_counts"][family] == 1


@pytest.mark.parametrize("invalid", [
    None, {}, {"jobs": 0}, [],
    {k: 0 for k in f2c.FRESH_INVENTORY} | {"unknown_project_lease": 0},
    {k: 0 for k in f2c.FRESH_INVENTORY} | {"jobs": -1},
    {k: 0 for k in f2c.FRESH_INVENTORY} | {"jobs": False},
    {k: 0 for k in f2c.FRESH_INVENTORY} | {"jobs": "0"},
    {k: 0 for k in f2c.FRESH_INVENTORY} | {"jobs": None},
])
def test_partial_or_untyped_inventory_is_never_trusted(invalid):
    result = assess(inventory=invalid)
    assert result["status"] == "STOP"
    assert result["source_contract_valid"] is False
    assert result["checks"]["every_durable_family_known_and_empty"] is False


@pytest.mark.parametrize("key,value", [
    ("PCP_FULLPATH_SOURCE_ONLY", ""),
    ("PCP_RUNTIME_STARTUP_MODE", "g0_fixture_run"),
    ("CODING_PROJECTS_ROOT", "/home/owner/chonhac"),
    ("CODING_WORKSPACES_ROOT", "/g0/workspaces"),
    ("CODEX_HOME", "/home/owner/.codex"),
])
def test_wrong_or_unparked_environment_is_not_first_boot(key, value):
    env, _, _, _ = inputs()
    env[key] = value
    result = assess(env=env)
    assert result["status"] == "STOP"
    assert result["checks"]["parked_f2_identity"] is False


@pytest.mark.parametrize("field,value", [
    ("database_role", "postgres"), ("database_name", "legacy"),
    ("is_superuser", "on"), ("user_relation_count", 1),
    ("user_function_count", 1), ("peer_session_count", 1),
])
def test_catalog_privilege_existing_data_or_peer_blocks_source_check(field, value):
    catalog = pristine()
    catalog[field] = value
    result = assess(catalog=catalog)
    assert result["source_contract_valid"] is False
    assert result["checks"]["fresh_non_superuser_catalog"] is False


@pytest.mark.parametrize("change", [
    lambda x: x["projects"].update({"chonhac": {}}),
    lambda x: x["projects"].update({"pcp-g0-drupal-fixture": {}}),
    lambda x: x["projects"][f2c.PROJECT_ID].update(
        {"base_branch": "benchmark/pcp"}
    ),
    lambda x: x["projects"][f2c.PROJECT_ID]["runtime"].update(
        {"workspace_mode": "direct"}
    ),
])
def test_foreign_projects_or_existing_seed_cannot_be_scoped_boot(change):
    _, projects, _, _ = inputs()
    change(projects)
    result = assess(projects=projects)
    assert result["source_contract_valid"] is False


def test_any_approved_or_foreign_baseline_requires_independent_cohort():
    _, _, baseline, _ = inputs()
    baseline["projects"][f2c.PROJECT_ID]["active_revision"] = "g0d01-seed"
    baseline["projects"][f2c.PROJECT_ID]["revisions"] = {
        "g0d01-seed": {"status": "approved", "source_commit": "a" * 40}
    }
    result = assess(baseline=baseline)
    assert result["status"] == "STOP"
    assert result["checks"]["singleton_parked_fixture_only"] is False


def test_malformed_documents_fail_closed_without_exceptions():
    result = f2c.assess_scoped_fresh_boot(
        environment=None, database_snapshot=[],
        projects_document=None, baselines_document=[],
        inventory=None,
    )
    assert result["status"] == "STOP"
    assert result["source_contract_valid"] is False
    assert result["startup_authorized"] is False


def test_direct_call_to_extracted_legacy_host_recovery_denied_for_f2(monkeypatch):
    monkeypatch.setenv("PCP_RUNTIME_STARTUP_MODE", "normal")
    monkeypatch.setenv("PCP_FULLPATH_SOURCE_ONLY", "true")
    touched = []

    async def forbidden_cancel():
        touched.append("cancel-global")

    monkeypatch.setattr(engine_core, "cancel_all_antigravity_runs", forbidden_cancel)
    instance = object.__new__(RuntimeEngineCore)
    with pytest.raises(FullPathCandidateNotReady, match="source-only"):
        asyncio.run(instance._reconcile_legacy_restart_effects())
    assert touched == []


def test_parked_f2_engine_start_denied_before_storage_even_with_clean_inventory(
    monkeypatch,
):
    monkeypatch.setenv("PCP_RUNTIME_STARTUP_MODE", "normal")
    monkeypatch.setenv("PCP_FULLPATH_SOURCE_ONLY", "true")

    class StrictStore:
        def init(self):
            raise AssertionError("F2 source-only must never initialize schemas")
        def list(self, limit=50):
            raise AssertionError("F2 source-only must never load historic jobs")

    instance = RuntimeEngineCore(StrictStore())
    with pytest.raises(FullPathCandidateNotReady, match="source-only"):
        asyncio.run(instance.start())
    assert instance.worker_task is None


def test_normal_legacy_restart_semantics_remain_unchanged(monkeypatch):
    """The extracted legacy path still cancels/replays/interrupts exactly once."""
    monkeypatch.setenv("PCP_RUNTIME_STARTUP_MODE", "normal")
    monkeypatch.delenv("PCP_FULLPATH_SOURCE_ONLY", raising=False)
    monkeypatch.setenv("PROJECTS_FILE", "/config/projects.yml")
    monkeypatch.setenv("PROJECT_BASELINES_FILE", "/config/project-baselines.yml")
    monkeypatch.setenv("CODING_PROJECTS_ROOT", "/home/owner/projects")
    monkeypatch.setenv("CODING_WORKSPACES_ROOT", "/home/owner/workspaces")
    monkeypatch.setenv("CODEX_HOME", "/home/coder/.codex")
    monkeypatch.setenv("DATABASE_URL", "postgresql://db:pw@db:5432/db")

    calls = []
    class FakeStore:
        def init(self):
            calls.append("init")
        def get(self, job_id):
            return (
                {"id": job_id, "project_id": "demo", "status": "queued", "checkpoint": {}}
                if job_id == "a" else None
            )
        def list(self, limit=50):
            assert limit == 500
            calls.append("list")
            return [
                {"id": "a", "project_id": "demo", "status": "queued", "checkpoint": {}},
                {"id": "b", "project_id": "demo", "status": "executing", "checkpoint": {}},
            ]
        def update(self, job_id, **kwargs):
            calls.append(("update", job_id, kwargs["status"]))
        def terminal_active_project_leases(self):
            calls.append("leases")
            return []

    class FakeDdev:
        async def cancel(self, *, job_id):
            calls.append(("cancel", job_id))

    async def fake_host_cancel():
        calls.append("legacy-global-cancel")

    monkeypatch.setattr(engine_core, "cancel_all_antigravity_runs", fake_host_cancel)

    async def scenario():
        engine = RuntimeEngineCore(FakeStore())
        engine.ddev = FakeDdev()
        await engine.start()
        try:
            assert engine.worker_task is not None
            assert engine.queue.qsize() == 1
            assert calls == [
                "init", "list", "legacy-global-cancel",
                ("update", "b", "interrupted"), ("cancel", "b"), "leases",
            ]
        finally:
            await engine.stop()
    asyncio.run(scenario())
