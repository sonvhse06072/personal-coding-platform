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
        if normalized.startswith("SELECT c.* FROM cp_plan_work_order_checkpoints c"):
            checkpoints = list(self.storage.checkpoint_rows.values())
            if "w.state='completed'" in normalized:
                tracked = {row["work_order_id"]: row for row in self.storage.tracked}
                checkpoints = [
                    row for row in checkpoints
                    if row["plan_id"] == params[0]
                    and row["kind"] in {"completed", "merged"}
                    and tracked[row["work_order_id"]]["state"] == "completed"
                    and tracked[row["work_order_id"]]["lifecycle"] == "active"
                    and row["job_id"] == tracked[row["work_order_id"]]["job_id"]
                ]
                checkpoints.sort(key=lambda row: (
                    tracked[row["work_order_id"]]["sequence_no"], row["work_order_id"], row["id"]
                ))
                return Result(rows=checkpoints)
            if "ORDER BY c.id DESC LIMIT 32" in normalized:
                checkpoints = [
                    row for row in checkpoints
                    if row["plan_id"] == params[0] and row["work_order_id"] == params[1]
                    and row["job_id"] == params[2]
                ]
                checkpoints.sort(key=lambda row: row["id"], reverse=True)
                return Result(rows=checkpoints[:32])
            assert "c.kind IN ('completed','merged')" in normalized
            active = {
                row["work_order_id"]: row for row in self.storage.tracked
                if row["lifecycle"] == "active"
            }
            checkpoints = [
                row for row in checkpoints
                if row["plan_id"] == params[0] and row["id"] < params[1]
                and row["kind"] in {"completed", "merged"}
                and row["work_order_id"] in active
                and row["job_id"] == active[row["work_order_id"]]["job_id"]
            ]
            checkpoints.sort(key=lambda row: row["id"], reverse=True)
            return Result(row=checkpoints[0] if checkpoints else None)
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
        "current_work_order": None, "blocked": None, "blocked_evidence": None,
        "next": ["WO-1"], "last_checkpoint": None,
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
    assert result["blocked_evidence"]["reason"] == "blocked_checkpoint_evidence_unavailable"
    assert result["blocked_evidence"]["next_safe_action"] == "repair"
    assert "private" not in str(result)


def test_blocked_pack_preserves_completed_checkpoint_and_exact_current_identity(
    progress_service, monkeypatch,
):
    storage = progress_service.storage
    storage.tracked[0].update(state="completed", job_id="job-1")
    storage.tracked[1].update(state="blocked", job_id="job-current")
    storage.plan["status"] = "blocked"
    completed = progress_service.store.append_checkpoint(**checkpoint(
        checkpoint_key="wo:merged:one", kind="merged", state="completed",
        job_id="job-1", evidence={
            "source_commit": "a" * 40, "produced_commit": "b" * 40,
            "branch": "ai/wo-1", "pr_number": 41, "merge_commit": "c" * 40,
            "verification": {"passed": True, "phases": [{"phase": "unit", "passed": True}]},
            "review_verdict": "pass", "pm_outcome": "accepted",
        },
    ))
    progress_service.store.append_checkpoint(**checkpoint(
        checkpoint_key="wo:stale:old-job", work_order_id="WO-2", kind="failed",
        state="running", job_id="job-stale", evidence={
            "branch": "ai/stale", "verification": {"passed": True},
            "review_verdict": "pass", "pm_outcome": "accepted",
        },
    ))
    accepted = progress_service.store.append_checkpoint(**checkpoint(
        checkpoint_key="wo:accepted:current", work_order_id="WO-2", kind="accepted",
        state="awaiting_merge", job_id="job-current", evidence={
            "produced_commit": "d" * 40, "branch": "ai/current", "pr_number": 42,
        },
    ))
    progress_service.store.append_checkpoint(**checkpoint(
        checkpoint_key="wo:repair:current", work_order_id="WO-2", kind="repair_reopened",
        state="running", job_id="job-current", evidence={"branch": "ai/current"},
    ))
    current_evidence = progress_service.store.append_checkpoint(**checkpoint(
        checkpoint_key="wo:evidence:current", work_order_id="WO-2", kind="failed",
        state="running", job_id="job-current", evidence={
            "branch": "ai/current",
            "verification": {"passed": False, "phases": [
                {"phase": "full_tests", "passed": False, "stderr": "PRIVATE STDERR"},
            ]},
            "review_verdict": "fail", "pm_outcome": "repair",
        },
    ))
    blocked = progress_service.store.append_checkpoint(**checkpoint(
        checkpoint_key="wo:blocked:current", work_order_id="WO-2", kind="blocked",
        state="blocked", job_id="job-current", evidence={
            "reason": "provider_failure_without_fallback",
            "prompt": "PRIVATE PROMPT", "result": {"raw": "PRIVATE RESULT"},
        },
    ))
    assert current_evidence["id"] < blocked["id"]
    before = deepcopy(storage.__dict__)

    result = progress_service.progress("plan-1")
    pack = result["blocked_evidence"]
    assert pack["completed_work_orders"] == [{
        "work_order_id": "WO-1",
        "checkpoint": {
            "id": completed["id"], "checkpoint_key": "wo:merged:one",
            "work_order_id": "WO-1", "kind": "merged", "state": "completed",
            "job_id": "job-1", "created_at": completed["created_at"].isoformat(),
            "evidence": completed["evidence"],
        },
    }]
    assert pack["current"] == {
        "work_order_id": "WO-2", "job_id": "job-current", "branch": "ai/current",
        "checkpoint_id": blocked["id"], "checkpoint_key": "wo:blocked:current",
    }
    assert pack["reason"] == "provider_failure_without_fallback"
    assert pack["latest_verification"] == {
        "passed": False, "phases": [{"phase": "full_tests", "passed": False}],
    }
    assert pack["latest_outcome"] == {"review_verdict": "fail", "pm_outcome": "repair"}
    assert pack["pending_work_orders"] == [{
        "work_order_id": "WO-3", "state": "pending", "job_id": None,
        "dependencies": ["WO-1", "WO-2"],
    }]
    assert pack["last_known_good_checkpoint"]["id"] == completed["id"]
    assert pack["last_known_good_checkpoint"]["id"] != accepted["id"]
    assert pack["next_safe_action"] == "reroute"
    assert "PRIVATE" not in str(result)
    assert progress_service.progress("plan-1")["blocked_evidence"] == pack
    for field in before.keys() - {"statements", "read_statements"}:
        assert storage.__dict__[field] == before[field]

    monkeypatch.setenv("RUNTIME_API_TOKEN", "test-progress-token")
    monkeypatch.setattr(main, "plan_orchestrator", progress_service)
    client = TestClient(main.app)
    path = "/v1/plans/plan-1/progress"
    assert client.get(path).status_code == 401
    response = client.get(path, headers={"Authorization": "Bearer test-progress-token"})
    assert response.status_code == 200
    assert response.json()["blocked_evidence"] == pack
    assert "PRIVATE" not in response.text


