from __future__ import annotations

from copy import deepcopy

from app.storage import Storage
from app.telemetry_storage import TELEMETRY_DDL, TelemetryStorage


def base_row() -> dict:
    return {
        "id": "job-1",
        "project_id": "project-a",
        "status": "executing",
        "task": {"title": "Task", "task_type": "bugfix"},
        "route": {
            "strategy": {
                "profile": "fast",
                "executor": {"id": "model-a", "provider": "provider-a"},
                "budget": {
                    "max_model_calls": 3,
                    "max_tool_calls": 20,
                    "max_iterations": 2,
                    "max_repair_iterations": 1,
                    "max_test_runs": 3,
                    "max_wall_time_minutes": 10,
                },
            }
        },
        "checkpoint": {},
        "progress": {"model_calls": 1, "iteration": 1},
        "result": None,
    }


def test_schema_persists_task_attention_and_continuity_evidence() -> None:
    assert "CREATE TABLE IF NOT EXISTS cp_task_telemetry" in TELEMETRY_DDL
    assert "CREATE TABLE IF NOT EXISTS cp_attention_events" in TELEMETRY_DDL
    assert "CREATE TABLE IF NOT EXISTS cp_continuity_proposals" in TELEMETRY_DDL
    assert "project_id, task_type, role" in TELEMETRY_DDL


def test_stable_block_transition_upserts_one_snapshot_and_continuity_proposal(monkeypatch) -> None:
    rows = {"job-1": base_row()}
    storage = TelemetryStorage()
    snapshots = []
    continuity = []

    monkeypatch.setattr(storage, "get", lambda job_id: deepcopy(rows.get(job_id)))

    def fake_base_update(self, job_id, **fields):
        rows[job_id].update(deepcopy(fields))

    monkeypatch.setattr(Storage, "update", fake_base_update)
    monkeypatch.setattr(storage, "_record_attention_transition", lambda previous, current: None)
    monkeypatch.setattr(storage, "_record_budget_attention", lambda previous, current: None)
    monkeypatch.setattr(storage, "_upsert_task_telemetry", lambda snapshot: snapshots.append(snapshot))
    monkeypatch.setattr(
        storage,
        "_persist_continuity",
        lambda row, *, event_type, telemetry, payload=None: continuity.append(
            {"event_type": event_type, "telemetry": telemetry}
        ),
    )

    storage.update(
        "job-1",
        status="blocked",
        result={"reason": "verification_failed"},
        progress={"model_calls": 2, "iteration": 1, "repair_iterations": 0},
    )

    assert len(snapshots) == 1
    assert snapshots[0]["status"] == "blocked"
    assert snapshots[0]["terminal"] is False
    assert continuity == [{"event_type": "job_blocked", "telemetry": snapshots[0]}]


def test_non_stable_execution_update_does_not_create_calibration_sample(monkeypatch) -> None:
    rows = {"job-1": base_row()}
    storage = TelemetryStorage()
    snapshots = []

    monkeypatch.setattr(storage, "get", lambda job_id: deepcopy(rows.get(job_id)))

    def fake_base_update(self, job_id, **fields):
        rows[job_id].update(deepcopy(fields))

    monkeypatch.setattr(Storage, "update", fake_base_update)
    monkeypatch.setattr(storage, "_record_attention_transition", lambda previous, current: None)
    monkeypatch.setattr(storage, "_record_budget_attention", lambda previous, current: None)
    monkeypatch.setattr(storage, "_upsert_task_telemetry", lambda snapshot: snapshots.append(snapshot))

    storage.update("job-1", progress={"model_calls": 2, "iteration": 1})

    assert snapshots == []
