from __future__ import annotations

import json
from copy import deepcopy
from datetime import datetime, timezone

import pytest

from app.plan_orchestrator import CHECKPOINT_EVIDENCE_MAX_BYTES, PlanOrchestratorStore
from app.work_order_checkpoints import blocked_plan_evidence
from test_plan_orchestrator_store import Connection, Result, Storage


class CheckpointConnection(Connection):
    def execute(self, sql, params=None):
        normalized = " ".join(sql.split())
        self.storage.statements.append(normalized)
        params = list(params or [])
        if normalized.startswith("SELECT 1 FROM cp_plan_work_orders"):
            return Result(row={"exists": 1} if tuple(params) in self.storage.identities else None)
        if normalized.startswith("INSERT INTO cp_plan_work_order_checkpoints"):
            key, plan, work_order, kind, state, job, evidence, created = params
            if key in self.storage.checkpoint_rows:
                return Result()
            row = dict(
                id=len(self.storage.checkpoint_rows) + 1, checkpoint_key=key,
                plan_id=plan, work_order_id=work_order, kind=kind, state=state,
                job_id=job, evidence=json.loads(evidence), created_at=created,
            )
            self.storage.checkpoint_rows[key] = row
            return Result(row=row)
        if normalized.startswith("SELECT * FROM cp_plan_work_order_checkpoints"):
            if "WHERE checkpoint_key=" in normalized:
                row = self.storage.checkpoint_rows.get(params[0])
                fields = ("checkpoint_key", "plan_id", "work_order_id", "kind", "state", "job_id")
                matches = row and all(row[field] == value for field, value in zip(fields, params[:6], strict=True))
                if matches:
                    matches = json.dumps(row["evidence"], sort_keys=True) == json.dumps(json.loads(params[6]), sort_keys=True)
                return Result(row=row if matches else None)
            rows = [row for row in self.storage.checkpoint_rows.values() if row["plan_id"] == params[0]]
            if len(params) > 1:
                rows = [row for row in rows if row["work_order_id"] == params[1]]
            rows.sort(key=lambda row: row["id"])
            if "ORDER BY id DESC LIMIT 1" in normalized:
                return Result(row=rows[-1] if rows else None)
            assert normalized.endswith("ORDER BY id")
            return Result(rows=rows)
        return super().execute(sql, params)


class CheckpointStorage(Storage):
    def __init__(self):
        super().__init__()
        self.work_order.update(plan_id="plan-1", work_order_id="WO-1", state="running")
        self.identities = {("plan-1", "WO-1"), ("plan-1", "WO-2"), ("plan-2", "WO-1")}
        self.checkpoint_rows = {}
        self.statements = []

    def connect(self):
        return CheckpointConnection(self)


def checkpoint(**overrides):
    return {
        "checkpoint_key": "plan-1:WO-1:accepted:commit-1",
        "plan_id": "plan-1", "work_order_id": "WO-1", "kind": "accepted",
        "state": "completed", "job_id": "job-1",
        "evidence": {"produced_commit": "a" * 40, "verification": {"passed": True, "count": 3}},
        **overrides,
    }


@pytest.fixture
def checkpoint_store():
    return PlanOrchestratorStore(CheckpointStorage())


def test_checkpoint_order_is_row_id_not_key_or_wall_clock(checkpoint_store, monkeypatch):
    stamps = iter([
        datetime(2026, 9, 29, 12, tzinfo=timezone.utc),
        datetime(2026, 9, 29, 11, tzinfo=timezone.utc),
        datetime(2026, 9, 29, 11, tzinfo=timezone.utc),
    ])
    monkeypatch.setattr("app.plan_orchestrator.now", lambda: next(stamps))
    first = checkpoint_store.append_checkpoint(**checkpoint(checkpoint_key="z"))
    second = checkpoint_store.append_checkpoint(**checkpoint(checkpoint_key="a", work_order_id="WO-2"))
    checkpoint_store.append_checkpoint(**checkpoint(checkpoint_key="other-plan", plan_id="plan-2"))
    assert checkpoint_store.checkpoints("plan-1") == [first, second]
    assert checkpoint_store.checkpoints("plan-1", work_order_id="WO-1") == [first]
    assert checkpoint_store.checkpoints("unknown") == []


def test_exact_retry_ignores_object_key_order_and_returns_original_timestamp(checkpoint_store):
    original = checkpoint_store.append_checkpoint(**checkpoint())
    retry = checkpoint(evidence={"verification": {"count": 3, "passed": True}, "produced_commit": "a" * 40})
    assert checkpoint_store.append_checkpoint(**retry) == original
    assert checkpoint_store.checkpoints("plan-1") == [original]


