"""Supervised plan continuation against a disposable PostgreSQL schema."""
from __future__ import annotations

import asyncio
import json
import os
import uuid
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from unittest.mock import AsyncMock

import psycopg
import pytest
from fastapi.testclient import TestClient
from psycopg import sql
from psycopg.rows import dict_row

from app import main
from app.engine import RuntimeEngine
from app.plan_orchestrator import (
    PlanContinuationConflict,
    PlanOrchestrator,
    PlanOrchestratorStore,
    build_continuation_key,
    launch_identity,
)
from app.storage import Storage
from test_plan_orchestrator import work_order


class FakeDdev:
    def __init__(self) -> None:
        self.prs: dict[int, dict] = {}

    async def github_pull_request(self, *, project_id, pr_number):
        return deepcopy(self.prs[pr_number])

    async def quiesce_workspace(self, **payload):
        return {"quiesced": True, "data_removed": bool(payload.get("remove_data"))}


class FakeEngine:
    def __init__(self, storage: Storage) -> None:
        self.storage = storage
        self.ddev = FakeDdev()
        self.created: list[str] = []
        self.enqueued: list[str] = []

    def create_job(self, payload, *, _orchestration=None):
        assert _orchestration is not None
        plan_id, work_order_id = _orchestration
        identity = launch_identity(plan_id, work_order_id)
        assert payload["_job_id"] == identity["job_id"]
        existing = self.storage.get(identity["job_id"])
        if existing is not None:
            return identity["job_id"]
        self.storage.create({
            "id": identity["job_id"],
            "project_id": payload["project_id"],
            "status": "queued",
            "source_commit": None,
            "task": {"title": work_order_id, "description": payload["work_order"]["objective"]},
            "progress": {},
            "checkpoint": {
                "work_order": payload["work_order"],
                "orchestrator_launch": {**identity, "state": "held"},
            },
            "result": None,
        })
        self.created.append(identity["job_id"])
        return identity["job_id"]

    async def enqueue(self, job_id):
        job = self.storage.get(job_id)
        assert job is not None
        checkpoint = deepcopy(job["checkpoint"])
        checkpoint["orchestrator_launch"]["state"] = "launched"
        self.storage.update(job_id, status="routing", checkpoint=checkpoint)
        self.enqueued.append(job_id)


@pytest.fixture
def supervision_db():
    dsn = os.getenv("PCP_CHECKPOINT_TEST_DSN")
    if not dsn:
        pytest.skip("PCP_CHECKPOINT_TEST_DSN is not configured (disposable PostgreSQL only)")
    schema = "plan_supervision_test_" + uuid.uuid4().hex
    with psycopg.connect(dsn, autocommit=True) as conn:
        conn.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))

    class TestStorage(Storage):
        def connect(self):
            return psycopg.connect(
                dsn,
                row_factory=dict_row,
                options=f"-csearch_path={schema}",
            )

    storage = TestStorage()
    store = PlanOrchestratorStore(storage)
    try:
        storage.init()
        store.ensure()
        with storage.connect() as conn:
            conn.execute("""CREATE TABLE cp_control_actions (
                id TEXT PRIMARY KEY, plan_id TEXT, work_order_id TEXT,
                status TEXT, updated_at TIMESTAMPTZ
            )""")
        yield storage, store
    finally:
        with psycopg.connect(dsn, autocommit=True) as conn:
            conn.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema)))


def create_plan(
    storage: Storage,
    *,
    mode: str = "supervised",
    roles: tuple[str, ...] = ("developer", "developer"),
) -> list[dict]:
    definitions = []
    for index, role in enumerate(roles, start=1):
        definitions.append(work_order(
            f"WO-{index}",
            dependencies=[] if index == 1 else [f"WO-{index - 1}"],
            requested_role=role,
        ))
    storage.create_execution_plan({
        "id": "plan-1",
        "project_id": "demo",
        "status": "ready",
        "baseline_revision": "v1",
        "baseline_source_commit": "a" * 40,
        "ticket": {"id": "GH-5", "title": "Supervised chain", "description": "bounded"},
        "staffing": None,
        "plan": {
            "scope_assessment": "in_scope",
            "summary": "bounded",
            "work_orders": definitions,
            "decision_boundaries": [],
            "ready_work_order_ids": ["WO-1"],
            **({"execution_mode": mode} if mode else {}),
        },
        "usage": None,
        "error": None,
    })
    return definitions


