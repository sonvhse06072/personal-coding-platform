from __future__ import annotations

import asyncio
from pathlib import Path

from app.engine_execution import RuntimeEngine as ExecutionRuntimeEngine
from app.engine_core import RuntimeEngineCore


class CleanupStorage:
    def __init__(self, row):
        self.row = dict(row)
        self.released = []

    def get(self, job_id):
        return dict(self.row) if job_id == self.row["id"] else None

    def release_project_lease(self, project_id, job_id):
        self.released.append((project_id, job_id))
        return True


class CleanupDdev:
    def __init__(self):
        self.quiesce_calls = []
        self.remove_calls = []

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
