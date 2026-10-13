"""F2-T01 one blocked-job re-entry: source-only tests, no Docker/DB/model."""

from __future__ import annotations

import asyncio
from copy import deepcopy
import os

from fastapi import HTTPException
import pytest

from app import fullpath_worker_only as f2
from app import main as runtime_main
from app.fullpath_fresh_startup import POST_SCHEMA_TABLES
from app.schemas import JobRunRequest
from test_f2_c3a_worker_only import f2_env, frame, good_snapshot


JOB = f2.F2_REENTRY_JOB_ID
PROJECT = f2.PROJECT_ID


def blocked_job():
    return {
        "id": JOB,
        "project_id": PROJECT,
        "source_commit": f2.F2_V2_SEED,
        "status": "blocked",
        "branch": "ai/88b9e0d85001",
        "workspace": "/fullpath/workspaces/" + JOB,
        "dry_run": False,
        "error": None,
        "result": {"reason": "material_change_missing_without_model_fallback"},
        "checkpoint": {
            "workspace_mode": "isolated_clone",
            "canonical_intake": {
                "mode": "direct",
                "bounded_direct": True,
                "decomposition_required": False,
                "baseline_revision": f2.F2_V2_REVISION,
            },
        },
        "progress": {
            "model_calls": 1,
            "iteration": 1,
            "changed_files": 0,
            "agent_succeeded": False,
            "last_agent_failure_kind": "no_effect",
            "provider_failures": [],
            "agent_attempts": [{
                "returncode": 1,
                "failure_kind": None,
            }],
        },
        "route": {
            "strategy": {
                "profile": "fast",
                "planner": None,
                "budget_mode": "legacy_hard",
                "executor": {
                    "id": "codex_gpt6_luna",
                    "model": "gpt-6-luna",
                    "reasoning_effort": "medium",
                },
                "budget": {
                    "max_model_calls": 2,
                    "max_iterations": 2,
                    "max_wall_time_minutes": 15,
                    "max_changed_files": 3,
                    "max_model_failovers": 0,
                    "max_provider_failovers": 0,
                },
            },
        },
    }


def recovery_snapshot():
    data = good_snapshot()
    data["table_counts"].update(f2.F2_REENTRY_COUNTS)
    return data


class ReadOnlyConnection:
    def __init__(self, row, *, foreign_table=None):
        self.row = row
        self.foreign_table = foreign_table
        self.sql = ""
        self.parameters = ()

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        pass

    def execute(self, sql, parameters=()):
        self.sql, self.parameters = sql, parameters
        if not sql.startswith("SET TRANSACTION"):
            assert parameters == (JOB,)
        return self

    def fetchone(self):
        if "FROM public.cp_jobs" in self.sql:
            return self.row
        for name, count in f2.F2_REENTRY_COUNTS.items():
            if name != "cp_jobs" and f'FROM public."{name}"' in self.sql:
                return {"n": count - (name == self.foreign_table)}
        pytest.fail("Unrecognized re-entry SQL")


class ReadOnlyStorage:
    def __init__(self, row=None, foreign_table=None):
        self.dsn = "postgresql://fullpath:fake@fullpath-db:5432/fullpath"
        self.row = row if row is not None else blocked_job()
        self.foreign_table = foreign_table
        self.calls = 0

    def connect(self):
        self.calls += 1
        return ReadOnlyConnection(self.row, foreign_table=self.foreign_table)


def admitted(monkeypatch, storage=None, snapshot=None):
    f2_env(monkeypatch)
    projects, baselines = frame(activate=True)
    storage = storage or ReadOnlyStorage()
    snapshot = snapshot if snapshot is not None else recovery_snapshot()
    monkeypatch.setattr(
        f2, "read_only_post_schema_table_snapshot",
        lambda **_kwargs: deepcopy(snapshot),
    )
    proof = f2.attest_f2_worker_database(
        storage=storage, env=os.environ,
        projects=projects, baselines=baselines,
    )
    assert proof == f2.F2WorkerReady(PROJECT, f2.F2_V2_SEED, "fullpath")
    return storage


def test_exact_single_blocked_job_can_start_worker_without_writing(monkeypatch):
    storage = admitted(monkeypatch)
    assert storage.calls == 1  # Only read-only re-entry SQL, no schema/migration.


@pytest.mark.parametrize("table", sorted(f2.F2_REENTRY_COUNTS))
def test_no_changed_row_count_can_enable_reentry(monkeypatch, table):
    f2_env(monkeypatch)
    snapshot = recovery_snapshot()
    snapshot["table_counts"][table] += 1
    with pytest.raises(f2.F2WorkerNotReady, match="manifest/count"):
        admitted(monkeypatch, snapshot=snapshot)


@pytest.mark.parametrize("foreign", [
    "cp_continuity_proposals", "cp_job_events", "cp_task_telemetry",
])
def test_foreign_or_orphan_child_record_is_denied(monkeypatch, foreign):
    f2_env(monkeypatch)
    projects, baselines = frame(activate=True)
    store = ReadOnlyStorage(foreign_table=foreign)
    monkeypatch.setattr(
        f2, "read_only_post_schema_table_snapshot",
        lambda **_kwargs: recovery_snapshot(),
    )
    with pytest.raises(f2.F2WorkerNotReady, match="foreign/orphan"):
        f2.attest_f2_worker_database(
            storage=store, env=os.environ,
            projects=projects, baselines=baselines,
        )


