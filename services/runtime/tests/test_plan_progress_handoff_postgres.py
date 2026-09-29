import asyncio
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.plan_progress_store import PlanProgressStore
from app.plan_progress_publisher import PlanProgressPublisher
from app.plan_orchestrator import PlanOrchestrator, PlanOrchestratorStore
from test_orchestrator_launch_postgres import launch_db  # noqa: F401
from test_plan_progress_handoff import success


@pytest.fixture
def handoffs(launch_db):
    store = PlanProgressStore(launch_db)
    store.ensure()
    with launch_db.connect() as conn:
        conn.execute("UPDATE cp_execution_plans SET created_at=clock_timestamp(),ticket=jsonb_set(ticket,'{id}','\"GH-123\"')")
        conn.execute("UPDATE cp_plan_orchestrations SET ticket_id='GH-123'")
    return store


def row(store):
    with store.storage.connect() as conn:
        return conn.execute("SELECT * FROM cp_plan_progress_handoffs").fetchone()


def expire(store):
    with store.storage.connect() as conn:
        conn.execute("UPDATE cp_plan_progress_handoffs SET lease_until=now()-interval '1 second',available_at=now()-interval '1 second'")


def test_initial_ticks_stage_once_and_ignore_polling_changes(handoffs):
    engine_store = PlanOrchestratorStore(handoffs.storage)
    service = PlanOrchestrator(handoffs.storage, None, store=engine_store, progress_handoffs=handoffs)
    service._reconcile_plan = AsyncMock()
    engine_store.any_busy_work_order = lambda: True
    asyncio.run(service.tick())
    original = row(handoffs)
    assert original['desired_generation'] == 1
    asyncio.run(service.tick())
    assert row(handoffs) == original
    engine_store.update_work_order("plan-1", "WO-1", detail={"private": "raw result"})
    assert not handoffs.stage_plan("plan-1")
    assert row(handoffs) == original


@pytest.mark.parametrize("kind,source,target,status", [
    ("started", "pending", "running", "executing"),
    ("accepted", "running", "awaiting_merge", "waiting_merge"),
    ("merged", "awaiting_merge", "completed", "completed"),
    ("completed", "running", "completed", "completed"),
    ("blocked", "running", "blocked", "blocked"),
    ("waiting_human", "running", "waiting_human", "waiting_human"),
    ("repair_reopened", "awaiting_merge", "running", "executing"),
])
def test_durable_transitions_keep_same_handoff(handoffs, kind, source, target, status):
    engineering = PlanOrchestratorStore(handoffs.storage)
    engineering.update_work_order("plan-1", "WO-1", state=source)
    assert handoffs.stage_plan("plan-1")
    first = row(handoffs)
    cp = engineering.transition_work_order(
        expected=engineering.work_orders("plan-1")[0], checkpoint_key=kind, kind=kind,
        state=target, evidence={"produced_commit": "a" * 40, "verification": {"passed": True}},
    )
    engineering.update_plan("plan-1", status=status)
    # Candidate recovery must include blocked/completed, even after a crash.
    restarted = PlanProgressStore(type(handoffs.storage)())
    restarted.ensure()
    assert restarted.candidates() == ["plan-1"]
    assert restarted.stage_plan("plan-1")
    second = row(restarted)
    assert second['handoff_key'] == first['handoff_key']
    assert second['desired_generation'] == 2
    assert f"State: {status}" in second['desired_body']
    assert f"kind: {kind}" in second['desired_body']
    assert not restarted.stage_plan("plan-1")
    assert engineering.checkpoints("plan-1") == [cp]


def test_ack_of_older_generation_preserves_newest_pending_and_comment(handoffs):
    handoffs.stage_plan("plan-1")
    first = handoffs.claim()
    PlanOrchestratorStore(handoffs.storage).update_plan("plan-1", status="completed")
    handoffs.stage_plan("plan-1")
    assert handoffs.claim() is None  # New generation cannot race in-flight request.
    assert handoffs.ack(first, 42)
    current = row(handoffs)
    assert (current['status'], current['published_generation'], current['desired_generation'], current['comment_id']) == ('pending', 1, 2, 42)
    assert current['published_sha256'] == first['desired_sha256']
    latest = handoffs.claim()
    assert latest['desired_generation'] == 2 and latest['comment_id'] == 42
    assert handoffs.ack(latest, 42)
    assert row(handoffs)['status'] == 'sent'


