"""B2.2c0 source-only startup regression: no real state or external systems."""
from __future__ import annotations

import asyncio
from copy import deepcopy
from pathlib import Path
import runpy

import httpx
import pytest
import yaml

from app import main as runtime_main
from app.baseline import ProjectBaselineRegistry, resolve_project_baseline

ROOT = Path(__file__).resolve().parents[3]
PROJECT = ROOT / "config/projects.pcp-local.yml"
BASELINE = ROOT / "config/project-baselines.pcp-local.yml"


def setup_drafts(monkeypatch, tmp_path):
    project = tmp_path / PROJECT.name
    baseline = tmp_path / BASELINE.name
    p = yaml.safe_load(PROJECT.read_text(encoding="utf-8"))
    b = yaml.safe_load(BASELINE.read_text(encoding="utf-8"))
    project.write_text(yaml.safe_dump(p), encoding="utf-8")
    baseline.write_text(yaml.safe_dump(b), encoding="utf-8")
    monkeypatch.setenv("PROJECTS_FILE", str(project))
    monkeypatch.setenv("PROJECT_BASELINES_FILE", str(baseline))
    monkeypatch.setenv("PCP_RUNTIME_STARTUP_MODE", "pcp_local_inspect")
    monkeypatch.delenv("PCP_FULLPATH_SOURCE_ONLY", raising=False)
    for key in runtime_main._PCP_LOCAL_FLAGS:
        monkeypatch.delenv(key, raising=False)
    return project, baseline, p, b


def forbid_external(monkeypatch):
    calls = []
    async def blocked(*args, **kwargs):
        calls.append("unsafe")
        raise AssertionError("Legacy DB/job/engine/publisher invocation")
    monkeypatch.setattr(
        runtime_main, "harden_runtime_process_secret_boundary",
        lambda: calls.append("harden"),
    )
    for item in (
        runtime_main.engine, runtime_main.plan_orchestrator,
        runtime_main.progress_publisher, runtime_main.job_status_publisher,
    ):
        monkeypatch.setattr(item, "start", blocked)
        monkeypatch.setattr(item, "stop", blocked)
    return calls


def assert_fail_start():
    async def run():
        with pytest.raises(RuntimeError, match="PCP-local"):
            async with runtime_main.lifespan(runtime_main.app):
                pytest.fail("invalid PCP-local startup entered")
    asyncio.run(run())


def test_committed_drafts_have_no_authority(monkeypatch, tmp_path):
    _, _, p, b = setup_drafts(monkeypatch, tmp_path)
    runtime_main._validate_pcp_local_inspection()
    assert list(p["projects"]) == ["pcp-local"]
    assert p["projects"]["pcp-local"]["path"] is None
    assert all(v is False for v in p["projects"]["pcp-local"]["autonomy"].values())
    assert ProjectBaselineRegistry.model_validate(b).projects["pcp-local"].active_revision is None
    monkeypatch.setattr("app.baseline.project_baselines_doc", lambda: b)
    assert resolve_project_baseline("pcp-local") is None
    with pytest.raises(ValueError, match="Unknown ProjectBaseline revision"):
        resolve_project_baseline("pcp-local", "fake")