def service_for(storage: Storage, store: PlanOrchestratorStore) -> tuple[PlanOrchestrator, FakeEngine]:
    engine = FakeEngine(storage)
    return PlanOrchestrator(storage, engine, store=store), engine


def complete_job(storage: Storage, job_id: str, *, pr_number: int | None = None) -> None:
    delivery = {"state": "accepted"}
    if pr_number is not None:
        delivery["pull_request"] = {
            "number": pr_number,
            "url": f"https://example.test/pull/{pr_number}",
            "head": "b" * 40,
        }
    storage.update(
        job_id,
        status="completed",
        result={"commit": "b" * 40, "delivery": delivery},
        progress={"required_checks_passed": True, "tests_passed": True},
    )


def continuation_payload(service: PlanOrchestrator) -> dict:
    supervision = service.progress("plan-1")["supervision"]
    return {
        "plan_id": "plan-1",
        "generation": supervision["generation"],
        "continuation_key": supervision["continuation_key"],
        "checkpoint_id": supervision["checkpoint"]["id"],
        "checkpoint_key": supervision["checkpoint"]["checkpoint_key"],
        "ready_work_order_ids": supervision["ready_work_order_ids"],
    }


def assert_released_retry_is_read_only(
    service: PlanOrchestrator,
    store: PlanOrchestratorStore,
    engine: FakeEngine,
    request: dict,
) -> None:
    before_orchestration = deepcopy(store.orchestration("plan-1"))
    before_work_orders = deepcopy(store.work_orders("plan-1"))
    before_checkpoints = deepcopy(store.checkpoints("plan-1"))
    before_created = list(engine.created)
    before_enqueued = list(engine.enqueued)

    result = asyncio.run(service.continue_plan(**deepcopy(request)))

    assert result["idempotent"] is True
    assert result["launched"] is None
    assert store.orchestration("plan-1") == before_orchestration
    assert store.work_orders("plan-1") == before_work_orders
    assert store.checkpoints("plan-1") == before_checkpoints
    assert engine.created == before_created
    assert engine.enqueued == before_enqueued


def test_operator_chain_holds_between_work_orders_and_retry_is_idempotent(supervision_db):
    storage, store = supervision_db
    create_plan(storage, roles=("operator", "operator"))
    service, engine = service_for(storage, store)

    asyncio.run(service.tick())
    assert [row["state"] for row in store.work_orders("plan-1")] == ["waiting_human", "pending"]
    asyncio.run(service.resolve_operator(
        plan_id="plan-1", work_order_id="WO-1", action="complete", note="done",
    ))
    assert [row["state"] for row in store.work_orders("plan-1")] == ["completed", "pending"]
    assert store.orchestration("plan-1")["status"] == "supervised_hold"
    payload = continuation_payload(service)

    released = asyncio.run(service.continue_plan(**payload))
    assert released["idempotent"] is False
    assert [row["state"] for row in store.work_orders("plan-1")] == ["completed", "waiting_human"]
    assert store.orchestration("plan-1")["status"] == "waiting_human"
    assert_released_retry_is_read_only(service, store, engine, payload)
    assert len([row for row in store.checkpoints("plan-1") if row["work_order_id"] == "WO-2"]) == 1


