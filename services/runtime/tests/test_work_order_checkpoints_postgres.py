"""Optional real-DB coverage; PCP_CHECKPOINT_TEST_DSN must point to a disposable DB."""
from __future__ import annotations

import json
import os
import uuid
from concurrent.futures import ThreadPoolExecutor

import psycopg
import pytest
from psycopg import sql
from psycopg.rows import dict_row

from app.plan_orchestrator import PlanOrchestrator, PlanOrchestratorStore
from app.storage import now
from test_work_order_checkpoints import checkpoint


@pytest.fixture
def postgres_store():
    dsn = os.getenv("PCP_CHECKPOINT_TEST_DSN")
    if not dsn:
        pytest.skip("PCP_CHECKPOINT_TEST_DSN is not configured (disposable PostgreSQL only)")
    schema = "checkpoint_test_" + uuid.uuid4().hex
    with psycopg.connect(dsn, autocommit=True) as conn:
        conn.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))

    class TestStorage:
        def connect(self):
            return psycopg.connect(dsn, row_factory=dict_row, options=f"-csearch_path={schema}")

    store = PlanOrchestratorStore(TestStorage())
    try:
        store.ensure()
        with store.storage.connect() as conn:
            conn.execute("CREATE TABLE cp_execution_plans (id TEXT PRIMARY KEY, plan JSONB)")
            conn.execute(
                "INSERT INTO cp_execution_plans VALUES (%s,%s::jsonb)",
                ("plan-1", json.dumps({"work_orders": [
                    {"id": "WO-1", "dependencies": []}, {"id": "WO-2", "dependencies": ["WO-1"]},
                ]})),
            )
            conn.execute(
                """INSERT INTO cp_plan_orchestrations
                (plan_id,project_id,ticket_id,status,created_at,updated_at)
                VALUES ('plan-1','demo','GH-5','active',%s,%s)""", (now(), now()),
            )
            for work_order_id, sequence in (("WO-1", 1), ("WO-2", 2)):
                conn.execute(
                    """INSERT INTO cp_plan_work_orders
                    (plan_id,work_order_id,sequence_no,execution_mode,state,created_at,updated_at)
                    VALUES ('plan-1',%s,%s,'agent','pending',%s,%s)""",
                    (work_order_id, sequence, now(), now()),
                )
        yield store
    finally:
        # Remove only the unique test schema created by this fixture.
        with psycopg.connect(dsn, autocommit=True) as conn:
            conn.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema)))


def test_postgres_ensure_retry_order_recreation_and_immutability(postgres_store):
    store = postgres_store
    with store.storage.connect() as conn:
        installed = conn.execute("SELECT installed_at FROM cp_plan_orchestrator_meta").fetchone()
    store.ensure()
    with store.storage.connect() as conn:
        assert conn.execute("SELECT installed_at FROM cp_plan_orchestrator_meta").fetchone() == installed
        indexes = conn.execute(
            "SELECT indexdef FROM pg_indexes WHERE schemaname=current_schema() AND tablename='cp_plan_work_order_checkpoints'"
        ).fetchall()
        assert len(indexes) == 4  # PK, unique transition key, plan order, WorkOrder order.
    first = store.append_checkpoint(**checkpoint())
    assert store.append_checkpoint(**checkpoint()) == first
    second = store.append_checkpoint(**checkpoint(checkpoint_key="second", work_order_id="WO-2"))
    with pytest.raises(RuntimeError, match="different identity/content"):
        store.append_checkpoint(**checkpoint(state="blocked"))
    with pytest.raises(RuntimeError, match="Unknown checkpoint"):
        store.append_checkpoint(**checkpoint(work_order_id="missing"))
    store.update_work_order("plan-1", "WO-1", state="completed", detail={"later": "mutable evidence"})
    # New storage, new connections and new store: nothing comes from process-local caches.
    recreated = PlanOrchestratorStore(type(store.storage)())
    recreated.ensure()
    assert recreated.checkpoints("plan-1") == [first, second]
    assert recreated.checkpoints("plan-1", work_order_id="WO-1") == [first]
    service = PlanOrchestrator(recreated.storage, None, store=recreated)
    result = service.progress("plan-1")
    assert result["completed"] == 1
    assert result["total"] == 2
    assert result["next"] == ["WO-2"]
    assert result["last_checkpoint"] == second
    assert service.progress("missing") is None
    with store.storage.connect() as conn:
        conn.execute("UPDATE cp_plan_work_orders SET lifecycle='superseded' WHERE work_order_id='WO-1'")
    result = service.progress("plan-1")
    assert (result["completed"], result["total"], result["next"]) == (0, 1, [])
    assert recreated.checkpoints("plan-1") == [first, second]


def test_postgres_composite_foreign_key_rejects_unbound_evidence(postgres_store):
    with pytest.raises(psycopg.errors.ForeignKeyViolation):
        with postgres_store.storage.connect() as conn:
            conn.execute(
                """INSERT INTO cp_plan_work_order_checkpoints
                (checkpoint_key,plan_id,work_order_id,kind,state,created_at)
                VALUES ('invalid','other-plan','WO-1','accepted','completed',%s)""", (now(),),
            )
    assert postgres_store.checkpoints("other-plan") == []


def test_postgres_canonical_jsonb_retry_preserves_types_and_numeric_values(postgres_store):
    payload = checkpoint(evidence={"large": 1e20, "small": 1e-20, "passed": True})
    original = postgres_store.append_checkpoint(**payload)
    assert postgres_store.append_checkpoint(**payload) == original
    payload["evidence"]["passed"] = 1
    with pytest.raises(RuntimeError, match="different identity/content"):
        postgres_store.append_checkpoint(**payload)
    assert postgres_store.checkpoints("plan-1") == [original]


def test_postgres_concurrent_exact_and_conflicting_retries(postgres_store):
    def append(values):
        try:
            return PlanOrchestratorStore(type(postgres_store.storage)()).append_checkpoint(**values)
        except RuntimeError as exc:
            return str(exc)

    with ThreadPoolExecutor(max_workers=2) as pool:
        identical = list(pool.map(append, [checkpoint(), checkpoint()]))
    assert isinstance(identical[0], dict)
    assert identical[0] == identical[1]
    assert postgres_store.checkpoints("plan-1") == [identical[0]]
    with ThreadPoolExecutor(max_workers=2) as pool:
        conflicting = list(pool.map(append, [
            checkpoint(checkpoint_key="race", state="completed"),
            checkpoint(checkpoint_key="race", state="blocked"),
        ]))
    assert sum(isinstance(result, dict) for result in conflicting) == 1
    assert "Checkpoint key already has different identity/content" in conflicting
    assert len(postgres_store.checkpoints("plan-1")) == 2
