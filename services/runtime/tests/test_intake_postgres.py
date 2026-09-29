"""Canonical API -> real planner/store/orchestrator, using disposable resources."""
import os
import uuid
from unittest.mock import AsyncMock

import psycopg
from psycopg import sql
from psycopg.rows import dict_row
import pytest
from fastapi.testclient import TestClient

from app import engine as engine_module, main
from app.engine import RuntimeEngine
from app.plan_orchestrator import PlanOrchestrator, PlanOrchestratorStore
from app.storage import Storage
from test_intake_api import request_payload
from test_pm_planning import baseline, configure, project_config, proposal, work_order


@pytest.fixture
def intake_db():
    dsn = os.getenv("PCP_CHECKPOINT_TEST_DSN")
    if not dsn:
        pytest.skip("PCP_CHECKPOINT_TEST_DSN is not configured (disposable PostgreSQL only)")
    schema = "intake_test_" + uuid.uuid4().hex
    with psycopg.connect(dsn, autocommit=True) as conn:
        conn.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))

    class TestStorage(Storage):
        def connect(self):
            return psycopg.connect(dsn, row_factory=dict_row, options=f"-csearch_path={schema}")

    storage = TestStorage()
    try:
        storage.init()
        PlanOrchestratorStore(storage).ensure()
        with storage.connect() as conn:
            conn.execute("""CREATE TABLE cp_control_actions (
                id TEXT PRIMARY KEY, plan_id TEXT, work_order_id TEXT, status TEXT, updated_at TIMESTAMPTZ
            )""")
        yield storage
    finally:
        with psycopg.connect(dsn, autocommit=True) as conn:
            conn.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema)))


@pytest.mark.parametrize("shape,status,jobs", [
    ("single", "failed", 0), ("decomposed", "ready", 1),
    ("out_of_scope", "out_of_scope", 0), ("ambiguous", "human_decision", 0),
    ("boundary", "human_decision", 0), ("direct", "queued", 1),
])
def test_canonical_intake_real_persistence_and_launch_gates(intake_db, monkeypatch, tmp_path, shape, status, jobs):
    output = proposal(work_order())
    if shape == "decomposed":
        output = proposal(work_order(), work_order("WO-2", dependencies=["WO-1"]))
    elif shape in {"out_of_scope", "ambiguous", "boundary"}:
        output = {
            "scope_assessment": "in_scope" if shape == "boundary" else shape,
            "summary": "Scope triage", "work_orders": [],
            "decision_boundaries": [] if shape == "out_of_scope" else [
                {"id": "D-1", "category": "security", "reason": "Human decision required"}
            ],
        }
    planner, _, _, _, _, adapter = configure(monkeypatch, tmp_path, output)
    planner.storage = intake_db
    monkeypatch.setattr(main, "resolve_project_baseline", lambda *args: baseline())
    monkeypatch.setattr(engine_module, "resolve_project_baseline", lambda *args: baseline())
    monkeypatch.setattr(engine_module, "project_config", lambda *args: project_config())
    engine = RuntimeEngine(intake_db)
    observed = []

    async def enqueue(job_id):
        # New connection and Storage instance prove durability before enqueue.
        observed.append(type(intake_db)().get(job_id))

    engine.enqueue = enqueue
    orchestrator = PlanOrchestrator(intake_db, engine)
    tick = AsyncMock(wraps=orchestrator.tick)
    monkeypatch.setattr(orchestrator, "tick", tick)
    monkeypatch.setattr(main, "storage", intake_db)
    monkeypatch.setattr(main, "engine", engine)
    monkeypatch.setattr(main, "pm_planner", planner)
    monkeypatch.setattr(main, "plan_orchestrator", orchestrator)
    monkeypatch.setenv("RUNTIME_API_TOKEN", "test-intake-token")
    client = TestClient(main.app)
    payload = request_payload()
    if shape != "direct":
        payload["repo_hints"]["dependency_depth"] = 1
    response = client.post("/v1/intake", json=payload, headers={"Authorization": "Bearer test-intake-token"})
    assert response.status_code == 200, response.text
    result = response.json()
    assert len(intake_db.list()) == len(observed) == jobs
    with intake_db.connect() as conn:
        plan_count = conn.execute("SELECT count(*) AS n FROM cp_execution_plans").fetchone()["n"]
    if shape == "direct":
        assert plan_count == 0 and adapter.calls == []
        assert observed[0]["checkpoint"]["canonical_intake"]["mode"] == "direct"
        assert result["job"]["status"] == status
        tick.assert_not_awaited()
        return
    assert plan_count == 1
    assert result["plan"]["status"] == status
    tick.assert_awaited_once()
    plan_id = result["plan"]["id"]
    stored = type(intake_db)().get_execution_plan(plan_id)
    if shape == "single":
        assert stored["plan"] is None
        assert "at least two WorkOrders" in stored["error"]
    if shape in {"single", "out_of_scope"}:
        assert orchestrator.store.orchestration(plan_id) is None
    elif shape == "decomposed":
        tracked = orchestrator.store.work_orders(plan_id)
        assert [row["state"] for row in tracked] == ["running", "pending"]
        assert observed[0]["checkpoint"]["work_order"]["id"] == "WO-1"
        assert "canonical_intake" not in observed[0]["checkpoint"]
        assert observed[0]["checkpoint"]["orchestrator_launch"]["state"] == "ready"
        assert [row["kind"] for row in orchestrator.store.checkpoints(plan_id)] == ["started"]
    else:
        assert stored["plan"]["work_orders"] == []
        assert orchestrator.store.orchestration(plan_id)["status"] == "waiting_human"