def test_lease_restart_and_stale_attempt_fencing(handoffs):
    handoffs.stage_plan("plan-1")
    first = handoffs.claim()
    assert handoffs.claim() is None
    expire(handoffs)
    restarted = PlanProgressStore(type(handoffs.storage)())
    restarted.ensure()
    recovered = restarted.claim()
    assert recovered['attempts'] == first['attempts'] + 1
    assert not restarted.ack(first, 10)
    assert not restarted.release(first, RuntimeError("old"))
    assert restarted.ack(recovered, 42)
    assert row(restarted)['status'] == 'sent'
    assert restarted.claim() is None


def test_concurrent_claims_and_locked_row_skip(handoffs):
    handoffs.stage_plan("plan-1")
    with handoffs.storage.connect() as conn:
        conn.execute("SELECT * FROM cp_plan_progress_handoffs FOR UPDATE")
        assert handoffs.claim() is None
    with ThreadPoolExecutor(max_workers=2) as pool:
        claims = list(pool.map(lambda _: PlanProgressStore(handoffs.storage).claim(), range(2)))
    assert sum(item is not None for item in claims) == 1


def test_publication_failure_preserves_all_engineering_and_retries_latest(handoffs):
    engineering = PlanOrchestratorStore(handoffs.storage)
    service = PlanOrchestrator(handoffs.storage, None, store=engineering)
    before = deepcopy(service.progress("plan-1"))
    handoffs.stage_plan("plan-1")
    executor = SimpleNamespace(upsert_plan_progress=AsyncMock(side_effect=RuntimeError("private token stdout")))
    publisher = PlanProgressPublisher(handoffs, executor)
    asyncio.run(publisher.publish_one())
    current = row(handoffs)
    assert current['status'] == 'pending' and current['last_error'] == 'RuntimeError'
    assert current['available_at'] > current['updated_at']
    assert service.progress("plan-1") == before
    assert engineering.checkpoints("plan-1") == []
    with handoffs.storage.connect() as conn:
        assert conn.execute("SELECT count(*) AS n FROM cp_notification_outbox").fetchone()['n'] == 0
    engineering.update_plan("plan-1", status="completed")
    handoffs.stage_plan("plan-1")
    newest = handoffs.claim()
    assert newest['desired_generation'] == 2


def test_historical_exclusion_and_existing_row_recovery(handoffs):
    with handoffs.storage.connect() as conn:
        conn.execute("UPDATE cp_execution_plans SET created_at=now()-interval '1 day'")
    assert handoffs.candidates() == []
    assert not handoffs.stage_plan("plan-1")
    with handoffs.storage.connect() as conn:
        conn.execute("UPDATE cp_execution_plans SET created_at=clock_timestamp()")
    handoffs.stage_plan("plan-1")
    claimed = handoffs.claim()
    # Existing durable rows remain recoverable even across a later install boundary.
    with handoffs.storage.connect() as conn:
        conn.execute("UPDATE cp_plan_progress_meta SET installed_at=now()+interval '1 day'")
    restarted = PlanProgressStore(type(handoffs.storage)())
    restarted.ensure()
    assert restarted.candidates() == ["plan-1"]
    assert not restarted.stage_plan("plan-1")
    assert restarted.ack(claimed, 42)


@pytest.mark.parametrize('ticket,staffing,eligible', [
    ('external', '{"issue_number":123}', True), ('GH-123', '{}', True),
    ('external', '{}', False), ('external', '{"comment_url":"https://github.com/a/b/issues/123"}', False),
])
def test_durable_binding_only(handoffs, ticket, staffing, eligible):
    with handoffs.storage.connect() as conn:
        conn.execute("UPDATE cp_plan_orchestrations SET ticket_id=%s", (ticket,))
        conn.execute("UPDATE cp_execution_plans SET staffing=%s::jsonb", (staffing,))
    assert handoffs.stage_plan('plan-1') is eligible
    assert (row(handoffs) is not None) is eligible


