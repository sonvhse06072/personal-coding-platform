from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from app.engine_execution import RuntimeEngine as ExecutionRuntimeEngine
from app.engine_core import RuntimeEngineCore


class CleanupStorage:
    def __init__(self, row, *, preview=None):
        self.row = dict(row)
        self.released = []
        self.preview = dict(preview) if preview else None
        self.actions = []

    def init(self):
        return None

    def list(self, limit=500):
        return [dict(self.row)]

    def get(self, job_id):
        return dict(self.row) if job_id == self.row["id"] else None

    def update(self, job_id, **fields):
        assert job_id == self.row["id"]
        self.row.update(fields)

    def preview_state(self, job_id):
        return dict(self.preview) if job_id == self.row["id"] and self.preview else None

    def upsert_preview_state(
        self,
        *,
        job_id,
        project_id,
        target,
        status,
        generation,
        frontend_url=None,
        backend_url=None,
        integration_note=None,
        error=None,
        stopped=False,
    ):
        self.preview = {
            "job_id": job_id,
            "project_id": project_id,
            "target": target,
            "status": status,
            "generation": generation,
            "frontend_url": frontend_url,
            "backend_url": backend_url,
            "integration_note": integration_note,
            "error": error,
            "updated_at": None,
            "stopped_at": None,
        }
        self.actions.append(("preview_state", status))
        return dict(self.preview)

    def terminal_active_project_leases(self):
        if str(self.row.get("status") or "") in {"completed", "failed", "cancelled"}:
            return [{
                "project_id": self.row["project_id"],
                "owner_job_id": self.row["id"],
                "state": "active",
            }]
        return []

    def reconcile_terminal_project_leases(self):
        self.actions.append(("reconcile_leases", self.row["id"]))
        return 1

    def release_project_lease(self, project_id, job_id):
        self.actions.append(("release_lease", job_id))
        self.released.append((project_id, job_id))
        return True


class CleanupDdev:
    def __init__(self, actions=None, *, fail_preview_stop=False):
        self.quiesce_calls = []
        self.remove_calls = []
        self.preview_stop_calls = []
        self.cancel_calls = []
        self.actions = actions if actions is not None else []
        self.fail_preview_stop = fail_preview_stop

    async def cancel(self, **payload):
        self.cancel_calls.append(dict(payload))
        self.actions.append(("cancel_executor", payload["job_id"]))
        return True

    async def preview_stop(self, **payload):
        self.preview_stop_calls.append(dict(payload))
        self.actions.append(("preview_stop", payload["job_id"]))
        if self.fail_preview_stop:
            raise RuntimeError("executor stop failed")
        return {"status": "stopped"}

    async def quiesce_workspace(self, **payload):
        self.quiesce_calls.append(dict(payload))
        return {
            "quiesced": False,
            "data_removed": False,
            "preserved": True,
            "reason": "direct_workspace_preserved",
        }

    async def remove_workspace(self, **payload):
        self.remove_calls.append(dict(payload))
        return {
            "removed": False,
            "preserved": True,
            "workspace": payload["workspace"],
            "reason": "direct_workspace_source_preserved",
        }


def test_cleanup_reports_preserved_direct_workspace_truthfully(monkeypatch, tmp_path):
    workspace = tmp_path / "chonhac"
    workspace.mkdir()
    storage = CleanupStorage(
        {
            "id": "job-direct-cleanup",
            "project_id": "chonhac",
            "workspace": str(workspace),
            "status": "cancelled",
            "checkpoint": {"workspace_mode": "direct"},
        }
    )
    engine = object.__new__(ExecutionRuntimeEngine)
    engine.storage = storage
    engine.ddev = CleanupDdev()

    monkeypatch.setattr(
        "app.engine_execution.project_config",
        lambda project_id: {"ddev": {"enabled": True}},
    )

    result = asyncio.run(
        engine.cleanup(
            "job-direct-cleanup",
            remove_workspace=True,
            release_ddev_data=True,
        )
    )

    assert result["cleaned"] is True
    assert result["workspace_removed"] is False
    assert result["workspace_preserved"] is True
    assert result["ddev_data_released"] is False
    assert engine.ddev.quiesce_calls[0]["remove_data"] is True
    assert len(engine.ddev.remove_calls) == 1
    assert workspace.exists()


