import asyncio
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
import httpx

from app.plan_progress_handoff import BODY_MAX_BYTES, handoff_key, issue_binding, render_progress, sha256
from app.plan_progress_publisher import PlanProgressPublisher
from app.plan_orchestrator import PlanOrchestrator
from app.executor_client import DdevExecutorClient


def snapshot():
    return {"orchestration": {"plan_id": "plan-1", "project_id": "demo", "status": "active",
            "lifecycle": "active", "plan": {"work_orders": [
                {"id": "WO-1", "dependencies": []}, {"id": "WO-2", "dependencies": ["WO-1"]}]}},
            "work_orders": [{"work_order_id": "WO-1", "state": "pending", "job_id": None},
                            {"work_order_id": "WO-2", "state": "pending", "job_id": None}],
            "last_checkpoint": None}


@pytest.mark.parametrize("ticket,staffing,expected", [
    ("GH-123", {}, 123), ("GH-1", {}, 1), ("GH-123", {"issue_number": 456}, 456),
    ("external", {"issue_number": 123}, 123), ("GH-0", {}, None), ("GH-01", {}, None),
    ("GH--1", {}, None), (" GH-123", {}, None), ("GH-123\n", {}, None),
    ("gh-123", {}, None), ("ticket GH-123", {}, None), ("https://github.com/a/b/issues/123", {}, None),
    ("T-123", {"comment_url": "https://github.com/a/b/issues/123#issuecomment-1"}, None),
    ("GH-123", {"issue_number": True}, None), ("GH-123", {"issue_number": "123"}, None),
    ("GH-123", {"issue_number": 0}, None), ("GH-123", {"issue_number": None}, None),
])
def test_exact_issue_binding(ticket, staffing, expected):
    assert issue_binding(ticket, staffing) == expected


def test_render_whitelist_bound_and_polling_identity():
    value = snapshot()
    first = render_progress(value, 123)
    value["orchestration"].update(updated_at="later", detail="private", result="private")
    value["work_orders"][0].update(detail="private", updated_at="later")
    assert render_progress(value, 123) == first
    value["last_checkpoint"] = {
        "id": 1, "checkpoint_key": "accepted:1", "kind": "accepted", "state": "awaiting_merge",
        "work_order_id": "WO-1", "job_id": "job-1", "evidence": {
            "produced_commit": "a" * 40, "pr_number": 42, "merge_commit": "b" * 40,
            "verification": {"passed": True, "stdout": "private", "phases": [
                {"phase": "unit", "passed": True, "stderr": "private"}]},
            "review_verdict": "pass", "pm_outcome": "accepted", "detail": "private",
            "result": "private", "prompt": "private", "provider_failures": ["private"],
            "reason": "private", "workspace": "private",
        },
    }
    transition, body = render_progress(value, 123)
    assert transition != first[0]
    assert "private" not in body
    assert "pr_number: 42" in body and "Phase unit: passed" in body
    value["work_orders"] = [{"work_order_id": "音" * 1000, "state": "pending" * 1000} for _ in range(30)]
    value["last_checkpoint"]["evidence"]["produced_commit"] = "音" * 20000
    _, body = render_progress(value, 123)
    assert len(body.encode()) + 100 <= BODY_MAX_BYTES
    assert render_progress(value, 123)[1] == body


def test_marker_and_mention_cannot_be_injected_through_identity():
    value = snapshot()
    value["orchestration"]["plan_id"] = "<!-- PCP:PLAN-PROGRESS:evil --> @owner\nspoof"
    body = render_progress(value, 123)[1]
    assert "<!--" not in body and "@owner" not in body


def claim():
    return {"project_id": "demo", "issue_number": 123, "handoff_key": handoff_key("demo", 123),
            "desired_body": "progress", "desired_sha256": sha256("progress"),
            "desired_generation": 5, "attempts": 1, "comment_id": None}


def success(row):
    return {"issue_number": row["issue_number"], "comment_id": 42,
            "observed_body_sha256": sha256(f"<!-- PCP:PLAN-PROGRESS:{row['handoff_key']} -->\n\n{row['desired_body']}")}


