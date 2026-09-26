from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

import app.engine_execution as engine_execution
from app.engine_execution import RuntimeEngine


JOB_ID = "0123456789abcdef0123456789abcdef"


class FakeStorage:
    def __init__(self, row, *, prefix_rows=None):
        self.row = dict(row)
        self.prefix_rows = (
            list(prefix_rows)
            if prefix_rows is not None
            else [
                {
                    "id": self.row["id"],
                    "project_id": self.row["project_id"],
                    "status": self.row["status"],
                    "workspace": self.row.get("workspace"),
                }
            ]
        )

    def get(self, job_id):
        return dict(self.row) if job_id == self.row["id"] else None

    def jobs_with_id_prefix(self, prefix):
        assert prefix == JOB_ID[:10]
        return [dict(item) for item in self.prefix_rows]


class FakeDdev:
    def __init__(self):
        self.orphan_calls = []
        self.quiesce_calls = []
        self.remove_calls = []

    async def orphan_resources(
        self,
        *,
        job_id,
        project_id,
        workspace,
        execute,
    ):
        self.orphan_calls.append(
            {
                "job_id": job_id,
                "project_id": project_id,
                "workspace": workspace,
                "execute": execute,
            }
        )
        if execute:
            return {
                "mode": "execute",
                "released": True,
                "before": {"resource_count": 3},
                "after": {"resource_count": 0},
            }
        return {
            "mode": "inspect",
            "released": False,
            "before": {"resource_count": 3},
            "after": {"resource_count": 3},
        }

    async def quiesce_workspace(self, **payload):
        self.quiesce_calls.append(dict(payload))
        return {"quiesced": True, "data_removed": bool(payload["remove_data"])}

    async def remove_workspace(self, **payload):
        self.remove_calls.append(dict(payload))
        return {"removed": True, "preserved": False}


def make_engine(monkeypatch, row, *, prefix_rows=None):
    runtime = object.__new__(RuntimeEngine)
    runtime.storage = FakeStorage(row, prefix_rows=prefix_rows)
    runtime.ddev = FakeDdev()
    monkeypatch.setattr(
        engine_execution,
        "project_config",
        lambda project_id: {"ddev": {"enabled": True}},
    )
    return runtime


@pytest.mark.parametrize("status", ["completed", "cancelled"])
def test_missing_workspace_terminal_cleanup_inspects_then_releases(
    monkeypatch,
    tmp_path,
    status,
):
    missing = tmp_path / "missing-workspace"
    row = {
        "id": JOB_ID,
        "project_id": "demo",
        "status": status,
        "workspace": str(missing),
    }
    runtime = make_engine(monkeypatch, row)

    result = asyncio.run(
        runtime.cleanup(
            JOB_ID,
            remove_workspace=False,
            release_ddev_data=True,
        )
    )

    assert [item["execute"] for item in runtime.ddev.orphan_calls] == [
        False,
        True,
    ]
    assert runtime.ddev.orphan_calls[0]["workspace"] == str(missing)
    assert runtime.ddev.quiesce_calls == []
    assert runtime.ddev.remove_calls == []
    assert result["cleaned"] is True
    assert result["ddev_data_released"] is True
    assert result["ddev_orphan"]["release"]["after"]["resource_count"] == 0
    assert result["workspace_removed"] is False


def test_missing_workspace_field_can_release_exact_terminal_resources(
    monkeypatch,
):
    row = {
        "id": JOB_ID,
        "project_id": "demo",
        "status": "completed",
        "workspace": None,
    }
    runtime = make_engine(monkeypatch, row)

    result = asyncio.run(
        runtime.cleanup(JOB_ID, release_ddev_data=True)
    )

    assert runtime.ddev.orphan_calls[0]["workspace"] is None
    assert result["ddev_data_released"] is True


@pytest.mark.parametrize(
    "status",
    ["queued", "executing", "blocked", "waiting_human", "failed"],
)
def test_missing_workspace_cleanup_refuses_noneligible_status(
    monkeypatch,
    tmp_path,
    status,
):
    row = {
        "id": JOB_ID,
        "project_id": "demo",
        "status": status,
        "workspace": str(tmp_path / "gone"),
    }
    runtime = make_engine(monkeypatch, row)

    with pytest.raises(RuntimeError) as exc:
        asyncio.run(
            runtime.cleanup(JOB_ID, release_ddev_data=True)
        )

    assert "completed/cancelled" in str(exc.value)
    assert runtime.ddev.orphan_calls == []


def test_missing_workspace_cleanup_refuses_ambiguous_job_prefix(
    monkeypatch,
    tmp_path,
):
    row = {
        "id": JOB_ID,
        "project_id": "demo",
        "status": "cancelled",
        "workspace": str(tmp_path / "gone"),
    }
    collision = {
        "id": JOB_ID[:10] + "aaaaaaaaaaaaaaaaaaaaaa",
        "project_id": "other",
        "status": "completed",
        "workspace": None,
    }
    runtime = make_engine(
        monkeypatch,
        row,
        prefix_rows=[
            {
                "id": JOB_ID,
                "project_id": "demo",
                "status": "cancelled",
                "workspace": row["workspace"],
            },
            collision,
        ],
    )

    with pytest.raises(RuntimeError) as exc:
        asyncio.run(
            runtime.cleanup(JOB_ID, release_ddev_data=True)
        )

    assert "unambiguous exact job prefix" in str(exc.value)
    assert runtime.ddev.orphan_calls == []


def test_workspace_present_keeps_normal_quiesce_path(
    monkeypatch,
    tmp_path,
):
    workspace = tmp_path / "workspace"
    (workspace / ".git").mkdir(parents=True)
    row = {
        "id": JOB_ID,
        "project_id": "demo",
        "status": "completed",
        "workspace": str(workspace),
    }
    runtime = make_engine(monkeypatch, row)

    result = asyncio.run(
        runtime.cleanup(JOB_ID, release_ddev_data=True)
    )

    assert runtime.ddev.orphan_calls == []
    assert runtime.ddev.quiesce_calls == [
        {
            "job_id": JOB_ID,
            "project_id": "demo",
            "workspace": str(workspace),
            "remove_data": True,
        }
    ]
    assert result["ddev_data_released"] is True


def test_missing_workspace_without_release_is_read_only(
    monkeypatch,
    tmp_path,
):
    row = {
        "id": JOB_ID,
        "project_id": "demo",
        "status": "completed",
        "workspace": str(tmp_path / "gone"),
    }
    runtime = make_engine(monkeypatch, row)

    result = asyncio.run(runtime.cleanup(JOB_ID))

    assert result == {
        "cleaned": False,
        "reason": "workspace unavailable",
        "workspace": row["workspace"],
    }
    assert runtime.ddev.orphan_calls == []
