"""C3A F2 Engine worker source tests: no host DB, Docker, provider, or model."""
from __future__ import annotations

import asyncio
from pathlib import Path

from fastapi import HTTPException
from fastapi.testclient import TestClient
import pytest
import yaml

from app import main as runtime_main
from app import fullpath_worker_only as f2
from app.engine_core import RuntimeEngineCore
from app.fullpath_fresh_startup import POST_SCHEMA_TABLES


ROOT = Path(__file__).resolve().parents[3]


def f2_env(monkeypatch):
    for key, value in f2.FIXED_ENV.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setenv("PCP_RUNTIME_STARTUP_MODE", f2.F2_WORKER_MODE)
    monkeypatch.setenv("PCP_F2_WORKER_ONLY_ENABLED", "owner-approved")
    monkeypatch.setenv(
        "DATABASE_URL", "postgresql://fullpath:fake@fullpath-db:5432/fullpath",
    )
    monkeypatch.setenv("ROUTER_URL", "http://fullpath-router:8090")
    monkeypatch.setenv("DDEV_EXECUTOR_URL", "http://fullpath-executor:8790")
    for key in (
        "PCP_FULLPATH_SOURCE_ONLY", "PCP_FULLPATH_OPERATIONAL_ACTIVATION",
        "GITHUB_DELIVERY_TOKEN", "ANTIGRAVITY_BRIDGE_URL",
        "ANTIGRAVITY_BRIDGE_TOKEN", "PCP_G0_EXECUTION_ENABLED",
        "PCP_G0_DELIVERY_ENABLED",
    ):
        monkeypatch.delenv(key, raising=False)
    actual_exists = Path.exists
    monkeypatch.setattr(
        f2.Path, "exists",
        lambda self: False if str(self) == "/var/run/docker.sock"
        else actual_exists(self),
    )


def frame(activate=False):
    projects = yaml.safe_load(
        (ROOT / "config/fullpath-candidate/projects.yml").read_text(encoding="utf-8")
    )
    baselines = yaml.safe_load(
        (ROOT / "config/fullpath-candidate/project-baselines.yml").read_text(
            encoding="utf-8"
        )
    )
    if activate:
        rights = projects["projects"][f2.PROJECT_ID]["autonomy"]
        for key in ("allow_commit", "allow_push_ai_branch", "allow_create_pr"):
            rights[key] = True
        baselines["projects"][f2.PROJECT_ID]["active_revision"] = f2.F2_V2_REVISION
    return projects, baselines


class ForbiddenStorage:
    def __init__(self, dsn):
        self.dsn = dsn

    def connect(self):
        pytest.fail("No real DB should be accessed by C3A CI tests")

    def __getattr__(self, attr):
        pytest.fail("Forbidden legacy/storage side effect: " + attr)


def good_snapshot():
    return {
        "database_name": "fullpath", "database_role": "fullpath",
        "is_superuser": "off",
        "peer_session_count": 0, "user_function_count": 0,
        "observed_tables": sorted(POST_SCHEMA_TABLES),
        "table_counts": {name: 0 for name in POST_SCHEMA_TABLES},
    }


def test_unchanged_f2_project_and_baseline_stay_parked(monkeypatch):
    f2_env(monkeypatch)
    projects, baselines = frame()
    with pytest.raises(f2.F2WorkerNotReady, match="registry"):
        f2.attest_f2_worker_database(
            storage=ForbiddenStorage(runtime_main.os.environ["DATABASE_URL"]),
            env=runtime_main.os.environ,
            projects=projects, baselines=baselines,
        )


def test_active_autonomy_without_active_baseline_still_stops(monkeypatch):
    f2_env(monkeypatch)
    projects, baselines = frame(activate=True)
    baselines["projects"][f2.PROJECT_ID]["active_revision"] = None
    with pytest.raises(f2.F2WorkerNotReady, match="approved baseline"):
        f2.attest_f2_worker_database(
            storage=ForbiddenStorage(runtime_main.os.environ["DATABASE_URL"]),
            env=runtime_main.os.environ,
            projects=projects, baselines=baselines,
        )


@pytest.mark.parametrize("transform", [
    lambda p,b: p["projects"].update(chonhac=dict(p["projects"][f2.PROJECT_ID])),
    lambda p,b: p["projects"][f2.PROJECT_ID].update(base_branch="benchmark/direct"),
    lambda p,b: p["projects"][f2.PROJECT_ID]["ddev"].update(enabled=True),
    lambda p,b: p["projects"][f2.PROJECT_ID]["autonomy"].update(allow_production_deploy=True),
    lambda p,b: b["projects"][f2.PROJECT_ID]["revisions"][f2.F2_V2_REVISION].update(
        source_commit="a"*40
    ),
])
def test_registry_scope_and_source_authority_drift_refused(transform):
    projects, baselines = frame(activate=True)
    transform(projects, baselines)
    with pytest.raises(f2.F2WorkerNotReady):
        f2.require_f2_worker_registry(projects, baselines)