def test_unstructured_block_reason_is_hashed_not_exposed(progress_service):
    storage = progress_service.storage
    storage.tracked[0].update(state="blocked", job_id="job-1")
    storage.plan["status"] = "blocked"
    progress_service.store.append_checkpoint(**checkpoint(
        checkpoint_key="wo:blocked:secret", kind="blocked", state="blocked",
        job_id="job-1", evidence={
            "reason": "Bearer credential-must-not-leak", "stderr": "PRIVATE STDERR",
            "branch": "ai/job-1",
        },
    ))
    pack = progress_service.progress("plan-1")["blocked_evidence"]
    assert pack["reason"] == "unclassified_block"
    assert len(pack["reason_sha256"]) == 64
    assert pack["next_safe_action"] == "repair"
    assert "credential-must-not-leak" not in str(pack)
    assert "PRIVATE" not in str(pack)


@pytest.mark.parametrize(("reason", "job_id", "expected"), [
    ("no_effect", "job-1", "repair"),
    ("provider_failure_without_fallback", "job-1", "reroute"),
    ("human_decision_required", "job-1", "human_decision"),
    ("work_order_definition_missing", None, "replan"),
    ("planner_budget_exhausted", "job-1", "human_decision"),
    ("preflight_budget_exhausted", "job-1", "human_decision"),
    ("execution_budget_exhausted", "job-1", "human_decision"),
    ("github_ci_infrastructure_failure", "job-1", "retry_delivery"),
])
def test_next_safe_action_uses_closed_advisory_vocabulary(
    progress_service, reason, job_id, expected,
):
    storage = progress_service.storage
    storage.tracked[0].update(state="blocked", job_id=job_id)
    storage.plan["status"] = "blocked"
    progress_service.store.append_checkpoint(**checkpoint(
        checkpoint_key=f"wo:blocked:{expected}", kind="blocked", state="blocked",
        job_id=job_id, evidence={"reason": reason, "branch": "ai/job-1"},
    ))
    before = deepcopy(storage.__dict__)
    pack = progress_service.progress("plan-1")["blocked_evidence"]
    assert pack["next_safe_action"] == expected
    assert pack["next_safe_action"] in {
        "repair", "reroute", "human_decision", "replan", "retry_delivery",
    }
    for field in before.keys() - {"statements", "read_statements"}:
        assert storage.__dict__[field] == before[field]


@pytest.mark.parametrize(("reason", "expected"), [
    ("provider_failure_without_fallback", "reroute"),
    ("github_ci_infrastructure_failure", "retry_delivery"),
])
def test_current_block_reason_beats_resolved_historical_human_decision(
    progress_service, reason, expected,
):
    storage = progress_service.storage
    storage.tracked[0].update(state="blocked", job_id="job-1")
    storage.plan["status"] = "blocked"
    progress_service.store.append_checkpoint(**checkpoint(
        checkpoint_key="wo:old:human-decision", kind="waiting_human",
        state="waiting_human", job_id="job-1", evidence={
            "pm_action": "human_decision", "pm_outcome": "needs_human_decision",
        },
    ))
    progress_service.store.append_checkpoint(**checkpoint(
        checkpoint_key="wo:blocked:after-resolution", kind="blocked",
        state="blocked", job_id="job-1", evidence={
            "reason": reason, "pm_action": "human_decision",
            "pm_outcome": "needs_human_decision", "decision_key": "resolved-earlier",
        },
    ))
    before = deepcopy(storage.__dict__)
    pack = progress_service.progress("plan-1")["blocked_evidence"]
    assert pack["reason"] == reason
    assert pack["latest_outcome"] == {
        "pm_outcome": "needs_human_decision", "pm_action": "human_decision",
    }
    assert pack["next_safe_action"] == expected
    assert pack["pending_work_orders"] == [
        {"work_order_id": "WO-2", "state": "pending", "job_id": None,
         "dependencies": ["WO-1"]},
        {"work_order_id": "WO-3", "state": "pending", "job_id": None,
         "dependencies": ["WO-1", "WO-2"]},
    ]
    for field in before.keys() - {"statements", "read_statements"}:
        assert storage.__dict__[field] == before[field]


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
