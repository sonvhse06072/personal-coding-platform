from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from app import main
from app.plan_orchestrator import PlanOrchestrator
from test_plan_orchestrator import plan_row, tracked, work_order
from test_plan_orchestrator_store import Result
from test_work_order_checkpoints import CheckpointConnection, CheckpointStorage, checkpoint


class ProgressConnection(CheckpointConnection):
    def execute(self, sql, params=None):
        normalized = " ".join(sql.split())
        if normalized.startswith("SET TRANSACTION"):
            self.storage.read_statements.append(normalized)
            assert normalized == "SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY"
            return Result()
        if normalized.startswith("SELECT o.plan_id"):
            self.storage.read_statements.append(normalized)
            return Result(row=self.storage.plan if params[0] == self.storage.plan["plan_id"] else None)
        if normalized.startswith("SELECT work_order_id, state, job_id"):
            self.storage.read_statements.append(normalized)
            assert "lifecycle='active'" in normalized
            assert "ORDER BY sequence_no, work_order_id" in normalized
            rows = sorted(self.storage.tracked, key=lambda row: (row["sequence_no"], row["work_order_id"]))
            return Result(rows=[
                {key: row[key] for key in ("work_order_id", "state", "job_id")}
                for row in rows if row["lifecycle"] == "active"
            ])
        if normalized.startswith("SELECT * FROM cp_plan_orchestrations"):
            return Result(row=self.storage.plan)
        if normalized.startswith("SELECT * FROM cp_plan_work_orders"):
            return Result(rows=self.storage.tracked)
        return super().execute(sql, params)


class ProgressStorage(CheckpointStorage):
    def __init__(self):
        super().__init__()
        self.plan = plan_row([
            work_order("WO-1"), work_order("WO-2", dependencies=["WO-1"]),
            work_order("WO-3", dependencies=["WO-1", "WO-2"]),
        ])
        self.plan.update(plan_id="plan-1", lifecycle="active")
        self.tracked = [tracked(f"WO-{i}", i, plan_id="plan-1") for i in range(1, 4)]
        self.read_statements = []

    def connect(self):
        return ProgressConnection(self)


@pytest.fixture
def progress_service():
    storage = ProgressStorage()
    # No engine is needed or available to the projection.
    return PlanOrchestrator(storage, None)


def test_fresh_pending_progress_is_compact_deterministic_and_read_only(progress_service):
    storage = progress_service.storage
    before = deepcopy(storage.__dict__)
    expected = {
        "plan_id": "plan-1", "project_id": "demo", "ticket_id": "GH-5",
        "state": "active", "lifecycle": "active", "completed": 0, "total": 3,
        "current_work_order": None, "blocked": None, "next": ["WO-1"], "last_checkpoint": None,
    }
    assert progress_service.progress("plan-1") == expected
    assert progress_service.progress("plan-1") == expected
    after = storage.__dict__
    for field in before.keys() - {"statements", "read_statements"}:
        assert after[field] == before[field]
    assert all(sql.startswith(("SELECT", "SET TRANSACTION")) for sql in storage.statements + storage.read_statements)


@pytest.mark.parametrize("state,status", [
    ("running", "executing"), ("awaiting_merge", "waiting_merge"), ("waiting_human", "waiting_human"),
])
def test_current_work_order_uses_busy_states(progress_service, state, status):
    progress_service.storage.tracked[0].update(state=state, job_id="job-1")
    progress_service.storage.plan["status"] = status
    result = progress_service.progress("plan-1")
    assert result["current_work_order"] == "WO-1"
    assert result["state"] == status
    assert result["completed"] == 0
    assert result["next"] == []


def test_blocked_identity_excludes_raw_details_and_does_not_unlock_dependencies(progress_service):
    progress_service.storage.tracked[0].update(state="blocked", job_id="job-1", detail={"raw_result": "private"})
    progress_service.storage.plan["status"] = "blocked"
    result = progress_service.progress("plan-1")
    assert result["blocked"] == {"work_order_id": "WO-1", "job_id": "job-1"}
    assert result["current_work_order"] is None
    assert result["state"] == "blocked"
    assert result["next"] == []
    assert "private" not in str(result)