def test_agent_completion_holds_without_creating_next_job_or_run_bypass(
    supervision_db, monkeypatch,
):
    storage, store = supervision_db
    create_plan(storage)
    service, engine = service_for(storage, store)
    asyncio.run(service.tick())
    first_job = engine.created[0]
    next_job = launch_identity("plan-1", "WO-2")["job_id"]
    complete_job(storage, first_job)

    asyncio.run(service.tick())

    assert store.orchestration("plan-1")["status"] == "supervised_hold"
    assert store.work_orders("plan-1")[1]["state"] == "pending"
    assert storage.get(next_job) is None
    monkeypatch.setattr(main, "storage", storage)
    monkeypatch.setattr(main, "engine", RuntimeEngine(storage))
    monkeypatch.setattr(main, "plan_orchestrator", service)
    monkeypatch.setenv("RUNTIME_API_TOKEN", "supervision-test-token")
    client = TestClient(main.app)
    response = client.post(
        f"/v1/jobs/{next_job}/run",
        headers={"Authorization": "Bearer supervision-test-token"},
    )
    assert response.status_code == 404
    assert storage.get(next_job) is None

    payload = continuation_payload(service)
    result = asyncio.run(service.continue_plan(**payload))
    assert result["launched"]["job_id"] == next_job
    assert storage.get(next_job) is not None
    assert len(engine.created) == 2
    assert store.orchestration("plan-1")["status"] == "executing"
    assert_released_retry_is_read_only(service, store, engine, payload)
    assert len(engine.created) == 2


def test_released_retry_is_idempotent_after_child_reaches_waiting_merge(supervision_db):
    storage, store = supervision_db
    create_plan(storage)
    service, engine = service_for(storage, store)
    asyncio.run(service.tick())
    complete_job(storage, engine.created[0])
    asyncio.run(service.tick())
    request = continuation_payload(service)
    asyncio.run(service.continue_plan(**request))

    child_job = engine.created[1]
    complete_job(storage, child_job, pr_number=52)
    engine.ddev.prs[52] = {
        "number": 52,
        "url": "https://example.test/pull/52",
        "head": "d" * 40,
        "state": "open",
        "merged": False,
    }
    asyncio.run(service.tick())

    assert store.work_orders("plan-1")[1]["state"] == "awaiting_merge"
    assert store.orchestration("plan-1")["status"] == "waiting_merge"
    assert_released_retry_is_read_only(service, store, engine, request)


def test_released_retry_is_idempotent_after_child_becomes_blocked(supervision_db):
    storage, store = supervision_db
    create_plan(storage)
    service, engine = service_for(storage, store)
    asyncio.run(service.tick())
    complete_job(storage, engine.created[0])
    asyncio.run(service.tick())
    request = continuation_payload(service)
    asyncio.run(service.continue_plan(**request))

    child_job = engine.created[1]
    storage.update(
        child_job,
        status="blocked",
        result={"reason": "verification_failed"},
    )
    asyncio.run(service.tick())

    assert store.work_orders("plan-1")[1]["state"] == "blocked"
    assert store.orchestration("plan-1")["status"] == "blocked"
    assert_released_retry_is_read_only(service, store, engine, request)


def test_released_retry_is_idempotent_after_final_child_completes(supervision_db):
    storage, store = supervision_db
    create_plan(storage)
    service, engine = service_for(storage, store)
    asyncio.run(service.tick())
    complete_job(storage, engine.created[0])
    asyncio.run(service.tick())
    request = continuation_payload(service)
    asyncio.run(service.continue_plan(**request))

    complete_job(storage, engine.created[1])
    asyncio.run(service.tick())

    assert [row["state"] for row in store.work_orders("plan-1")] == ["completed", "completed"]
    assert store.orchestration("plan-1")["status"] == "completed"
    assert store.orchestration("plan-1")["supervision_generation"] == request["generation"]
    assert_released_retry_is_read_only(service, store, engine, request)


def test_pr_acceptance_does_not_hold_but_durable_merge_does(supervision_db):
    storage, store = supervision_db
    create_plan(storage)
    service, engine = service_for(storage, store)
    asyncio.run(service.tick())
    complete_job(storage, engine.created[0], pr_number=41)
    engine.ddev.prs[41] = {
        "number": 41,
        "url": "https://example.test/pull/41",
        "head": "b" * 40,
        "state": "open",
        "merged": False,
    }

    asyncio.run(service.tick())
    assert store.work_orders("plan-1")[0]["state"] == "awaiting_merge"
    assert store.orchestration("plan-1")["status"] == "waiting_merge"
    assert service.progress("plan-1")["supervision"] == {"mode": "supervised", "state": None}

    engine.ddev.prs[41].update(
        state="closed",
        merged=True,
        merged_at="2026-09-30T01:00:00Z",
        merge_commit_sha="c" * 40,
    )
    asyncio.run(service.tick())
    progress = service.progress("plan-1")
    assert progress["state"] == "supervised_hold"
    assert progress["supervision"]["checkpoint"]["work_order_id"] == "WO-1"
    assert progress["last_checkpoint"]["kind"] == "merged"