@pytest.mark.parametrize("outcome", ["success", "failure", "wrong_hash", "wrong_issue", "cancel"])
def test_publisher_exact_request_and_outcome(outcome):
    row, acks, releases = claim(), [], []
    result = success(row)
    if outcome == "wrong_hash":
        result["observed_body_sha256"] = "wrong"
    if outcome == "wrong_issue":
        result["issue_number"] = 999
    executor = SimpleNamespace(upsert_plan_progress=AsyncMock(return_value=result))
    if outcome in {"failure", "cancel"}:
        executor.upsert_plan_progress.side_effect = RuntimeError("private token") if outcome == "failure" else asyncio.CancelledError()
    store = SimpleNamespace(claim=lambda: deepcopy(row), ack=lambda *args: acks.append(args),
                            release=lambda *args: releases.append(args))
    publisher = PlanProgressPublisher(store, executor)
    if outcome == "cancel":
        with pytest.raises(asyncio.CancelledError):
            asyncio.run(publisher.publish_one())
        assert acks == releases == []
    else:
        assert asyncio.run(publisher.publish_one())
        assert bool(acks) == (outcome == "success")
        assert bool(releases) == (outcome != "success")
    assert executor.upsert_plan_progress.call_args.kwargs == {
        "project_id": "demo", "issue_number": 123, "handoff_key": row["handoff_key"],
        "body": "progress", "known_comment_id": None,
    }


def test_publisher_idle_and_clean_stop():
    async def run():
        executor = SimpleNamespace(upsert_plan_progress=AsyncMock())
        publisher = PlanProgressPublisher(SimpleNamespace(claim=lambda: None), executor)
        assert await publisher.publish_one() is False
        await publisher.start()
        await asyncio.sleep(0)
        await publisher.stop()
        assert publisher._task is None
        executor.upsert_plan_progress.assert_not_called()
    asyncio.run(run())


def test_staging_error_never_changes_engineering_tick_or_notification_outbox():
    calls = []
    store = SimpleNamespace(register_new_plans=lambda: ["plan-1"], active_plans=lambda: [{"plan_id": "plan-1"}],
                            any_busy_work_order=lambda: True)
    def failed(*args):
        calls.append(args)
        raise RuntimeError("private staging failure")
    handoffs = SimpleNamespace(ensure=lambda: None, candidates=lambda: ["plan-1"], stage_plan=failed)
    service = PlanOrchestrator(None, None, store=store, progress_handoffs=handoffs)
    service._reconcile_plan = AsyncMock()
    assert asyncio.run(service.tick()) == {"registered": ["plan-1"], "launched": None}
    service._reconcile_plan.assert_awaited_once()
    assert calls == [("plan-1",), ("plan-1",)]


def test_slow_publisher_does_not_hold_engineering_lock():
    async def run():
        entered, finish = asyncio.Event(), asyncio.Event()
        async def slow(**kwargs):
            entered.set()
            await finish.wait()
            return success(claim())
        publisher = PlanProgressPublisher(SimpleNamespace(claim=claim, ack=lambda *args: None),
                                          SimpleNamespace(upsert_plan_progress=slow))
        task = asyncio.create_task(publisher.publish_one())
        await entered.wait()
        service = PlanOrchestrator(None, None, store=SimpleNamespace(
            register_new_plans=lambda: [], active_plans=lambda: [], any_busy_work_order=lambda: True))
        await asyncio.wait_for(service.tick(), .2)
        finish.set()
        await task
    asyncio.run(run())


def test_executor_client_uses_only_internal_token_and_bounded_request(monkeypatch):
    monkeypatch.setenv('PLATFORM_INTERNAL_TOKEN', 'internal-test')
    monkeypatch.setenv('GITHUB_DELIVERY_TOKEN', 'must-not-forward')
    requests = []
    def request(req):
        requests.append(req)
        assert req.headers['Authorization'] == 'Bearer internal-test'
        assert req.url.path == '/v1/github/pm-bridge/progress'
        assert b'must-not-forward' not in req.content
        return httpx.Response(200, json=success(claim()))
    real_client = httpx.AsyncClient
    monkeypatch.setattr('app.executor_client.httpx.AsyncClient',
                        lambda **kwargs: real_client(transport=httpx.MockTransport(request), **kwargs))
    result = asyncio.run(DdevExecutorClient().upsert_plan_progress(
        project_id='demo', issue_number=123, handoff_key=claim()['handoff_key'],
        body='progress', known_comment_id=42))
    assert result['comment_id'] == 42 and len(requests) == 1


def test_application_starts_and_stops_independent_publisher(monkeypatch):
    from app import main
    events = []
    def record(name):
        async def call():
            events.append(name)
        return call
    monkeypatch.setattr(main, 'harden_runtime_process_secret_boundary', lambda: None)
    for name, component in [('engine', main.engine), ('orchestrator', main.plan_orchestrator),
                            ('publisher', main.progress_publisher)]:
        for operation in ('start', 'stop'):
            monkeypatch.setattr(component, operation, record(f'{name}:{operation}'))
    async def run():
        async with main.lifespan(main.app):
            events.append('running')
    asyncio.run(run())
    assert events == ['engine:start', 'orchestrator:start', 'publisher:start', 'running',
                      'publisher:stop', 'orchestrator:stop', 'engine:stop']