def test_terminal_direct_lease_release_uses_durable_checkpoint_not_live_config():
    storage = CleanupStorage(
        {
            "id": "job-direct-terminal",
            "project_id": "chonhac",
            "workspace": "/home/sonvh/chonhac",
            "status": "completed",
            "checkpoint": {"workspace_mode": "direct"},
        }
    )
    engine = object.__new__(RuntimeEngineCore)
    engine.storage = storage

    assert engine._release_terminal_direct_lease("job-direct-terminal") is True
    assert storage.released == [("chonhac", "job-direct-terminal")]


def test_terminal_isolated_job_never_releases_project_lease():
    storage = CleanupStorage(
        {
            "id": "job-isolated-terminal",
            "project_id": "chonhac",
            "workspace": "/tmp/workspaces/job-isolated-terminal",
            "status": "completed",
            "checkpoint": {"workspace_mode": "isolated_clone"},
        }
    )
    engine = object.__new__(RuntimeEngineCore)
    engine.storage = storage

    assert engine._release_terminal_direct_lease("job-isolated-terminal") is False
    assert storage.released == []



def test_cancel_retires_direct_preview_before_releasing_project_lease():
    row = {
        "id": "job-direct-cancel",
        "project_id": "chonhac",
        "workspace": "/home/sonvh/chonhac",
        "work_order_id": "WO-DIRECT",
        "status": "executing",
        "checkpoint": {"workspace_mode": "direct"},
    }
    storage = CleanupStorage(
        row,
        preview={
            "job_id": row["id"],
            "project_id": "chonhac",
            "target": "frontend",
            "status": "ready",
            "generation": 1,
        },
    )
    ddev = CleanupDdev(storage.actions)
    engine = object.__new__(RuntimeEngineCore)
    engine.storage = storage
    engine.ddev = ddev
    engine.active_jobs = {}

    result = asyncio.run(engine.cancel(row["id"]))

    assert result["status"] == "cancelled"
    assert len(ddev.preview_stop_calls) == 1
    preview_index = storage.actions.index(("preview_stop", row["id"]))
    release_index = storage.actions.index(("release_lease", row["id"]))
    assert preview_index < release_index
    assert storage.preview["status"] == "stopped"


def test_runtime_start_retires_terminal_preview_before_lease_reconciliation(monkeypatch):
    async def scenario():
        row = {
            "id": "job-direct-restart",
            "project_id": "chonhac",
            "workspace": "/home/sonvh/chonhac",
            "work_order_id": "WO-DIRECT",
            "status": "completed",
            "checkpoint": {"workspace_mode": "direct"},
        }
        storage = CleanupStorage(
            row,
            preview={
                "job_id": row["id"],
                "project_id": "chonhac",
                "target": "both",
                "status": "ready",
                "generation": 2,
            },
        )
        ddev = CleanupDdev(storage.actions)
        engine = RuntimeEngineCore(storage)
        engine.ddev = ddev

        async def no_antigravity_runs():
            return None

        monkeypatch.setattr(
            "app.engine_core.cancel_all_antigravity_runs",
            no_antigravity_runs,
        )

        await engine.start()
        try:
            assert len(ddev.preview_stop_calls) == 1
            preview_index = storage.actions.index(("preview_stop", row["id"]))
            reconcile_index = storage.actions.index(("reconcile_leases", row["id"]))
            assert preview_index < reconcile_index
            assert storage.preview["status"] == "stopped"
        finally:
            if engine.worker_task:
                engine.worker_task.cancel()
                try:
                    await engine.worker_task
                except asyncio.CancelledError:
                    pass

    asyncio.run(scenario())



def test_cancel_keeps_direct_lease_when_preview_retirement_fails():
    row = {
        "id": "job-direct-cancel-failed-preview",
        "project_id": "chonhac",
        "workspace": "/home/sonvh/chonhac",
        "work_order_id": "WO-DIRECT",
        "status": "executing",
        "checkpoint": {"workspace_mode": "direct"},
    }
    storage = CleanupStorage(
        row,
        preview={
            "job_id": row["id"],
            "project_id": "chonhac",
            "target": "frontend",
            "status": "ready",
            "generation": 1,
        },
    )
    ddev = CleanupDdev(storage.actions, fail_preview_stop=True)
    engine = object.__new__(RuntimeEngineCore)
    engine.storage = storage
    engine.ddev = ddev
    engine.active_jobs = {}

    result = asyncio.run(engine.cancel(row["id"]))

    assert result["status"] == "cancelled"
    assert len(ddev.preview_stop_calls) == 1
    assert storage.preview["status"] == "failed"
    assert storage.released == []
    assert ("release_lease", row["id"]) not in storage.actions