def test_restart_and_busy_direct_lease_preserve_released_generation(supervision_db, monkeypatch):
    storage, store = supervision_db
    create_plan(storage, roles=("developer", "developer", "developer"))
    service, engine = service_for(storage, store)
    asyncio.run(service.tick())
    complete_job(storage, engine.created[0])
    asyncio.run(service.tick())
    held = continuation_payload(service)

    recreated_store = PlanOrchestratorStore(type(storage)())
    restarted = PlanOrchestrator(recreated_store.storage, engine, store=recreated_store)
    assert continuation_payload(restarted) == held
    lease_busy = {"value": True}
    monkeypatch.setattr(
        restarted,
        "_direct_project_lease_busy",
        lambda project_id, candidate_job_id: lease_busy["value"],
    )
    released = asyncio.run(restarted.continue_plan(**held))
    assert released["idempotent"] is False and released["launched"] is None
    assert restarted.progress("plan-1")["supervision"]["state"] == "released"
    assert len(engine.created) == 1

    restarted_again = PlanOrchestrator(
        type(storage)(), engine, store=PlanOrchestratorStore(type(storage)()),
    )
    monkeypatch.setattr(
        restarted_again,
        "_direct_project_lease_busy",
        lambda project_id, candidate_job_id: lease_busy["value"],
    )
    asyncio.run(restarted_again.tick())
    assert restarted_again.progress("plan-1")["supervision"]["state"] == "released"
    assert len(engine.created) == 1

    lease_busy["value"] = False
    next_job = launch_identity("plan-1", "WO-2")["job_id"]
    assert storage.get(next_job) is None
    assert_released_retry_is_read_only(
        restarted_again, restarted_again.store, engine, held,
    )
    assert storage.get(next_job) is None

    asyncio.run(restarted_again.tick())
    assert len(engine.created) == 2
    assert storage.get(next_job) is not None
    complete_job(storage, engine.created[1])
    asyncio.run(restarted_again.tick())
    newer = continuation_payload(restarted_again)
    assert newer["generation"] == held["generation"] + 1
    assert newer["continuation_key"] != held["continuation_key"]
    with pytest.raises(PlanContinuationConflict):
        restarted_again.store.release_supervision(**held)


def test_released_retry_does_not_reconcile_terminal_child_before_normal_tick(supervision_db):
    storage, store = supervision_db
    create_plan(storage, roles=("developer", "developer", "developer"))
    service, engine = service_for(storage, store)
    asyncio.run(service.tick())
    complete_job(storage, engine.created[0])
    asyncio.run(service.tick())
    released = continuation_payload(service)
    asyncio.run(service.continue_plan(**released))

    child_job = engine.created[1]
    complete_job(storage, child_job)
    assert store.work_orders("plan-1")[1]["state"] == "running"
    assert store.orchestration("plan-1")["status"] == "executing"
    assert not any(
        checkpoint["work_order_id"] == "WO-2" and checkpoint["kind"] == "completed"
        for checkpoint in store.checkpoints("plan-1")
    )

    assert_released_retry_is_read_only(service, store, engine, released)
    assert store.work_orders("plan-1")[1]["state"] == "running"

    asyncio.run(service.tick())
    rows = store.work_orders("plan-1")
    assert [row["state"] for row in rows] == ["completed", "completed", "pending"]
    assert any(
        checkpoint["work_order_id"] == "WO-2" and checkpoint["kind"] == "completed"
        for checkpoint in store.checkpoints("plan-1")
    )
    newer = continuation_payload(service)
    assert newer["generation"] == released["generation"] + 1
    assert store.orchestration("plan-1")["status"] == "supervised_hold"
    assert len(engine.created) == 2


