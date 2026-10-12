"""G0 full-path candidate admission: synthetic, never contacts Docker/provider/DB."""
from __future__ import annotations

import asyncio
from copy import deepcopy
import pytest
from fastapi.testclient import TestClient

from app import fullpath_fixture_safety as gate
from app import main
from app.engine_core import RuntimeEngineCore


def candidate():
    env = {
        **gate.FIXED_ENV,
        "DATABASE_URL": "postgresql://fullpath:private-only@fullpath-db:5432/fullpath",
        "ROUTER_URL": "http://fullpath-router:8090",
        "DDEV_EXECUTOR_URL": "http://fullpath-executor:8790",
    }
    projects = {"projects": {gate.PROJECT_ID: {
        "path": "${CODING_PROJECTS_ROOT}/pcp-g0-fullpath-fixture",
        "base_branch": "benchmark/fullpath",
        "runtime": {
            "workspace_mode": "isolated_clone",
            "exclusive_project_lease": False,
            "developer_permission_mode": "bounded",
        },
        "autonomy": {
            "allow_commit": False, "allow_push_ai_branch": False,
            "allow_create_pr": False, "allow_auto_merge_low_risk": False,
            "allow_production_deploy": False,
        },
        "ddev": {"enabled": False},
    }}}
    baselines = {"projects": {gate.PROJECT_ID: {
        "active_revision": "fullpath-v1",
        "revisions": {"fullpath-v1": {
            "status": "approved", "source_commit": "a" * 40,
        }},
    }}}
    return env, projects, baselines


def assess(env, projects, baselines, socket=False):
    return gate.assess_source_contract(
        env, projects, baselines, docker_socket_present=socket
    )


def test_plausible_candidate_remains_explicitly_non_executable():
    env, projects, baselines = candidate()
    before = deepcopy((env, projects, baselines))
    value = assess(env, projects, baselines)
    assert value["status"] == "STOP"
    assert value["candidate_source_contract_valid"] is True
    assert all(value["checks"].values())
    assert value["blockers"] == list(gate.SOURCE_ONLY_BLOCKERS)
    assert not value["full_runtime_start_allowed"]
    assert not value["real_verification_proven"]
    assert not value["auto_delivery_proven"]
    assert not value["ready_to_dispatch"]
    assert value["model_calls_this_command"] == 0
    assert (env, projects, baselines) == before


@pytest.mark.parametrize("key,value,check", [
    ("PCP_RUNTIME_STARTUP_MODE", "normal", "dedicated_config_and_workspace_roots"),
    ("CODING_PROJECTS_ROOT", "/home/sonvh", "dedicated_config_and_workspace_roots"),
    ("CODING_WORKSPACES_ROOT", "/g0/workspaces", "dedicated_config_and_workspace_roots"),
    ("PROJECTS_FILE", "/config/projects.yml", "dedicated_config_and_workspace_roots"),
    ("CODEX_HOME", "/home/coder/.codex", "dedicated_config_and_workspace_roots"),
    ("DATABASE_URL", "postgresql://g0:pw@db:5432/g0", "dedicated_db_identity"),
    ("DATABASE_URL", "postgresql://fullpath:pw@fullpath-db:5433/fullpath",
     "dedicated_db_identity"),
    ("DATABASE_URL", "postgresql://fullpath:pw@fullpath-db:5432/g0",
     "dedicated_db_identity"),
    ("ROUTER_URL", "http://router:8090", "dedicated_router_identity"),
    ("ROUTER_URL", "http://fullpath-router:8090/path", "dedicated_router_identity"),
    ("DDEV_EXECUTOR_URL", "http://ddev-executor:8790", "dedicated_executor_identity"),
    ("PCP_FULLPATH_OPERATIONAL_ACTIVATION", "owner-approved",
     "no_host_privileged_or_old_g0_secrets"),
    ("ANTIGRAVITY_BRIDGE_URL", "http://127.0.0.1",
     "no_host_privileged_or_old_g0_secrets"),
    ("GITHUB_DELIVERY_TOKEN", "secret", "no_host_privileged_or_old_g0_secrets"),
    ("PCP_G0_DELIVERY_ENABLED", "owner-approved",
     "no_host_privileged_or_old_g0_secrets"),
])
def test_wrong_environment_or_privilege_fails(key, value, check):
    env, projects, baseline = candidate()
    env[key] = value
    value = assess(env, projects, baseline)
    assert value["status"] == "STOP"
    assert value["checks"][check] is False


def test_host_socket_is_prohibited():
    env, projects, baseline = candidate()
    result = assess(env, projects, baseline, socket=True)
    assert not result["checks"]["no_host_privileged_or_old_g0_secrets"]


