from __future__ import annotations

from copy import deepcopy
from concurrent.futures import ThreadPoolExecutor

import pytest

from app.plan_orchestrator import PlanOrchestrator, PlanOrchestratorStore
from test_work_order_checkpoints_postgres import postgres_store  # noqa: F401


@pytest.fixture
def atomic_store(postgres_store):
    with postgres_store.storage.connect() as conn:
        conn.execute("""CREATE TABLE cp_control_actions (
            id TEXT PRIMARY KEY, plan_id TEXT, work_order_id TEXT, status TEXT, updated_at TIMESTAMPTZ
        )""")
    return postgres_store


def request(store, *, kind="started", source="pending", target="running", job_id="job-1"):
    if source != "pending":
        store.update_work_order("plan-1", "WO-1", state=source, job_id=job_id)
    expected = store.work_orders("plan-1")[0]
    return {
        "expected": expected, "checkpoint_key": "test:" + kind, "kind": kind,
        "evidence": {"produced_commit": "a" * 40}, "state": target,
        "job_id": job_id, "detail": {"reason": "new transition"},
    }


def test_postgres_atomic_commit_retry_and_store_recreation(atomic_store):
    payload = request(atomic_store)
    first = atomic_store.transition_work_order(**payload)
    current = atomic_store.work_orders("plan-1")[0]
    assert current["state"] == "running"
    assert first["job_id"] == current["job_id"] == "job-1"
    assert first["evidence"]["next"] == []
    recreated = PlanOrchestratorStore(type(atomic_store.storage)())
    assert recreated.transition_work_order(**payload) == first
    assert recreated.checkpoints("plan-1") == [first]
    assert recreated.work_orders("plan-1")[0] == current


def test_postgres_conflict_cannot_mutate_state_or_unlock(atomic_store):
    payload = request(atomic_store, kind="completed", source="running", target="completed")
    original = atomic_store.append_checkpoint(
        checkpoint_key=payload["checkpoint_key"], plan_id="plan-1", work_order_id="WO-1",
        kind="blocked", state="blocked", job_id="job-1", evidence={"reason": "conflict"},
    )
    before = atomic_store.work_orders("plan-1")[0]
    with pytest.raises(RuntimeError, match="different identity/content"):
        atomic_store.transition_work_order(**payload)
    assert atomic_store.work_orders("plan-1")[0] == before
    assert atomic_store.checkpoints("plan-1") == [original]
    assert PlanOrchestrator(atomic_store.storage, None, store=atomic_store).progress("plan-1")["next"] == []


@pytest.mark.parametrize("failure", ["before_insert", "after_insert", "oversized"])
def test_postgres_persistence_failure_rolls_back_state_checkpoint_and_attention(atomic_store, monkeypatch, failure):
    store = atomic_store
    payload = request(store, kind="merged", source="awaiting_merge", target="completed")
    for status in ("pending", "sent"):
        store.emit_notification(
            dedupe_key=status, event_type="human_decision_required", severity="warning",
            project_id="demo", ticket_id="GH-5", plan_id="plan-1", work_order_id="WO-1",
            summary="merge gate", github_url=None, payload={"attention_state": "awaiting_merge"},
        )
    with store.storage.connect() as conn:
        conn.execute("UPDATE cp_notification_outbox SET status='sent' WHERE dedupe_key='sent'")
        conn.execute("INSERT INTO cp_control_actions VALUES ('action','plan-1','WO-1','pending',now())")
    before = store.work_orders("plan-1")[0]
    real_append = store._append_checkpoint
    def injected(conn, **kwargs):
        # Same transaction has mutated the row, but another connection still
        # sees the old state and cannot consider the dependent child ready.
        assert conn.execute("SELECT state FROM cp_plan_work_orders WHERE work_order_id='WO-1'").fetchone()["state"] == "completed"
        observer = PlanOrchestrator(store.storage, None, store=store)
        assert observer.progress("plan-1")["completed"] == 0
        assert observer.progress("plan-1")["next"] == []
        if failure == "after_insert":
            real_append(conn, **kwargs)
        if failure == "oversized":
            kwargs["evidence"]["reason"] = "x" * 17000
            return real_append(conn, **kwargs)
        raise RuntimeError("injected checkpoint failure")
    monkeypatch.setattr(store, "_append_checkpoint", injected)
    with pytest.raises((RuntimeError, ValueError), match="injected|exceeds"):
        store.transition_work_order(**payload)
    assert store.work_orders("plan-1")[0] == before
    assert store.checkpoints("plan-1") == []
    with store.storage.connect() as conn:
        assert [row["status"] for row in conn.execute("SELECT status FROM cp_notification_outbox ORDER BY id").fetchall()] == ["pending", "sent"]
        assert conn.execute("SELECT status FROM cp_control_actions").fetchone()["status"] == "pending"