def test_stale_identity_matrix_and_protected_states_do_not_mutate(supervision_db):
    storage, store = supervision_db
    create_plan(storage)
    service, engine = service_for(storage, store)
    asyncio.run(service.tick())
    complete_job(storage, engine.created[0])
    asyncio.run(service.tick())
    valid = continuation_payload(service)

    variants = []
    for key, value in (
        ("generation", valid["generation"] + 1),
        ("continuation_key", "plan:continue:" + "0" * 64),
        ("checkpoint_id", valid["checkpoint_id"] + 1),
        ("checkpoint_key", valid["checkpoint_key"] + ":wrong"),
        ("ready_work_order_ids", valid["ready_work_order_ids"] + ["WO-X"]),
        ("plan_id", "wrong-plan"),
    ):
        variants.append({**valid, key: value})
    before = deepcopy(store.orchestration("plan-1"))
    for request in variants:
        with pytest.raises(PlanContinuationConflict):
            store.release_supervision(**request)
        assert store.orchestration("plan-1") == before

    store.update_plan("plan-1", status="blocked")
    with pytest.raises(PlanContinuationConflict):
        store.release_supervision(**valid)
    assert store.orchestration("plan-1")["supervision_state"] == "held"

    with storage.connect() as conn:
        conn.execute("UPDATE cp_plan_orchestrations SET status='waiting_merge' WHERE plan_id='plan-1'")
    with pytest.raises(PlanContinuationConflict):
        store.release_supervision(**valid)
    assert store.orchestration("plan-1")["supervision_state"] == "held"

    with storage.connect() as conn:
        conn.execute("UPDATE cp_plan_orchestrations SET status='waiting_human' WHERE plan_id='plan-1'")
    with pytest.raises(PlanContinuationConflict):
        store.release_supervision(**valid)
    assert store.orchestration("plan-1")["supervision_state"] == "held"

    with storage.connect() as conn:
        plan = conn.execute("SELECT plan FROM cp_execution_plans WHERE id='plan-1'").fetchone()["plan"]
        plan["decision_boundaries"] = [{"id": "D-1"}]
        conn.execute("UPDATE cp_execution_plans SET plan=%s::jsonb WHERE id='plan-1'", (json.dumps(plan),))
    with pytest.raises(PlanContinuationConflict):
        store.release_supervision(**valid)
    assert store.orchestration("plan-1")["supervision_state"] == "held"


def test_autonomous_and_legacy_plans_continue_without_supervision_records(supervision_db):
    storage, store = supervision_db
    create_plan(storage, mode="")
    service, engine = service_for(storage, store)
    asyncio.run(service.tick())
    complete_job(storage, engine.created[0])
    asyncio.run(service.tick())

    assert len(engine.created) == 2
    progress = service.progress("plan-1")
    assert progress["supervision"] == {"mode": "autonomous", "state": None}
    orchestration = store.orchestration("plan-1")
    assert orchestration["supervision_generation"] == 0
    request = {
        "plan_id": "plan-1",
        "generation": 1,
        "checkpoint_id": 1,
        "checkpoint_key": "wo:completed:legacy",
        "ready_work_order_ids": ["WO-2"],
    }
    request["continuation_key"] = build_continuation_key(**request)
    with pytest.raises(PlanContinuationConflict, match="not supervised"):
        store.release_supervision(**request)


def test_concurrent_release_is_one_transition_and_one_child_launch(supervision_db):
    storage, store = supervision_db
    create_plan(storage)
    service, engine = service_for(storage, store)
    asyncio.run(service.tick())
    complete_job(storage, engine.created[0])
    asyncio.run(service.tick())
    request = continuation_payload(service)

    def release(_):
        recreated = PlanOrchestratorStore(type(storage)())
        return recreated.release_supervision(**deepcopy(request))["changed"]

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(release, range(2)))
    assert sorted(outcomes) == [False, True]
    assert store.orchestration("plan-1")["supervision_state"] == "released"

    asyncio.run(service.tick())
    assert len(engine.created) == 2
    assert store.work_orders("plan-1")[1]["state"] == "running"