@pytest.mark.parametrize("mutate", [
    lambda d: d["projects"].update({"chonhac": {}}),
    lambda d: d["projects"].update({"pcp-g0-drupal-fixture": {}}),
    lambda d: d["projects"][gate.PROJECT_ID].update({"base_branch": "benchmark/pcp"}),
    lambda d: d["projects"][gate.PROJECT_ID].update({"path": "/home/sonvh"}),
    lambda d: d["projects"][gate.PROJECT_ID]["runtime"].update(
        {"workspace_mode": "direct"}),
    lambda d: d["projects"][gate.PROJECT_ID]["runtime"].update(
        {"exclusive_project_lease": True}),
    lambda d: d["projects"][gate.PROJECT_ID]["runtime"].update(
        {"developer_permission_mode": "trusted_local"}),
])
def test_foreign_project_and_workspace_denied(mutate):
    env, projects, baseline = candidate()
    mutate(projects)
    result = assess(env, projects, baseline)
    assert not result["checks"]["singleton_new_fixture_with_locked_workspace"]


@pytest.mark.parametrize("mutate", [
    lambda d: d["projects"][gate.PROJECT_ID]["autonomy"].update(
        {"allow_create_pr": True}),
    lambda d: d["projects"][gate.PROJECT_ID]["autonomy"].update(
        {"allow_production_deploy": True}),
    lambda d: d["projects"][gate.PROJECT_ID]["ddev"].update(
        {"enabled": True}),
])
def test_unproven_delivery_or_ddev_cannot_be_assumed(mutate):
    env, projects, baseline = candidate()
    mutate(projects)
    result = assess(env, projects, baseline)
    assert not result["checks"]["no_unproven_delivery_or_ddev"]


@pytest.mark.parametrize("mutate", [
    lambda d: d["projects"].update({"other": {}}),
    lambda d: d["projects"][gate.PROJECT_ID]["revisions"]["fullpath-v1"].update(
        {"source_commit": gate.OLD_G0_SEED}),
    lambda d: d["projects"][gate.PROJECT_ID]["revisions"]["fullpath-v1"].update(
        {"status": "candidate"}),
    lambda d: d["projects"][gate.PROJECT_ID].update(
        {"active_revision": "not-approved"}),
])
def test_old_seed_and_unapproved_baseline_denied(mutate):
    env, projects, baseline = candidate()
    mutate(baseline)
    result = assess(env, projects, baseline)
    assert not result["checks"]["independent_approved_source_revision"]


def test_explicit_refusal_never_is_a_source_only_go():
    with pytest.raises(gate.FullPathCandidateNotReady, match="source-only"):
        gate.refuse_source_only_startup()


def test_existing_startup_modes_unchanged(monkeypatch):
    for mode in ("normal", "inspect", "g0_fixture_run"):
        monkeypatch.setenv("PCP_RUNTIME_STARTUP_MODE", mode)
        assert main.runtime_startup_mode() == mode
    monkeypatch.setenv("PCP_RUNTIME_STARTUP_MODE", gate.MODE)
    assert main.runtime_startup_mode() == gate.MODE


def test_candidate_lifespan_stops_before_engine_plan_or_publishers(monkeypatch):
    monkeypatch.setenv("PCP_RUNTIME_STARTUP_MODE", gate.MODE)
    events = []
    monkeypatch.setattr(main, "harden_runtime_process_secret_boundary",
                        lambda: events.append("harden"))
    async def forbidden(*a, **k):
        raise AssertionError("normal engine/scheduler/publisher activated")
    for comp in (main.engine, main.plan_orchestrator, main.progress_publisher,
                 main.job_status_publisher):
        monkeypatch.setattr(comp, "start", forbidden)
    async def exercise():
        with pytest.raises(gate.FullPathCandidateNotReady, match="source-only"):
            async with main.lifespan(main.app):
                raise AssertionError("source-only mode entered")
    asyncio.run(exercise())
    assert events == ["harden"]


def test_http_even_without_lifespan_is_503(monkeypatch):
    monkeypatch.setenv("PCP_RUNTIME_STARTUP_MODE", gate.MODE)
    monkeypatch.setenv("RUNTIME_API_TOKEN", "synthetic-token")
    client = TestClient(main.app)  # Deliberately avoid lifespan/DB startup.
    try:
        for method, uri in (
            ("GET", "/health"), ("GET", "/docs"), ("GET", "/openapi.json"),
            ("GET", "/v1/jobs"), ("POST", "/v1/intake"), ("POST", "/v1/jobs"),
            ("POST", "/v1/plans"), ("POST", "/v1/orchestrator/tick"),
            ("POST", "/v1/g0-fixture/prepare"),
        ):
            response = client.request(method, uri)
            assert response.status_code == 503, (method, uri, response.status_code)
    finally:
        client.close()