def test_later_plan_reuses_comment_and_old_plan_cannot_take_it_back(handoffs):
    handoffs.stage_plan('plan-1')
    handoffs.ack(handoffs.claim(), 42)
    original = row(handoffs)
    with handoffs.storage.connect() as conn:
        conn.execute("""INSERT INTO cp_execution_plans
            (id,project_id,status,baseline_revision,baseline_source_commit,ticket,plan,staffing,created_at,updated_at)
            SELECT 'plan-2',project_id,status,baseline_revision,baseline_source_commit,ticket,plan,staffing,
                   clock_timestamp(),clock_timestamp() FROM cp_execution_plans WHERE id='plan-1'""")
    PlanOrchestratorStore(handoffs.storage).register_new_plans()
    assert handoffs.stage_plan('plan-2')
    assert not handoffs.stage_plan('plan-1')
    current = row(handoffs)
    assert current['handoff_key'] == original['handoff_key']
    assert (current['comment_id'], current['plan_id'], current['desired_generation']) == (42, 'plan-2', 2)


def test_publisher_success_persists_across_recreation(handoffs):
    handoffs.stage_plan('plan-1')
    expected = row(handoffs)
    executor = SimpleNamespace(upsert_plan_progress=AsyncMock(return_value=success(expected)))
    asyncio.run(PlanProgressPublisher(handoffs, executor).publish_one())
    restarted = PlanProgressStore(type(handoffs.storage)())
    assert row(restarted)['status'] == 'sent'
    assert row(restarted)['comment_id'] == 42
    assert restarted.claim() is None


def test_failed_terminal_staging_recovers_on_next_tick(handoffs, monkeypatch):
    engineering = PlanOrchestratorStore(handoffs.storage)
    engineering.update_work_order('plan-1', 'WO-1', state='running')
    handoffs.stage_plan('plan-1')
    before = row(handoffs)
    service = PlanOrchestrator(handoffs.storage, None, store=engineering, progress_handoffs=handoffs)
    async def complete(plan):
        engineering.transition_work_order(
            expected=engineering.work_orders('plan-1')[0], checkpoint_key='final',
            kind='completed', state='completed', evidence={'verification': {'passed': True}})
        engineering.update_plan('plan-1', status='completed')
    service._reconcile_plan = complete
    engineering.any_busy_work_order = lambda: True
    actual_stage = handoffs.stage_plan
    def fail(plan_id):
        raise RuntimeError('staging unavailable')
    monkeypatch.setattr(handoffs, 'stage_plan', fail)
    asyncio.run(service.tick())
    assert engineering.orchestration('plan-1')['status'] == 'completed'
    assert len(engineering.checkpoints('plan-1')) == 1
    assert row(handoffs) == before
    monkeypatch.setattr(handoffs, 'stage_plan', actual_stage)
    asyncio.run(service.tick())
    assert 'State: completed' in row(handoffs)['desired_body']
    assert row(handoffs)['desired_generation'] == 2


def test_failure_keeps_known_comment_and_bounded_retry_does_not_stop(handoffs):
    handoffs.stage_plan('plan-1')
    handoffs.ack(handoffs.claim(), 42)
    PlanOrchestratorStore(handoffs.storage).update_plan('plan-1', status='completed')
    handoffs.stage_plan('plan-1')
    with handoffs.storage.connect() as conn:
        conn.execute('UPDATE cp_plan_progress_handoffs SET attempts=100000')
    claimed = handoffs.claim()
    assert handoffs.release(claimed, RuntimeError('secret' * 20000))
    current = row(handoffs)
    assert current['comment_id'] == 42
    assert current['status'] == 'pending'
    assert (current['available_at'] - current['updated_at']).total_seconds() == 300
    assert current['last_error'] == 'RuntimeError'


def test_installation_time_is_durable_across_ensure_and_restart(handoffs):
    with handoffs.storage.connect() as conn:
        original = conn.execute('SELECT installed_at FROM cp_plan_progress_meta').fetchone()
    PlanProgressStore(type(handoffs.storage)()).ensure()
    with handoffs.storage.connect() as conn:
        assert conn.execute('SELECT installed_at FROM cp_plan_progress_meta').fetchone() == original
