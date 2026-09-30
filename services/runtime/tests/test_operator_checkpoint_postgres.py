"""Real operator API and PostgreSQL checkpoint transactions on a disposable schema."""
from __future__ import annotations

import asyncio
import hashlib
import os
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import psycopg
import pytest
from fastapi.testclient import TestClient
from psycopg import sql
from psycopg.rows import dict_row

from app import main
from app.orchestrator_notifications import PlanOrchestrator
from app.plan_orchestrator import PlanOrchestratorStore
from app.plan_progress_store import PlanProgressStore
from app.telemetry_storage import TelemetryStorage


PLAN_ID = "operator-checkpoint-test"
WORK_ORDERS = ("WO-1", "WO-2", "WO-3")
PRIVATE_NOTE = "controlled free-form operator finding"


@pytest.fixture
def operator_db():
    dsn = os.getenv("PCP_CHECKPOINT_TEST_DSN")
    if not dsn:
        pytest.skip("PCP_CHECKPOINT_TEST_DSN is not configured (disposable PostgreSQL only)")
    schema = "operator_checkpoint_test_" + uuid.uuid4().hex
    with psycopg.connect(dsn, autocommit=True) as conn:
        conn.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))

    class TestStorage(TelemetryStorage):
        def connect(self):
            return psycopg.connect(dsn, row_factory=dict_row, options=f"-csearch_path={schema}")

    storage = TestStorage()
    try:
        storage.init()
        store = PlanOrchestratorStore(storage)
        store.ensure()
        handoffs = PlanProgressStore(storage)
        handoffs.ensure()
        storage.create_execution_plan({
            "id": PLAN_ID, "project_id": "demo", "status": "ready",
            "baseline_revision": "test", "baseline_source_commit": "a" * 40,
            "ticket": {"id": "GH-377", "title": "Operator checkpoint test"},
            "plan": {"work_orders": [
                {"id": work_order_id, "requested_role": "operator",
                 "dependencies": [WORK_ORDERS[index - 1]] if index else []}
                for index, work_order_id in enumerate(WORK_ORDERS)
            ]},
        })
        assert store.register_new_plans() == [PLAN_ID]

        def unexpected_job(*args, **kwargs):
            raise AssertionError("operator plan must not create a source job")

        engine = SimpleNamespace(create_job=unexpected_job, enqueue=AsyncMock(side_effect=unexpected_job))
        service = PlanOrchestrator(storage, engine, store=store, progress_handoffs=handoffs)
        service.controls.ensure()
        yield storage, service, handoffs, engine
    finally:
        with psycopg.connect(dsn, autocommit=True) as conn:
            conn.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema)))


def snapshot(storage):
    # Re-opened connection observes only committed state and checkpoint rows.
    with type(storage)().connect() as conn:
        work_orders = list(conn.execute(
            "SELECT work_order_id, state, job_id, detail FROM cp_plan_work_orders WHERE plan_id=%s ORDER BY sequence_no",
            (PLAN_ID,),
        ).fetchall())
        checkpoints = list(conn.execute(
            "SELECT * FROM cp_plan_work_order_checkpoints WHERE plan_id=%s ORDER BY id", (PLAN_ID,),
        ).fetchall())
        plan = conn.execute("SELECT status FROM cp_plan_orchestrations WHERE plan_id=%s", (PLAN_ID,)).fetchone()
    return work_orders, checkpoints, plan


def operator_client(monkeypatch, service):
    assert type(main.plan_orchestrator) is PlanOrchestrator
    assert isinstance(main.plan_orchestrator.store, PlanOrchestratorStore)
    assert isinstance(main.plan_orchestrator.storage, TelemetryStorage)
    monkeypatch.setattr(main, "plan_orchestrator", service)
    monkeypatch.setenv("RUNTIME_API_TOKEN", "operator-checkpoint-test-token")
    return TestClient(main.app)


def resolve(client, work_order_id, action, note):
    return client.post(
        f"/v1/plans/{PLAN_ID}/work-orders/{work_order_id}/operator",
        headers={"Authorization": "Bearer operator-checkpoint-test-token"},
        json={"action": action, "note": note},
    )