@pytest.mark.parametrize("name,value", [
    ("PROJECTS_FILE", "/config/projects.yml"),
    ("DATABASE_URL", "postgresql://db:pw@db:5432/db"),
    ("CODING_PROJECTS_ROOT", "/home/sonvh/chonhac"),
    ("PCP_F2_WORKER_ONLY_ENABLED", "not-approved"),
    ("PCP_FULLPATH_SOURCE_ONLY", "true"),
    ("GITHUB_DELIVERY_TOKEN", "foreign"),
])
def test_f2_environment_mismatch_blocks_before_db(monkeypatch, name, value):
    f2_env(monkeypatch)
    monkeypatch.setenv(name, value)
    with pytest.raises(f2.F2WorkerNotReady):
        f2.require_f2_worker_environment(runtime_main.os.environ)


def test_read_only_catalog_proof_requires_25_empty_tables(monkeypatch):
    f2_env(monkeypatch)
    projects, baselines = frame(activate=True)
    storage = ForbiddenStorage(runtime_main.os.environ["DATABASE_URL"])
    monkeypatch.setattr(f2, "read_only_post_schema_table_snapshot",
                        lambda **kwargs: good_snapshot())
    proof = f2.attest_f2_worker_database(
        storage=storage, env=runtime_main.os.environ,
        projects=projects, baselines=baselines,
    )
    assert proof == f2.F2WorkerReady(f2.PROJECT_ID, f2.F2_V2_SEED, "fullpath")

    modified = good_snapshot()
    modified["table_counts"]["cp_jobs"] = 1
    monkeypatch.setattr(f2, "read_only_post_schema_table_snapshot",
                        lambda **kwargs: modified)
    with pytest.raises(f2.F2WorkerNotReady, match="25 empty"):
        f2.attest_f2_worker_database(
            storage=storage, env=runtime_main.os.environ,
            projects=projects, baselines=baselines,
        )


def test_existing_engine_starts_only_one_f2_worker_without_legacy_recovery(monkeypatch):
    f2_env(monkeypatch)
    engine = RuntimeEngineCore(ForbiddenStorage("unused"))
    events = []

    async def worker():
        events.append("worker")
        await asyncio.Event().wait()

    async def legacy():
        pytest.fail("Legacy global recovery should not be called")

    monkeypatch.setattr(engine, "_worker_loop", worker)
    monkeypatch.setattr(engine, "_reconcile_legacy_restart_effects", legacy)

    async def scenario():
        proof = f2.F2WorkerReady(f2.PROJECT_ID, f2.F2_V2_SEED, "fullpath")
        await engine.start_fullpath_worker_only(proof)
        await asyncio.sleep(0)
        assert events == ["worker"] and engine._f2_worker_only
        with pytest.raises(f2.F2WorkerNotReady, match="already started"):
            await engine.start_fullpath_worker_only(proof)
        await engine.stop_fullpath_worker_only()
        assert engine.worker_task is None
        assert engine._f2_worker_only is False

    asyncio.run(scenario())


def test_single_f2_job_enqueue_never_accepts_foreign_or_orchestrated(monkeypatch):
    f2_env(monkeypatch)
    class Storage:
        row = {"project_id": f2.PROJECT_ID, "status": "queued", "checkpoint": {}}
        def get(self, job_id):
            return self.row
    storage = Storage()
    engine = RuntimeEngineCore(storage)
    engine._f2_worker_only = True

    async def scenario():
        await engine.enqueue("a"*32)
        with pytest.raises(f2.F2WorkerNotReady, match="one exact queued"):
            await engine.enqueue("b"*32)
        assert engine.queue.qsize() == 1
        await engine.queue.get()
        engine.queue.task_done()
        storage.row = {"project_id": "chonhac", "status": "queued"}
        with pytest.raises(f2.F2WorkerNotReady):
            await engine.enqueue("c"*32)

    asyncio.run(scenario())


def test_api_still_inert_when_lifespan_db_proof_is_absent(monkeypatch):
    f2_env(monkeypatch)
    monkeypatch.setattr(runtime_main.engine, "_f2_worker_only", False)
    # Do not enter TestClient lifespan; the real current inactive baseline
    # correctly blocks startup. Middleware must also block direct invocations.
    client = TestClient(runtime_main.app, raise_server_exceptions=False)
    assert client.get("/health").status_code == 503
    assert client.post("/v1/jobs").status_code == 503
    assert f2.f2_direct_intake_route_allowed("POST", "/v1/jobs")
    assert f2.f2_direct_intake_route_allowed("GET", "/v1/jobs/" + "a"*32)
    for method, path in (
        ("POST", "/v1/plans"), ("POST", "/v1/orchestrator/tick"),
        ("POST", "/v1/jobs/" + "a"*32 + "/cancel"),
        ("GET", "/v1/jobs"), ("GET", "/docs"),
        ("POST", "/v1/jobs/" + "a"*32 + "/run"),
    ):
        assert not f2.f2_direct_intake_route_allowed(method, path)