def test_postgres_accepted_then_merge_controls_dependency_unlock(atomic_store):
    store = atomic_store
    accepted = request(store, kind="accepted", source="running", target="awaiting_merge")
    accepted.update(pr_number=7, pr_url="https://example.test/pr/7")
    first = store.transition_work_order(**accepted)
    assert first["evidence"]["next"] == []
    expected = store.work_orders("plan-1")[0]
    merged = {"expected": expected, "checkpoint_key": "merged:7:c", "kind": "merged",
              "state": "completed", "evidence": {"pr_number": 7, "merge_commit": "c" * 40}}
    completion = store.transition_work_order(**merged)
    assert completion["evidence"]["next"] == ["WO-2"]
    observer = PlanOrchestrator(store.storage, None, store=store)
    assert observer.progress("plan-1")["next"] == ["WO-2"]
    store.update_work_order("plan-1", "WO-2", state="running", job_id="job-2")
    store.transition_work_order(
        expected=store.work_orders("plan-1")[1], checkpoint_key="block:child", kind="blocked",
        state="blocked", evidence={"reason": "later child"},
    )
    # Retrying the exact completion after the next child changes must preserve
    # its original dependency snapshot and must never rewrite earlier evidence.
    assert store.transition_work_order(**merged) == completion
    assert store.checkpoints("plan-1")[:2] == [first, completion]


@pytest.mark.parametrize("field,value", [("state", "blocked"), ("job_id", "other"), ("pr_number", 9), ("updated_at", None)])
def test_postgres_stale_transition_fails_closed(atomic_store, field, value):
    payload = request(atomic_store)
    payload["expected"][field] = value
    with pytest.raises(RuntimeError, match="Stale|Invalid"):
        atomic_store.transition_work_order(**payload)
    assert atomic_store.work_orders("plan-1")[0]["state"] == "pending"
    assert atomic_store.checkpoints("plan-1") == []


def test_postgres_supersession_blocks_new_transition(atomic_store):
    payload = request(atomic_store)
    with atomic_store.storage.connect() as conn:
        conn.execute("UPDATE cp_plan_work_orders SET lifecycle='superseded' WHERE work_order_id='WO-1'")
    with pytest.raises(RuntimeError, match="Superseded"):
        atomic_store.transition_work_order(**payload)
    assert atomic_store.checkpoints("plan-1") == []


def test_postgres_concurrent_transition_retry_is_one_commit(atomic_store):
    payload = request(atomic_store)
    def transition(_):
        recreated = PlanOrchestratorStore(type(atomic_store.storage)())
        return recreated.transition_work_order(**deepcopy(payload))
    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(transition, range(2)))
    assert outcomes[0] == outcomes[1]
    assert atomic_store.checkpoints("plan-1") == [outcomes[0]]


def test_postgres_replay_never_resurrects_recovered_work(atomic_store):
    payload = request(atomic_store, kind="blocked", source="running", target="blocked")
    checkpoint = atomic_store.transition_work_order(**payload)
    atomic_store.update_work_order("plan-1", "WO-1", state="running")
    assert atomic_store.transition_work_order(**payload) == checkpoint
    assert atomic_store.work_orders("plan-1")[0]["state"] == "running"


def test_postgres_success_retires_attention_in_same_commit(atomic_store):
    store = atomic_store
    payload = request(store, kind="merged", source="awaiting_merge", target="completed")
    store.emit_notification(
        dedupe_key="attention", event_type="human_decision_required", severity="warning",
        project_id="demo", ticket_id="GH-5", plan_id="plan-1", work_order_id="WO-1",
        summary="merge gate", github_url=None, payload={"attention_state": "awaiting_merge"},
    )
    with store.storage.connect() as conn:
        conn.execute("INSERT INTO cp_control_actions VALUES ('action','plan-1','WO-1','pending',now())")
    store.transition_work_order(**payload)
    with store.storage.connect() as conn:
        assert conn.execute("SELECT status FROM cp_notification_outbox").fetchone()["status"] == "superseded"
        assert conn.execute("SELECT status FROM cp_control_actions").fetchone()["status"] == "cancelled"
    assert len(store.checkpoints("plan-1")) == 1


def test_postgres_new_block_episode_after_recovery_has_new_durable_key(atomic_store):
    store = atomic_store
    store.update_work_order("plan-1", "WO-1", state="running", job_id="job-1")
    job = {"id": "job-1", "status": "blocked", "progress": {"model_calls": 1}}
    service = PlanOrchestrator(store.storage, None, store=store)
    first = service._checkpoint_transition(
        store.work_orders("plan-1")[0], kind="blocked", state="blocked", job=job, reason="same_reason",
    )
    store.update_work_order("plan-1", "WO-1", state="running")
    recreated = PlanOrchestratorStore(type(store.storage)())
    restarted = PlanOrchestrator(recreated.storage, None, store=recreated)
    second = restarted._checkpoint_transition(
        recreated.work_orders("plan-1")[0], kind="blocked", state="blocked", job=job, reason="same_reason",
    )
    assert first["checkpoint_key"] != second["checkpoint_key"]
    assert recreated.checkpoints("plan-1") == [first, second]


def test_postgres_reused_key_with_changed_source_episode_fails_closed(atomic_store):
    payload = request(atomic_store, kind="blocked", source="running", target="blocked")
    original = atomic_store.transition_work_order(**payload)
    atomic_store.update_work_order("plan-1", "WO-1", state="running")
    payload["expected"] = atomic_store.work_orders("plan-1")[0]
    with pytest.raises(RuntimeError, match="different identity/content"):
        atomic_store.transition_work_order(**payload)
    assert atomic_store.work_orders("plan-1")[0]["state"] == "running"
    assert atomic_store.checkpoints("plan-1") == [original]