def test_operator_api_complete_then_block_commits_exact_checkpoints_and_handoff(operator_db, monkeypatch):
    storage, service, handoffs, engine = operator_db
    client = operator_client(monkeypatch, service)
    asyncio.run(service.tick())
    work_orders, checkpoints, plan = snapshot(storage)
    assert [row["state"] for row in work_orders] == ["waiting_human", "pending", "pending"]
    assert [(row["work_order_id"], row["kind"]) for row in checkpoints] == [("WO-1", "waiting_human")]
    assert plan["status"] == "waiting_human"

    first = resolve(client, "WO-1", "complete", "operator completed first step")
    assert first.status_code == 200, first.text
    work_orders, checkpoints, plan = snapshot(storage)
    completed = [row for row in checkpoints if row["work_order_id"] == "WO-1" and row["kind"] == "completed"]
    assert len(completed) == 1 and completed[0]["job_id"] is None
    assert [row["state"] for row in work_orders] == ["completed", "waiting_human", "pending"]
    assert plan["status"] == "waiting_human"
    before = dict(completed[0])
    initial_handoff = handoffs.claim()
    assert initial_handoff is not None and handoffs.ack(initial_handoff, 377)

    blocked = resolve(client, "WO-2", "block", PRIVATE_NOTE)
    assert blocked.status_code == 200, blocked.text
    work_orders, checkpoints, plan = snapshot(storage)
    blocks = [row for row in checkpoints if row["work_order_id"] == "WO-2" and row["kind"] == "blocked"]
    assert [row["state"] for row in work_orders] == ["completed", "blocked", "pending"]
    assert plan["status"] == "blocked"
    assert all(row["job_id"] is None for row in work_orders)
    assert len(blocks) == 1 and blocks[0]["job_id"] is None
    assert blocks[0]["evidence"]["reason"] == PRIVATE_NOTE
    assert work_orders[1]["detail"] == {"reason": "operator_blocked", "operator_note": PRIVATE_NOTE}
    assert next(row for row in checkpoints if row["id"] == before["id"]) == before
    assert engine.enqueue.await_count == 0

    restarted = PlanOrchestrator(type(storage)(), engine, store=PlanOrchestratorStore(type(storage)()))
    progress = restarted.progress(PLAN_ID)
    assert progress == service.progress(PLAN_ID)
    evidence = progress["blocked_evidence"]
    assert evidence["current"]["checkpoint_id"] == blocks[0]["id"]
    assert evidence["current"]["checkpoint_key"] == blocks[0]["checkpoint_key"]
    assert evidence["reason"] == "unclassified_block"
    assert evidence["reason_sha256"] == hashlib.sha256(PRIVATE_NOTE.encode()).hexdigest()
    assert evidence["last_known_good_checkpoint"]["id"] == completed[0]["id"]
    assert [row["work_order_id"] for row in evidence["pending_work_orders"]] == ["WO-3"]
    assert evidence["next_safe_action"] == "replan"
    with type(storage)().connect() as conn:
        handoff = conn.execute("SELECT * FROM cp_plan_progress_handoffs").fetchone()
    assert handoff["comment_id"] == 377
    assert handoff["handoff_key"] == initial_handoff["handoff_key"]
    assert handoff["desired_generation"] > initial_handoff["desired_generation"]
    assert PRIVATE_NOTE not in handoff["desired_body"]
    assert "unclassified_block" in handoff["desired_body"]


@pytest.mark.parametrize("action,work_order_id,expected_state", [
    ("complete", "WO-1", "completed"),
    ("block", "WO-2", "blocked"),
])
def test_operator_checkpoint_failure_rolls_back_state(operator_db, monkeypatch, action, work_order_id, expected_state):
    storage, service, _, engine = operator_db
    asyncio.run(service.tick())
    if action == "block":
        service.store.transition_work_order(
            expected=service.store.work_orders(PLAN_ID)[0],
            checkpoint_key="test:completed:first", kind="completed", state="completed", evidence={},
        )
        asyncio.run(service.tick())
    before_rows, before_checkpoints, before_plan = snapshot(storage)
    assert before_rows[0 if action == "complete" else 1]["state"] == "waiting_human"
    assert before_plan["status"] == "waiting_human"
    real_append = service.store._append_checkpoint

    def fail_after_update(conn, **kwargs):
        current = conn.execute(
            "SELECT state FROM cp_plan_work_orders WHERE plan_id=%s AND work_order_id=%s",
            (PLAN_ID, work_order_id),
        ).fetchone()
        assert current["state"] == expected_state
        raise RuntimeError("injected checkpoint append failure")

    monkeypatch.setattr(service.store, "_append_checkpoint", fail_after_update)
    with pytest.raises(RuntimeError, match="injected checkpoint append failure"):
        asyncio.run(service.resolve_operator(plan_id=PLAN_ID, work_order_id=work_order_id, action=action, note=PRIVATE_NOTE))
    work_orders, checkpoints, plan = snapshot(storage)
    assert work_orders == before_rows
    assert checkpoints == before_checkpoints
    assert plan == before_plan
    assert engine.enqueue.await_count == 0

    monkeypatch.setattr(service.store, "_append_checkpoint", real_append)
    asyncio.run(service.resolve_operator(plan_id=PLAN_ID, work_order_id=work_order_id, action=action, note=PRIVATE_NOTE))
    work_orders, checkpoints, plan = snapshot(storage)
    assert work_orders[0 if action == "complete" else 1]["state"] == expected_state
    assert plan["status"] == ("blocked" if action == "block" else "waiting_human")
    assert len([row for row in checkpoints if row["work_order_id"] == work_order_id and row["kind"] == expected_state]) == 1


def test_long_operator_note_has_bounded_durable_evidence_and_private_handoff(operator_db, monkeypatch):
    storage, service, _, _ = operator_db
    client = operator_client(monkeypatch, service)
    asyncio.run(service.tick())
    assert resolve(client, "WO-1", "complete", "completed").status_code == 200
    note = "private-" + "x" * 1500
    assert resolve(client, "WO-2", "block", note).status_code == 200
    work_orders, checkpoints, _ = snapshot(storage)
    blocked = next(row for row in checkpoints if row["work_order_id"] == "WO-2" and row["kind"] == "blocked")
    assert work_orders[1]["detail"] == {"reason": "operator_blocked", "operator_note": note}
    assert blocked["evidence"]["reason"] == note[:1000]
    assert blocked["evidence"]["reason_sha256"] == hashlib.sha256(note.encode()).hexdigest()
    evidence = service.progress(PLAN_ID)["blocked_evidence"]
    assert evidence["reason"] == "unclassified_block"
    assert note not in str(evidence)
    with type(storage)().connect() as conn:
        body = conn.execute("SELECT desired_body FROM cp_plan_progress_handoffs").fetchone()["desired_body"]
    assert note not in body and note[:1000] not in body
