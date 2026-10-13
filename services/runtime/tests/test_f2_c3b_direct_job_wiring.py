"""F2 one-job direct path through existing Engine/Executor; no host/model/DB calls."""
from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from fastapi import HTTPException

from app import main as runtime_main
from app import engine_execution as execution
from app.fullpath_worker_only import F2WorkerNotReady, F2_V2_SEED, F2_V2_REVISION
from app.intake_policy import HARD_BOUNDARIES
from app.schemas import JobCreateRequest, RepoHints, SemanticSignals, TaskInput
from test_f2_c3a_worker_only import f2_env


JOB = "a" * 32
PROJECT = "pcp-g0-fullpath-fixture"


def payload():
    hints = {
        "estimated_files": 3, "affected_components": 1,
        "dependency_depth": 0, "tests_available": True,
        "existing_pattern": True, "historical_churn": 0,
        **{name: False for name in HARD_BOUNDARIES},
    }
    return JobCreateRequest(
        project_id=PROJECT,
        task=TaskInput(
            title="F2-T01 crossing-midnight interval overlap",
            description="Exactly three approved source/test files, no dependencies.",
            semantic=SemanticSignals(**{
                name: 10 for name in SemanticSignals.model_fields
            }),
        ),
        repo_hints=RepoHints(**hints),
        source_commit=F2_V2_SEED,
        baseline_revision=F2_V2_REVISION,
        auto_run=True,
        dry_run=False,
    )


def test_f2_create_job_passes_deterministic_direct_decision_before_insert(monkeypatch):
    f2_env(monkeypatch)
    monkeypatch.setattr(runtime_main.engine, "_f2_worker_only", True)
    calls = []

    def list_jobs(limit=50):
        assert limit == 1
        calls.append("list")
        return []

    async def fake_create(request, *, intake_decision=None):
        assert request.source_commit == F2_V2_SEED
        assert intake_decision is not None
        assert intake_decision.mode == "direct"
        assert intake_decision.bounded_direct is True
        assert intake_decision.decomposition_required is False
        assert intake_decision.reasons == ["bounded_direct_eligible"]
        calls.append("create_with_atomic_intake")
        return JOB

    monkeypatch.setattr(runtime_main.storage, "list", list_jobs)
    monkeypatch.setattr(runtime_main.storage, "get", lambda _job: {"id": JOB})
    monkeypatch.setattr(runtime_main, "_create_local_job_guarded", fake_create)
    monkeypatch.setattr(runtime_main, "view", lambda row: row)

    answer = asyncio.run(runtime_main.create_job(payload()))
    assert answer == {"id": JOB}
    assert calls == ["list", "create_with_atomic_intake"]


@pytest.mark.parametrize("change", ["missing_hints", "protected", "missing_semantic"])
def test_f2_unbounded_intake_denied_before_database(monkeypatch, change):
    f2_env(monkeypatch)
    monkeypatch.setattr(runtime_main.engine, "_f2_worker_only", True)
    task = payload()
    if change == "missing_hints":
        task.repo_hints = RepoHints()
    elif change == "protected":
        task.repo_hints = task.repo_hints.model_copy(
            update={"security_sensitive": True}
        )
    else:
        task.task = task.task.model_copy(
            update={"semantic": SemanticSignals()}
        )

    monkeypatch.setattr(
        runtime_main.storage, "list",
        lambda *_a, **_k: pytest.fail("Invalid F2 task reached persistent job store"),
    )
    monkeypatch.setattr(
        runtime_main, "_create_local_job_guarded",
        lambda *_a, **_k: pytest.fail("Invalid F2 task reached job creation"),
    )
    with pytest.raises(HTTPException, match="canonical bounded direct intake") as exc:
        asyncio.run(runtime_main.create_job(task))
    assert exc.value.status_code == 422


class ReadStorage:
    def __init__(self, row):
        self.row = dict(row)
    def get(self, _job_id):
        return dict(self.row)


class HaltAtWorkspace:
    def __init__(self):
        self.calls = []
    async def create_workspace(self, **kwargs):
        self.calls.append(kwargs)
        raise RuntimeError("STOP_AT_F2_EXECUTOR_BOUNDARY")


def job(*, project=PROJECT, canonical=True):
    return {
        "id": JOB, "project_id": project, "status": "queued",
        "source_commit": F2_V2_SEED, "workspace": None,
        "task": {"title": "F2-T01", "description": "Bounded fixture repair"},
        "checkpoint": ({
            "canonical_intake": {
                "mode": "direct", "bounded_direct": True,
                "decomposition_required": False,
                "baseline_revision": F2_V2_REVISION,
            }
        } if canonical else {}),
        "progress": {}, "repo_analysis": None,
    }


def engine_for(monkeypatch, tmp_path, row, *, f2):
    storage = ReadStorage(row)
    engine = execution.RuntimeEngine(storage)
    engine._f2_worker_only = f2
    engine.workspace_root = Path(tmp_path)
    worker = HaltAtWorkspace()
    engine.ddev = worker
    monkeypatch.setattr(
        execution, "project_config",
        lambda project_id: {
            "path": str(tmp_path / "fixed-fixture"),
            "runtime": {"workspace_mode": "isolated_clone"},
            "ddev": {"enabled": False},
        },
    )
    monkeypatch.setattr(
        engine, "_ensure_review_repair_churn_epoch",
        lambda **kwargs: None,
    )
    return engine, worker


def test_f2_existing_engine_requests_exact_isolated_clone(monkeypatch, tmp_path):
    f2_env(monkeypatch)
    engine, executor = engine_for(
        monkeypatch, tmp_path, job(), f2=True,
    )
    with pytest.raises(RuntimeError, match="STOP_AT_F2_EXECUTOR_BOUNDARY"):
        asyncio.run(engine.run_job(JOB))
    assert executor.calls == [{
        "job_id": JOB, "project_id": PROJECT,
        "ref": F2_V2_SEED, "workspace_mode": "isolated_clone",
    }]


def test_legacy_workspace_request_keeps_project_default(monkeypatch, tmp_path):
    engine, executor = engine_for(
        monkeypatch, tmp_path, job(project="demo", canonical=False),
        f2=False,
    )
    with pytest.raises(RuntimeError, match="STOP_AT_F2_EXECUTOR_BOUNDARY"):
        asyncio.run(engine.run_job(JOB))
    assert executor.calls == [{
        "job_id": JOB, "project_id": "demo",
        "ref": F2_V2_SEED,
    }]


@pytest.mark.parametrize("row", [
    job(project="chonhac"),
    job(canonical=False),
    {**job(), "source_commit": "b" * 40},
])
def test_direct_python_worker_cannot_route_other_or_unaudited_job(
    monkeypatch, tmp_path, row,
):
    f2_env(monkeypatch)
    engine, executor = engine_for(monkeypatch, tmp_path, row, f2=True)
    with pytest.raises(F2WorkerNotReady, match="unaudited or foreign"):
        asyncio.run(engine.run_job(JOB))
    assert executor.calls == []
