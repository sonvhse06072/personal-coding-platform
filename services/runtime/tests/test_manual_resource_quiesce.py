import asyncio

import app.engine_core as engine_core
from app.engine_core import RuntimeEngineCore
from app.work_order_checkpoints import launch_identity


class FakeStorage:
    def __init__(self, rows):
        self.rows = rows

    def get(self, job_id):
        row = self.rows.get(job_id)
        return dict(row) if row else None

    def update(self, job_id, **fields):
        self.rows[job_id].update(fields)

    def list(self, limit=500):
        return list(self.rows.values())[:limit]

    def init(self):
        return None


class FakeDdev:
    def __init__(self, *, fail=False):
        self.calls = []
        self.fail = fail

    async def quiesce_workspace(
        self,
        *,
        job_id,
        project_id,
        workspace,
        remove_data=False,
    ):
        self.calls.append({
            "job_id": job_id,
            "project_id": project_id,
            "workspace": workspace,
            "remove_data": remove_data,
        })
        if self.fail:
            raise RuntimeError("cleanup failed")
        return {
            "quiesced": True,
            "data_removed": bool(remove_data),
        }

    async def cancel(self, *, job_id):
        return True


def row(status, *, checkpoint=None):
    return {
        "id": "job-manual-1",
        "project_id": "demo",
        "status": status,
        "workspace": "/tmp/workspaces/job-manual-1",
        "checkpoint": dict(checkpoint or {}),
    }


def engine(monkeypatch, status, *, checkpoint=None, fail=False):
    storage = FakeStorage({
        "job-manual-1": row(
            status,
            checkpoint=checkpoint,
        )
    })
    runtime = RuntimeEngineCore(storage)
    runtime.ddev = FakeDdev(fail=fail)
    monkeypatch.setattr(
        engine_core,
        "project_config",
        lambda project_id: {"ddev": {"enabled": True}},
    )
    return runtime, storage


def test_blocked_manual_job_quiesces_without_data_removal(monkeypatch):
    runtime, storage = engine(monkeypatch, "blocked")

    asyncio.run(runtime._quiesce_stable_manual_job("job-manual-1"))

    assert runtime.ddev.calls == [{
        "job_id": "job-manual-1",
        "project_id": "demo",
        "workspace": "/tmp/workspaces/job-manual-1",
        "remove_data": False,
    }]
    assert storage.rows["job-manual-1"]["status"] == "blocked"
    assert storage.rows["job-manual-1"]["checkpoint"]["resource_quiesce"] == {
        "quiesced": True,
        "data_removed": False,
        "status": "blocked",
    }


def test_failed_manual_job_quiesces_without_data_removal(monkeypatch):
    runtime, _storage = engine(monkeypatch, "failed")

    asyncio.run(runtime._quiesce_stable_manual_job("job-manual-1"))

    assert runtime.ddev.calls[0]["remove_data"] is False


def test_completed_manual_job_releases_data(monkeypatch):
    runtime, storage = engine(monkeypatch, "completed")

    asyncio.run(runtime._quiesce_stable_manual_job("job-manual-1"))

    assert runtime.ddev.calls[0]["remove_data"] is True
    assert storage.rows["job-manual-1"]["status"] == "completed"


def test_orchestrated_job_is_left_to_plan_orchestrator(monkeypatch):
    identity = launch_identity("plan-1", "WO-1")
    checkpoint = {
        "work_order": {"id": "WO-1"},
        "orchestrator_launch": {**identity, "state": "launched"},
    }
    storage = FakeStorage({
        identity["job_id"]: {
            "id": identity["job_id"],
            "project_id": "demo",
            "status": "blocked",
            "workspace": f"/tmp/workspaces/{identity['job_id']}",
            "checkpoint": checkpoint,
        }
    })
    runtime = RuntimeEngineCore(storage)
    runtime.ddev = FakeDdev()
    monkeypatch.setattr(
        engine_core,
        "project_config",
        lambda project_id: {"ddev": {"enabled": True}},
    )

    asyncio.run(runtime._quiesce_stable_manual_job(identity["job_id"]))

    assert runtime.ddev.calls == []
    assert storage.rows[identity["job_id"]]["checkpoint"] == checkpoint


def test_standalone_work_order_without_orchestrator_launch_still_quiesces(monkeypatch):
    runtime, storage = engine(
        monkeypatch,
        "blocked",
        checkpoint={"work_order": {"id": "WO-STANDALONE"}},
    )

    asyncio.run(runtime._quiesce_stable_manual_job("job-manual-1"))

    assert runtime.ddev.calls == [{
        "job_id": "job-manual-1",
        "project_id": "demo",
        "workspace": "/tmp/workspaces/job-manual-1",
        "remove_data": False,
    }]
    assert storage.rows["job-manual-1"]["checkpoint"]["work_order"] == {
        "id": "WO-STANDALONE"
    }
    assert storage.rows["job-manual-1"]["checkpoint"]["resource_quiesce"] == {
        "quiesced": True,
        "data_removed": False,
        "status": "blocked",
    }


def test_cleanup_failure_is_recorded_without_changing_primary_status(monkeypatch):
    runtime, storage = engine(monkeypatch, "blocked", fail=True)

    asyncio.run(runtime._quiesce_stable_manual_job("job-manual-1"))

    assert storage.rows["job-manual-1"]["status"] == "blocked"
    detail = storage.rows["job-manual-1"]["checkpoint"]["resource_quiesce"]
    assert detail["quiesced"] is False
    assert detail["data_removed"] is False
    assert detail["status"] == "blocked"
    assert "cleanup failed" in detail["error"]


def test_cancelled_manual_job_releases_data(monkeypatch):
    runtime, storage = engine(monkeypatch, "queued")

    result = asyncio.run(runtime.cancel("job-manual-1"))

    assert result["status"] == "cancelled"
    assert runtime.ddev.calls[-1]["remove_data"] is True
    assert storage.rows["job-manual-1"]["checkpoint"]["resource_quiesce"] == {
        "quiesced": True,
        "data_removed": True,
        "status": "cancelled",
    }