def test_simultaneous_continue_calls_use_one_launch_path(supervision_db):
    storage, store = supervision_db
    create_plan(storage)
    service, engine = service_for(storage, store)
    asyncio.run(service.tick())
    complete_job(storage, engine.created[0])
    asyncio.run(service.tick())
    request = continuation_payload(service)

    async def continue_twice():
        return await asyncio.gather(
            service.continue_plan(**deepcopy(request)),
            service.continue_plan(**deepcopy(request)),
        )

    outcomes = asyncio.run(continue_twice())
    assert sorted(result["idempotent"] for result in outcomes) == [False, True]
    assert len(engine.created) == 2
    assert len(set(engine.created)) == 2
    assert store.work_orders("plan-1")[1]["state"] == "running"


def test_release_persistence_failure_rolls_back_and_creates_no_child(
    supervision_db, monkeypatch,
):
    storage, store = supervision_db
    create_plan(storage)
    service, engine = service_for(storage, store)
    asyncio.run(service.tick())
    complete_job(storage, engine.created[0])
    asyncio.run(service.tick())
    request = continuation_payload(service)
    real_release = store._mark_supervision_released

    def fail_after_update(conn, **kwargs):
        real_release(conn, **kwargs)
        raise RuntimeError("injected continuation persistence failure")

    monkeypatch.setattr(store, "_mark_supervision_released", fail_after_update)
    with pytest.raises(RuntimeError, match="injected continuation"):
        store.release_supervision(**request)

    current = store.orchestration("plan-1")
    assert current["status"] == "supervised_hold"
    assert current["supervision_state"] == "held"
    assert current["supervision_continuation_key"] == request["continuation_key"]
    assert len(engine.created) == 1


def test_retry_after_first_release_tick_failure_does_not_tick_again(
    supervision_db, monkeypatch,
):
    storage, store = supervision_db
    create_plan(storage)
    service, engine = service_for(storage, store)
    asyncio.run(service.tick())
    complete_job(storage, engine.created[0])
    asyncio.run(service.tick())
    request = continuation_payload(service)
    failed_tick = AsyncMock(side_effect=RuntimeError("injected post-release tick failure"))
    monkeypatch.setattr(service, "tick", failed_tick)

    with pytest.raises(RuntimeError, match="post-release tick failure"):
        asyncio.run(service.continue_plan(**request))
    assert store.orchestration("plan-1")["supervision_state"] == "released"
    assert len(engine.created) == 1

    retry = asyncio.run(service.continue_plan(**request))
    assert retry["idempotent"] is True
    assert retry["launched"] is None
    assert failed_tick.await_count == 1
    assert len(engine.created) == 1


def test_authenticated_continue_api_is_strict_and_exact(supervision_db, monkeypatch):
    storage, store = supervision_db
    create_plan(storage)
    service, engine = service_for(storage, store)
    asyncio.run(service.tick())
    complete_job(storage, engine.created[0])
    asyncio.run(service.tick())
    request = continuation_payload(service)
    body = {key: value for key, value in request.items() if key != "plan_id"}
    monkeypatch.setattr(main, "plan_orchestrator", service)
    monkeypatch.setenv("RUNTIME_API_TOKEN", "supervision-api-token")
    client = TestClient(main.app)
    path = "/v1/plans/plan-1/continue"

    assert client.post(path, json=body).status_code == 401
    assert client.post(
        path,
        json={**body, "unexpected": True},
        headers={"Authorization": "Bearer supervision-api-token"},
    ).status_code == 422
    response = client.post(
        path,
        json=body,
        headers={"Authorization": "Bearer supervision-api-token"},
    )
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "released"
    assert response.json()["idempotent"] is False
    assert len(engine.created) == 2
    child_job = engine.created[1]
    complete_job(storage, child_job, pr_number=61)
    engine.ddev.prs[61] = {
        "number": 61,
        "url": "https://example.test/pull/61",
        "head": "e" * 40,
        "state": "open",
        "merged": False,
    }
    asyncio.run(service.tick())
    assert store.orchestration("plan-1")["status"] == "waiting_merge"
    before = deepcopy(store.orchestration("plan-1"))
    retry = client.post(
        path,
        json=body,
        headers={"Authorization": "Bearer supervision-api-token"},
    )
    assert retry.status_code == 200 and retry.json()["idempotent"] is True
    assert len(engine.created) == 2
    assert store.orchestration("plan-1") == before