class HandoffStorage:
    def __init__(self, workspace: Path):
        self.workspace = workspace
        self.actions = []
        self.job = {
            "id": "job-direct-handoff",
            "project_id": "chonhac",
            "status": "queued",
            "source_commit": None,
            "workspace": None,
            "branch": None,
            "task": {"title": "handoff", "description": "bounded"},
            "repo_analysis": None,
            "progress": {},
            "checkpoint": {},
            "result": None,
            "error": None,
        }

    def get(self, job_id):
        return dict(self.job) if job_id == self.job["id"] else None

    def update(self, job_id, **fields):
        assert job_id == self.job["id"]
        self.job.update(fields)
        self.actions.append(("update", tuple(sorted(fields))))

    def acquire_project_lease(self, project_id, job_id):
        self.actions.append(("acquire", job_id))
        return {
            "project_id": project_id,
            "owner_job_id": job_id,
            "state": "active",
            "generation": 1,
        }

    def release_project_lease(self, project_id, job_id):
        self.actions.append(("release", job_id))
        return True


class HandoffDdev:
    def __init__(self, storage: HandoffStorage):
        self.storage = storage
        self.create_calls = []

    async def create_workspace(self, **payload):
        self.storage.actions.append(("create_workspace", payload["job_id"]))
        self.create_calls.append(dict(payload))
        return {
            "workspace": str(self.storage.workspace),
            "branch": "ai/job-direct-h",
            "source_commit": "abcdef1234567890",
            "workspace_mode": "direct",
        }


def _handoff_project_config(workspace: Path):
    return {
        "path": str(workspace),
        "base_branch": "main",
        "runtime": {
            "workspace_mode": "direct",
            "exclusive_project_lease": True,
        },
        "preview": {
            "backend": {"enabled": True},
            "frontend": {"enabled": True},
        },
    }


def test_direct_job_retires_idle_preview_after_lease_before_workspace_mutation(
    monkeypatch,
    tmp_path,
):
    workspace = tmp_path / "chonhac"
    workspace.mkdir()
    storage = HandoffStorage(workspace)
    engine = ExecutionRuntimeEngine(storage)
    engine.ddev = HandoffDdev(storage)

    class HandoffPreview:
        def __init__(self, _storage, _ddev):
            pass

        async def handoff_to_job(self, project_id, job_id):
            storage.actions.append(("handoff", job_id))

    monkeypatch.setenv("CODING_DIRECT_PROJECT_ROOT", str(workspace))
    monkeypatch.setattr(
        "app.engine_execution.project_config",
        lambda project_id: _handoff_project_config(workspace),
    )
    monkeypatch.setattr("app.engine_execution.ProjectPreviewManager", HandoffPreview)

    def stop_after_workspace(*_args, **_kwargs):
        raise RuntimeError("stop after workspace proof")

    monkeypatch.setattr("app.engine_execution.analyze_repo", stop_after_workspace)

    with pytest.raises(RuntimeError, match="stop after workspace proof"):
        asyncio.run(engine.run_job(storage.job["id"]))

    acquire = storage.actions.index(("acquire", storage.job["id"]))
    handoff = storage.actions.index(("handoff", storage.job["id"]))
    create = storage.actions.index(("create_workspace", storage.job["id"]))
    assert acquire < handoff < create


def test_direct_job_handoff_failure_releases_new_lease_before_workspace_mutation(
    monkeypatch,
    tmp_path,
):
    workspace = tmp_path / "chonhac"
    workspace.mkdir()
    storage = HandoffStorage(workspace)
    engine = ExecutionRuntimeEngine(storage)
    engine.ddev = HandoffDdev(storage)

    class FailedHandoffPreview:
        def __init__(self, _storage, _ddev):
            pass

        async def handoff_to_job(self, project_id, job_id):
            storage.actions.append(("handoff", job_id))
            raise RuntimeError("idle preview retirement failed")

    monkeypatch.setenv("CODING_DIRECT_PROJECT_ROOT", str(workspace))
    monkeypatch.setattr(
        "app.engine_execution.project_config",
        lambda project_id: _handoff_project_config(workspace),
    )
    monkeypatch.setattr(
        "app.engine_execution.ProjectPreviewManager",
        FailedHandoffPreview,
    )

    with pytest.raises(RuntimeError, match="idle preview retirement failed"):
        asyncio.run(engine.run_job(storage.job["id"]))

    assert storage.actions[:3] == [
        ("acquire", storage.job["id"]),
        ("handoff", storage.job["id"]),
        ("release", storage.job["id"]),
    ]
    assert engine.ddev.create_calls == []