def test_parked_lifespan_and_middleware_have_zero_external_effects(monkeypatch, tmp_path):
    setup_drafts(monkeypatch, tmp_path)
    calls = forbid_external(monkeypatch)
    async def forbid_health():
        calls.append("network")
        raise AssertionError("health may not touch Router/Executor")
    monkeypatch.setattr(runtime_main.engine.router, "health", forbid_health)
    monkeypatch.setattr(runtime_main.engine.ddev, "health", forbid_health)

    async def run():
        transport = httpx.ASGITransport(app=runtime_main.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            assert (await client.get("/health")).status_code == 503
        async with runtime_main.lifespan(runtime_main.app):
            assert runtime_main.app.state.pcp_local_inspection_ready is True
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                result = await client.get("/health")
                assert result.status_code == 200
                assert result.json()["status"] == "degraded"
                assert result.json()["router"] == "not_checked"
                for method, url in [
                    ("GET", "/v1/jobs"), ("GET", "/v1/quota"),
                    ("GET", "/dashboard"),
                    ("GET", "/v1/pm-bridge/local-source/candidates"),
                    ("POST", "/v1/intake"), ("POST", "/v1/jobs"),
                    ("POST", "/v1/g0-fixture/prepare"),
                ]:
                    assert (await client.request(method, url)).status_code == 503
                # Changing an env variable cannot unpark a live process.
                monkeypatch.setenv("PCP_RUNTIME_STARTUP_MODE", "normal")
                assert (await client.get("/health")).status_code == 503
                assert (await client.post("/v1/jobs")).status_code == 503
        assert runtime_main.app.state.pcp_local_inspection_ready is False
    asyncio.run(run())
    assert calls == []


@pytest.mark.parametrize("mode", [
    "normal", "inspect", "g0_fixture_run", "g0_fullpath_candidate",
    "g0_fullpath_worker",
])
def test_wrong_mode_does_not_touch_legacy(monkeypatch, tmp_path, mode):
    setup_drafts(monkeypatch, tmp_path)
    monkeypatch.setenv("PCP_RUNTIME_STARTUP_MODE", mode)
    calls = forbid_external(monkeypatch)
    assert_fail_start()
    assert calls == []


@pytest.mark.parametrize("flag", runtime_main._PCP_LOCAL_FLAGS)
def test_flag_only_cannot_activate_mode(monkeypatch, tmp_path, flag):
    setup_drafts(monkeypatch, tmp_path)
    monkeypatch.setenv(flag, "owner-approved")
    calls = forbid_external(monkeypatch)
    assert_fail_start()
    monkeypatch.setenv("PCP_RUNTIME_STARTUP_MODE", "normal")
    assert_fail_start()
    assert calls == []


@pytest.mark.parametrize("mutate", [
    lambda p,b: p["projects"].update({"chonhac": {}}),
    lambda p,b: p["projects"].update({"historical-fixture": {}}),
    lambda p,b: p["projects"]["pcp-local"].update(path="/owner/old/jobs"),
    lambda p,b: p["projects"]["pcp-local"].update(registration_status="approved"),
    lambda p,b: p["projects"]["pcp-local"].update(repository="other/repo"),
    lambda p,b: p["projects"]["pcp-local"].update(base_branch="release"),
    lambda p,b: p["projects"]["pcp-local"]["autonomy"].update(allow_commit=True),
    lambda p,b: p["projects"]["pcp-local"]["autonomy"].update(allow_create_pr=True),
    lambda p,b: p["projects"]["pcp-local"]["autonomy"].update(allow_production_deploy=True),
    lambda p,b: p["projects"]["pcp-local"]["runtime"].update(workspace_mode="direct"),
    lambda p,b: p["projects"]["pcp-local"]["runtime"].update(developer_permission_mode="trusted_project"),
    lambda p,b: p["projects"]["pcp-local"]["ddev"].update(enabled=True),
    lambda p,b: b["projects"].update({"chonhac": {}}),
    lambda p,b: b["projects"]["pcp-local"].update(active_revision="fake"),
    lambda p,b: b["projects"]["pcp-local"].update(revisions={"fake": {"status": "approved"}}),
    lambda p,b: b["projects"]["pcp-local"].pop("active_revision"),
    lambda p,b: b["projects"]["pcp-local"].pop("revisions"),
    lambda p,b: b.update(version=2),
])
def test_draft_promotion_or_cross_project_injection_denied(monkeypatch, tmp_path, mutate):
    project, baseline, p, b = setup_drafts(monkeypatch, tmp_path)
    p, b = deepcopy(p), deepcopy(b)
    mutate(p, b)
    project.write_text(yaml.safe_dump(p), encoding="utf-8")
    baseline.write_text(yaml.safe_dump(b), encoding="utf-8")
    calls = forbid_external(monkeypatch)
    assert_fail_start()
    assert calls == []


@pytest.mark.parametrize("fault", [
    "missing_project", "missing_baseline", "bad_project", "bad_baseline",
    "symlink", "different_parent", "wrong_name", "relative",
])
def test_broken_or_foreign_files_denied(monkeypatch, tmp_path, fault):
    project, baseline, _, _ = setup_drafts(monkeypatch, tmp_path)
    if fault == "missing_project":
        project.unlink()
    if fault == "missing_baseline":
        baseline.unlink()
    if fault == "bad_project":
        project.write_text("version: [\n", encoding="utf-8")
    if fault == "bad_baseline":
        baseline.write_text("version: [\n", encoding="utf-8")
    if fault == "symlink":
        copied = tmp_path / "not-checked.yml"
        project.rename(copied)
        project.symlink_to(copied)
    if fault == "different_parent":
        other = tmp_path / "other"
        other.mkdir()
        moved = other / baseline.name
        baseline.rename(moved)
        monkeypatch.setenv("PROJECT_BASELINES_FILE", str(moved))
    if fault == "wrong_name":
        monkeypatch.setenv("PROJECTS_FILE", str(baseline))
    if fault == "relative":
        monkeypatch.setenv("PROJECTS_FILE", project.name)
    calls = forbid_external(monkeypatch)
    assert_fail_start()
    assert calls == []


def test_direct_legacy_control_helpers_denied(monkeypatch, tmp_path):
    setup_drafts(monkeypatch, tmp_path)
    calls = forbid_external(monkeypatch)
    async def run():
        for function in (
            runtime_main._start_legacy_control_plane,
            runtime_main._stop_legacy_control_plane,
        ):
            with pytest.raises(RuntimeError, match="PCP-local"):
                await function()
    asyncio.run(run())
    assert calls == []


def test_protected_paths_are_registered():
    policy = runpy.run_path(str(ROOT / "scripts/check_project_doc_authority.py"))
    for path in (
        "config/projects.pcp-local.yml",
        "config/project-baselines.pcp-local.yml",
        "services/runtime/app/main.py",
    ):
        assert policy["classify_path"](path) == "protected"


class ReplayStore:
    """Durable data and external operations are separate, observable fakes."""
    def __init__(self, rows):
        self.rows = {r["id"]: deepcopy(r) for r in rows}
        self.receipt = {"state": "claimed", "generation": 1, "model_calls": 0}
        self.lease = {"owner_job_id": rows[0]["id"], "state": "active", "generation": 4}
        self.updates = []

    def init(self):
        pass

    def get(self, job_id):
        return deepcopy(self.rows.get(job_id))

    def list(self, limit=500):
        return deepcopy(list(self.rows.values()))

    def update(self, job_id, **fields):
        self.updates.append((job_id, fields))
        self.rows[job_id].update(deepcopy(fields))

    def terminal_active_project_leases(self):
        return [deepcopy(self.lease)]

    def release_project_lease(self, *args):
        raise AssertionError("SOURCE lease released")


@pytest.mark.parametrize("status", ["queued", "routing", "executing", "interrupted", "blocked", "completed"])
@pytest.mark.parametrize("identity", ["source", "missing-marker", "null-marker", "foreign-marker", "missing-project", "corrupt-checkpoint"])
def test_b2f2_legacy_reconcile_preserves_source_rows_and_lease(monkeypatch, status, identity):
    from app import engine_core
    row = {"id": "a" * 32, "project_id": "pcp-local", "status": status,
           "checkpoint": {"pcp_local_source": {"receipt": {"generation": 1}}, "workspace_mode": "direct"},
           "progress": {"model_calls": 0, "test_runs": 2, "elapsed_minutes": 3}}
    if identity == "missing-marker":
        row["checkpoint"].pop("pcp_local_source")
    elif identity == "null-marker":
        row["checkpoint"]["pcp_local_source"] = None
    elif identity == "foreign-marker":
        row["project_id"] = "synthetic-foreign"
    elif identity == "missing-project":
        row.pop("project_id")
    elif identity == "corrupt-checkpoint":
        row["checkpoint"] = "not-a-checkpoint"
    store = ReplayStore([row])
    instance = engine_core.RuntimeEngineCore(store)
    original = deepcopy((store.rows, store.receipt, store.lease))
    calls = []
    async def forbidden(*args, **kwargs):
        calls.append("external")
        raise AssertionError("SOURCE invoked a legacy external operation")
    monkeypatch.setattr(engine_core, "cancel_all_antigravity_runs", forbidden)
    instance.enqueue = forbidden
    instance.ddev.cancel = forbidden
    async def run():
        await instance._reconcile_legacy_restart_effects()
    asyncio.run(run())
    assert (store.rows, store.receipt, store.lease) == original
    assert store.updates == calls == []


def test_b2f2_valid_legacy_jobs_still_reconcile_in_mixed_inventory(monkeypatch):
    from app import engine_core
    source_row = {"id": "source", "project_id": "pcp-local", "status": "queued", "checkpoint": {}}
    queued = {"id": "queued", "project_id": "synthetic-legacy", "status": "queued", "checkpoint": {}}
    inflight = {"id": "inflight", "project_id": "synthetic-legacy", "status": "executing", "checkpoint": {}}
    store = ReplayStore([source_row, queued, inflight])
    instance = engine_core.RuntimeEngineCore(store)
    enqueued, cancelled = [], []
    async def enqueue(job_id):
        enqueued.append(job_id)
    async def cancel(*, job_id):
        cancelled.append(job_id)
    async def forbid_global():
        raise AssertionError("Unscoped cancellation could touch SOURCE")
    instance.enqueue = enqueue
    instance.ddev.cancel = cancel
    monkeypatch.setattr(engine_core, "cancel_all_antigravity_runs", forbid_global)
    asyncio.run(instance._reconcile_legacy_restart_effects())
    assert enqueued == ["queued"] and cancelled == ["inflight"]
    assert store.rows["source"] == source_row
    assert store.rows["inflight"]["status"] == "interrupted"
    assert [job_id for job_id, _ in store.updates] == ["inflight"]


@pytest.mark.parametrize("inventory_size", [1, 500])
def test_b2f2_valid_legacy_queue_recovery_is_not_globally_disabled(monkeypatch, inventory_size):
    from app import engine_core
    rows = [{"id": str(index), "project_id": "synthetic-legacy", "status": "queued", "checkpoint": {}}
            for index in range(inventory_size)]
    store = ReplayStore(rows)
    # No terminal lease to clean up in this synthetic ordinary project.
    store.terminal_active_project_leases = lambda: []
    instance = engine_core.RuntimeEngineCore(store)
    calls = []
    async def cancel_global():
        calls.append("global")
    monkeypatch.setattr(engine_core, "cancel_all_antigravity_runs", cancel_global)
    asyncio.run(instance._reconcile_legacy_restart_effects())
    # A full page may hide an older SOURCE row: only scoped recovery is safe.
    assert calls == (["global"] if inventory_size < 500 else [])
    assert [instance.queue.get_nowait() for _ in rows] == [row["id"] for row in rows]
    assert store.updates == []


@pytest.mark.parametrize("becomes_source", [False, True])
def test_b2f2_generic_worker_preserves_source_on_exception_but_runs_valid_legacy(becomes_source):
    from app import engine_core
    rows = [
        {"id": "source", "project_id": "pcp-local", "status": "queued", "checkpoint": {"pcp_local_source": None}},
        {"id": "legacy", "project_id": "synthetic-legacy", "status": "queued", "checkpoint": {}, "progress": {"model_calls": 7}},
    ]
    store = ReplayStore(rows)
    seen = []
    class Worker(engine_core.RuntimeEngineCore):
        async def run_job(self, job_id):
            seen.append(job_id)
            if becomes_source:
                store.rows[job_id]["checkpoint"]["pcp_local_source"] = "uncertain"
                raise RuntimeError("synthetic in-flight failure after identity changed")
    instance = Worker(store)
    async def run():
        await instance.queue.put("source")
        await instance.queue.put("legacy")
        task = asyncio.create_task(instance._worker_loop())
        try:
            await asyncio.wait_for(instance.queue.join(), timeout=1)
        finally:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
    asyncio.run(run())
    assert seen == ["legacy"]
    assert store.rows["source"] == rows[0]
    assert store.rows["legacy"]["status"] == "queued"
    assert store.rows["legacy"]["progress"] == {"model_calls": 7}
    assert store.updates == []


@pytest.mark.parametrize("job_id,payload", [
    ("not-the-admitted-job", None),
    (runtime_main.F2_REENTRY_JOB_ID, runtime_main.JobRunRequest(reroute=True)),
    (runtime_main.F2_REENTRY_JOB_ID, runtime_main.JobRunRequest(reset_transient_provider_failures=True)),
])
def test_b2f2_frozen_scope_rejection_precedes_any_job_database_read(monkeypatch, job_id, payload):
    from fastapi import HTTPException
    monkeypatch.setattr(runtime_main, "runtime_startup_mode", lambda: runtime_main.F2_WORKER_MODE)
    monkeypatch.setattr(runtime_main, "require_f2_worker_environment", lambda *_: None)
    def forbidden(*_, **__):
        raise AssertionError("Rejected historical scope read a job")
    monkeypatch.setattr(runtime_main.storage, "get", forbidden)
    async def run():
        with pytest.raises(HTTPException) as exc:
            await runtime_main.run_job(job_id, payload)
        assert exc.value.status_code == 409
    asyncio.run(run())


def test_worker_mode_flags_alone_never_activate(monkeypatch, tmp_path):
    from app import pcp_local_trusted_readers as trusted
    from app.pcp_local_task_queue import TaskStop
    calls = forbid_external(monkeypatch)
    monkeypatch.setattr(trusted, 'ACTIVATION_FILE', tmp_path / 'absent.json')
    monkeypatch.setenv('PCP_RUNTIME_STARTUP_MODE', 'pcp_local_worker')
    for key in runtime_main._PCP_LOCAL_FLAGS:
        monkeypatch.setenv(key, 'owner-approved')
    async def check():
        with pytest.raises(TaskStop, match='delegation_missing'):
            async with runtime_main.lifespan(runtime_main.app):
                pytest.fail('flags cannot supply operational authority')
    asyncio.run(check())
    assert calls == ['harden']


def test_worker_http_does_not_open_generic_controls(monkeypatch):
    monkeypatch.setenv('PCP_RUNTIME_STARTUP_MODE', 'pcp_local_worker')
    monkeypatch.setattr(runtime_main.app.state, 'pcp_local_worker_ready', True, raising=False)
    async def check():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=runtime_main.app), base_url='http://test') as client:
            for method, path in [('POST','/v1/jobs'), ('POST','/v1/jobs/old/run'),
                                 ('POST','/v1/jobs/old/resume'), ('GET','/v1/jobs')]:
                assert (await client.request(method, path)).status_code == 403
    asyncio.run(check())