@pytest.mark.parametrize("changes", [
    {"plan_id": "plan-2"}, {"work_order_id": "WO-2"}, {"kind": "blocked"},
    {"state": "blocked"}, {"job_id": "job-2"}, {"job_id": None},
    {"evidence": {"produced_commit": "b" * 40}},
    {"evidence": {"produced_commit": "a" * 40, "verification": {"passed": 1, "count": 3}}},
])
def test_conflicting_key_fails_closed_without_rewriting_evidence(checkpoint_store, changes):
    original = checkpoint_store.append_checkpoint(**checkpoint())
    with pytest.raises(RuntimeError, match="different identity/content"):
        checkpoint_store.append_checkpoint(**checkpoint(**changes))
    assert checkpoint_store.checkpoints("plan-1") == [original]


@pytest.mark.parametrize("changes", [
    {"plan_id": "unknown"}, {"work_order_id": "unknown"},
    {"plan_id": "plan-2", "work_order_id": "WO-2"},
])
def test_unknown_or_mismatched_work_order_is_rejected(checkpoint_store, changes):
    with pytest.raises(RuntimeError, match="Unknown checkpoint plan/WorkOrder"):
        checkpoint_store.append_checkpoint(**checkpoint(**changes))
    assert checkpoint_store.storage.checkpoint_rows == {}


@pytest.mark.parametrize("field,limit", [
    ("checkpoint_key", 500), ("plan_id", 200), ("work_order_id", 200),
    ("kind", 200), ("state", 200), ("job_id", 200),
])
def test_checkpoint_strings_are_bounded_exact_and_nonempty(checkpoint_store, field, limit):
    for value in ("", " ", " leading", "trailing ", "x" * (limit + 1), "a\x00b", 1):
        with pytest.raises(ValueError, match=field):
            checkpoint_store.append_checkpoint(**checkpoint(**{field: value}))
    assert checkpoint_store.storage.checkpoint_rows == {}


def test_evidence_limit_counts_serialized_utf8_bytes(checkpoint_store):
    # {"reason":""} requires thirteen bytes in compact JSON.
    accepted = {"reason": "x" * (CHECKPOINT_EVIDENCE_MAX_BYTES - 13)}
    checkpoint_store.append_checkpoint(**checkpoint(evidence=accepted))
    for oversized in ({"reason": accepted["reason"] + "x"}, {"reason": "é" * (CHECKPOINT_EVIDENCE_MAX_BYTES // 2)}):
        with pytest.raises(ValueError, match="exceeds"):
            checkpoint_store.append_checkpoint(**checkpoint(checkpoint_key="too-big", evidence=oversized))
    assert len(checkpoint_store.checkpoints("plan-1")) == 1


@pytest.mark.parametrize("evidence", [[], "summary", {"count": float("nan")}, {"count": float("inf")}, {"bad": object()}])
def test_evidence_must_be_a_json_object(checkpoint_store, evidence):
    with pytest.raises(ValueError, match="JSON"):
        checkpoint_store.append_checkpoint(**checkpoint(evidence=evidence))


def test_checkpoint_survives_mutable_update_and_store_recreation(checkpoint_store):
    payload = checkpoint()
    original = checkpoint_store.append_checkpoint(**payload)
    expected = deepcopy(original)
    payload["evidence"]["verification"]["passed"] = False
    original["evidence"]["verification"]["passed"] = False
    checkpoint_store.update_work_order("plan-1", "WO-1", state="blocked", detail={"reason": "later failure"})
    recreated = PlanOrchestratorStore(checkpoint_store.storage)
    recreated.ensure()
    assert recreated.checkpoints("plan-1") == [expected]
    assert recreated.storage.work_order["state"] == "blocked"


def test_optional_job_and_evidence_defaults_are_durable(checkpoint_store):
    values = checkpoint()
    del values["job_id"], values["evidence"]
    first = checkpoint_store.append_checkpoint(**values)
    assert first["job_id"] is None
    assert first["evidence"] == {}
    assert checkpoint_store.append_checkpoint(**values) == first


def test_repeated_deterministic_verification_failure_is_bounded_repair() -> None:
    snapshot = {
        "work_orders": [
            {
                "work_order_id": "WO-verify",
                "state": "blocked",
                "job_id": "job-verify",
            }
        ],
        "blocked_checkpoint": {
            "evidence": {
                "reason": "repeated_deterministic_verification_failure",
            }
        },
        "current_checkpoint_history": [],
    }

    result = blocked_plan_evidence(snapshot)

    assert result is not None
    assert result["reason"] == "repeated_deterministic_verification_failure"
    assert result["next_safe_action"] == "repair"


def test_runtime_failed_is_public_bounded_repair_reason() -> None:
    snapshot = {
        "work_orders": [
            {
                "work_order_id": "WO-runtime-failed",
                "state": "blocked",
                "job_id": "job-runtime-failed",
            }
        ],
        "blocked_checkpoint": {
            "evidence": {
                "reason": "runtime_failed",
            }
        },
        "current_checkpoint_history": [],
    }

    result = blocked_plan_evidence(snapshot)

    assert result is not None
    assert result["reason"] == "runtime_failed"
    assert result["next_safe_action"] == "repair"