@pytest.mark.parametrize("completed,ready", [(1, ["WO-2"]), (2, ["WO-3"]), (3, [])])
def test_completed_count_and_dependency_derived_next(progress_service, completed, ready):
    for row in progress_service.storage.tracked[:completed]:
        row["state"] = "completed"
    if completed == 3:
        progress_service.storage.plan["status"] = "completed"
    result = progress_service.progress("plan-1")
    assert result["completed"] == completed
    assert result["total"] == 3
    assert result["next"] == ready  # Ignores stale plan.ready_work_order_ids = [WO-1].
    if completed == 3:
        assert result["state"] == "completed"


@pytest.mark.parametrize("state", ["pending", "running", "awaiting_merge", "waiting_human", "blocked", "completed"])
def test_superseded_work_never_counts_or_unlocks_dependents(progress_service, state):
    progress_service.storage.tracked[0].update(state=state, lifecycle="superseded")
    result = progress_service.progress("plan-1")
    assert result["total"] == 2
    assert result["completed"] == 0
    assert result["current_work_order"] is None
    assert result["blocked"] is None
    assert result["next"] == []


def test_missing_definition_and_missing_dependency_fail_closed(progress_service):
    progress_service.storage.plan["plan"]["work_orders"] = [work_order("WO-2", dependencies=["missing"])]
    assert progress_service.progress("plan-1")["next"] == []


def test_empty_and_fully_superseded_plan_projection(progress_service):
    for row in progress_service.storage.tracked:
        row["lifecycle"] = "superseded"
    progress_service.storage.plan["lifecycle"] = "superseded"
    result = progress_service.progress("plan-1")
    assert result["lifecycle"] == "superseded"
    assert (result["completed"], result["total"], result["next"]) == (0, 0, [])
    progress_service.storage.tracked = []
    progress_service.storage.plan["plan"]["work_orders"] = []
    assert progress_service.progress("plan-1")["total"] == 0


def test_ready_list_includes_all_independent_pending_work_in_sequence_order(progress_service):
    progress_service.storage.plan["plan"]["work_orders"] = [work_order(f"WO-{i}") for i in (3, 2, 1)]
    progress_service.storage.tracked.reverse()
    assert progress_service.progress("plan-1")["next"] == ["WO-1", "WO-2", "WO-3"]


def test_latest_checkpoint_is_plan_scoped_and_survives_supersession(progress_service, monkeypatch):
    monkeypatch.setattr("app.plan_orchestrator.now", lambda: datetime(2026, 9, 29, tzinfo=timezone.utc))
    store = progress_service.store
    store.append_checkpoint(**checkpoint())
    latest = store.append_checkpoint(**checkpoint(checkpoint_key="latest", work_order_id="WO-2"))
    store.append_checkpoint(**checkpoint(checkpoint_key="unrelated", plan_id="plan-2"))
    progress_service.storage.tracked[1]["lifecycle"] = "superseded"
    assert progress_service.progress("plan-1")["last_checkpoint"] == latest
    assert store.checkpoints("plan-1", work_order_id="WO-2") == [latest]
    assert len(store.checkpoints("plan-1")) == 2


def test_progress_api_auth_unknown_plan_and_existing_orchestration_contract(progress_service, monkeypatch):
    monkeypatch.setenv("RUNTIME_API_TOKEN", "test-progress-token")
    monkeypatch.setattr(main, "plan_orchestrator", progress_service)
    client = TestClient(main.app)  # No context manager: never starts Runtime workers.
    path = "/v1/plans/plan-1/progress"
    assert client.get(path).status_code == 401
    assert client.get(path, headers={"Authorization": "Bearer wrong"}).status_code == 401
    assert progress_service.storage.read_statements == []
    headers = {"Authorization": "Bearer test-progress-token"}
    response = client.get(path, headers=headers)
    assert response.status_code == 200
    assert response.json() == progress_service.progress("plan-1")
    assert client.get("/v1/plans/unknown/progress", headers=headers).status_code == 404
    progress_service.store.append_checkpoint(**checkpoint())
    assert client.get(path, headers=headers).json()["last_checkpoint"]["created_at"]
    before = deepcopy(progress_service.view("plan-1"))
    progress_service.progress("plan-1")
    assert progress_service.view("plan-1") == before
    legacy = client.get("/v1/plans/plan-1/orchestration", headers=headers)
    assert legacy.status_code == 200
    assert legacy.json()["work_orders"] == before["work_orders"]
    assert "last_checkpoint" not in legacy.json()
    assert "completed" not in legacy.json()
    assert client.post(path, headers=headers, json={}).status_code == 405