@pytest.mark.parametrize("field,value", [
    ("id", "a" * 32),
    ("project_id", "chonhac"),
    ("source_commit", "b" * 40),
    ("status", "queued"),
    ("status", "completed"),
    ("branch", "ai/unrelated"),
    ("workspace", "/fullpath/workspaces/foreign"),
    ("dry_run", True),
])
def test_wrong_blocked_job_identity_cannot_reenter(monkeypatch, field, value):
    job = blocked_job()
    job[field] = value
    with pytest.raises(f2.F2WorkerNotReady):
        f2.require_f2_exact_blocked_job(job)


@pytest.mark.parametrize("change", [
    lambda x: x["result"].update(reason="provider_failure_without_fallback"),
    lambda x: x["result"].update(commit="a" * 40),
    lambda x: x["progress"].update(model_calls=2),
    lambda x: x["progress"].update(iteration=2),
    lambda x: x["progress"].update(changed_files=1),
    lambda x: x["progress"].update(provider_failures=["quota_exhausted"]),
    lambda x: x["progress"]["agent_attempts"][0].update(returncode=0),
    lambda x: x["checkpoint"]["canonical_intake"].update(mode="planning"),
    lambda x: x["checkpoint"].update(orchestrator_launch={"state": "held"}),
    lambda x: x["route"]["strategy"]["budget"].update(max_model_calls=3),
    lambda x: x["route"]["strategy"]["executor"].update(model="other"),
])
def test_blocked_job_provenance_or_budget_drift_denied(change):
    job = blocked_job()
    change(job)
    with pytest.raises(f2.F2WorkerNotReady):
        f2.require_f2_exact_blocked_job(job)


def test_other_table_populated_or_wrong_schema_denied(monkeypatch):
    snapshot = recovery_snapshot()
    extra = next(iter(set(POST_SCHEMA_TABLES) - set(f2.F2_REENTRY_COUNTS)))
    snapshot["table_counts"][extra] = 1
    with pytest.raises(f2.F2WorkerNotReady, match="manifest/count"):
        admitted(monkeypatch, snapshot=snapshot)
    snapshot = recovery_snapshot()
    snapshot["observed_tables"] = snapshot["observed_tables"][:-1]
    with pytest.raises(f2.F2WorkerNotReady, match="manifest/count"):
        admitted(monkeypatch, snapshot=snapshot)


def test_parked_registry_does_not_gain_reentry_access(monkeypatch):
    f2_env(monkeypatch)
    parked_projects, parked_baselines = frame(activate=False)
    store = ReadOnlyStorage()
    with pytest.raises(f2.F2WorkerNotReady, match="registry"):
        f2.attest_f2_worker_database(
            storage=store, env=os.environ,
            projects=parked_projects, baselines=parked_baselines,
        )
    assert store.calls == 0


def test_only_exact_job_resume_http_scope_is_allowed():
    path = f"/v1/jobs/{JOB}/run"
    assert f2.f2_direct_intake_route_allowed("POST", path)
    assert not f2.f2_direct_intake_route_allowed(
        "POST", "/v1/jobs/" + "a" * 32 + "/run"
    )
    assert not f2.f2_direct_intake_route_allowed("POST", "/v1/jobs/" + JOB + "/cancel")
    assert not f2.f2_direct_intake_route_allowed("GET", "/v1/jobs")
    assert not f2.f2_direct_intake_route_allowed("POST", "/v1/plans")


def test_one_exact_f2_resume_preserves_args_and_rejects_second(monkeypatch):
    f2_env(monkeypatch)
    row = blocked_job()
    monkeypatch.setattr(runtime_main.engine, "_f2_worker_only", True)
    monkeypatch.setattr(runtime_main.engine, "active_jobs", {})
    monkeypatch.setattr(runtime_main.engine, "queue", asyncio.Queue())
    monkeypatch.setattr(runtime_main.storage, "get", lambda _id: deepcopy(row))
    monkeypatch.setattr(runtime_main, "view", lambda result: result)
    calls = []

    async def resume(job_id, **kwargs):
        calls.append((job_id, kwargs))
        return {"id": job_id, "status": "queued"}

    monkeypatch.setattr(runtime_main.engine, "resume", resume)
    result = asyncio.run(runtime_main.run_job(JOB))
    assert result == {"id": JOB, "status": "queued"}
    assert calls == [(JOB, {})]

    row["status"] = "queued"
    with pytest.raises(HTTPException):
        asyncio.run(runtime_main.run_job(JOB))
    assert len(calls) == 1


@pytest.mark.parametrize("id,run_request", [
    ("a" * 32, None),
    (JOB, JobRunRequest(reroute=True)),
    (JOB, JobRunRequest(reset_transient_provider_failures=True)),
    (JOB, JobRunRequest(verification_only_after_pm_handoff=True)),
])
def test_f2_resume_never_reopens_generic_controls(monkeypatch, id, run_request):
    f2_env(monkeypatch)
    monkeypatch.setattr(runtime_main.engine, "_f2_worker_only", True)
    monkeypatch.setattr(
        runtime_main.engine, "resume",
        lambda *_args, **_kw: pytest.fail("Disallowed F2 retry reached Engine"),
    )
    with pytest.raises(HTTPException):
        asyncio.run(runtime_main.run_job(id, run_request))