def test_direct_core_start_call_cannot_bypass_http_or_lifespan(monkeypatch):
    monkeypatch.setenv("PCP_RUNTIME_STARTUP_MODE", gate.MODE)
    touched = []
    class FakeStore:
        def init(self):
            touched.append("storage.init")
        def list(self, limit=50):
            touched.append("storage.list")
            return []
    instance = RuntimeEngineCore(FakeStore())
    with pytest.raises(gate.FullPathCandidateNotReady, match="source-only"):
        asyncio.run(instance.start())
    assert touched == []
    assert instance.worker_task is None


def test_unknown_candidate_like_mode_fails_closed(monkeypatch):
    monkeypatch.setenv("PCP_RUNTIME_STARTUP_MODE", "g0_fullpath_candidate_extra")
    with pytest.raises(RuntimeError, match="Invalid PCP_RUNTIME_STARTUP_MODE"):
        main.runtime_startup_mode()


@pytest.mark.parametrize("indicator,value", [
    ("PROJECTS_FILE", "/fullpath/config/projects.yml"),
    ("PROJECT_BASELINES_FILE", "/fullpath/config/project-baselines.yml"),
    ("CODING_PROJECTS_ROOT", "/fullpath/sources"),
    ("CODING_WORKSPACES_ROOT", "/fullpath/workspaces"),
    ("CODEX_HOME", "/home/coder/.codex-fullpath"),
    ("DATABASE_URL", "postgresql://fullpath:pw@fullpath-db:5432/fullpath"),
    ("PCP_FULLPATH_SOURCE_ONLY", "true"),
])
def test_parked_source_identity_detected_even_after_normal_mode_flip(
    indicator, value, monkeypatch,
):
    monkeypatch.setenv("PCP_RUNTIME_STARTUP_MODE", "normal")
    isolated = {indicator: value}
    assert gate.parked_fullpath_environment(isolated) is True
    assert main.runtime_startup_mode() == "normal"


def test_existing_normal_root_does_not_accidentally_trigger_f2_detector():
    assert gate.parked_fullpath_environment({
        "PCP_RUNTIME_STARTUP_MODE": "normal",
        "PROJECTS_FILE": "/config/projects.yml",
        "PROJECT_BASELINES_FILE": "/config/project-baselines.yml",
        "CODING_PROJECTS_ROOT": "/home/owner/projects",
        "CODING_WORKSPACES_ROOT": "/home/owner/pcp-workspaces",
        "DATABASE_URL": "postgresql://db:pw@db:5432/db",
        "CODEX_HOME": "/home/coder/.codex",
    }) is False


def test_switched_normal_mode_still_denies_every_http_route(monkeypatch):
    monkeypatch.setenv("PCP_RUNTIME_STARTUP_MODE", "normal")
    monkeypatch.setenv("PROJECTS_FILE", "/fullpath/config/projects.yml")
    monkeypatch.setenv("RUNTIME_API_TOKEN", "synthetic-token")
    client = TestClient(main.app)
    try:
        for method, uri in (
            ("GET", "/health"), ("GET", "/docs"), ("GET", "/v1/jobs"),
            ("POST", "/v1/intake"), ("POST", "/v1/jobs"),
            ("POST", "/v1/g0-fullpath/jobs/" + "a"*32 + "/pm-review"),
            ("POST", "/v1/orchestrator/tick"),
        ):
            response = client.request(method, uri)
            assert response.status_code == 503, (method, uri, response.status_code)
    finally:
        client.close()


def test_switched_normal_mode_lifespan_blocks_before_engine_and_planner(
    monkeypatch,
):
    monkeypatch.setenv("PCP_RUNTIME_STARTUP_MODE", "normal")
    monkeypatch.setenv("CODEX_HOME", "/home/coder/.codex-fullpath")
    calls = []
    monkeypatch.setattr(main, "harden_runtime_process_secret_boundary",
                        lambda: calls.append("harden"))
    async def forbidden(*a, **k):
        raise AssertionError("engine / PlanOrchestrator / publishers must not start")
    for comp in (main.engine, main.plan_orchestrator, main.progress_publisher,
                 main.job_status_publisher):
        monkeypatch.setattr(comp, "start", forbidden)
    async def exercise():
        with pytest.raises(gate.FullPathCandidateNotReady, match="source-only"):
            async with main.lifespan(main.app):
                raise AssertionError("source-only mode entered")
    asyncio.run(exercise())
    assert calls == ["harden"]


def test_switched_normal_mode_direct_engine_start_does_not_touch_storage(
    monkeypatch,
):
    monkeypatch.setenv("PCP_RUNTIME_STARTUP_MODE", "normal")
    monkeypatch.setenv("DATABASE_URL",
                       "postgresql://fullpath:pw@fullpath-db:5432/fullpath")
    touched = []
    class FakeStore:
        def init(self):
            touched.append("storage.init")
        def list(self, limit=50):
            touched.append("storage.list")
            return []
    instance = RuntimeEngineCore(FakeStore())
    with pytest.raises(gate.FullPathCandidateNotReady, match="source-only"):
        asyncio.run(instance.start())
    assert touched == []
    assert instance.worker_task is None
