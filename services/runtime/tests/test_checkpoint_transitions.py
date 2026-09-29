from __future__ import annotations

import asyncio
import json
from copy import deepcopy
from datetime import datetime, timezone

import pytest

from app.plan_orchestrator import PlanOrchestrator
from app.work_order_checkpoints import checkpoint_evidence, transition_key
from test_plan_orchestrator import orchestrator, tracked, work_order


def fixture(*, state="pending", operator=False):
    return orchestrator(
        [work_order("WO-1", requested_role="operator" if operator else "developer"),
         work_order("WO-2", dependencies=["WO-1"])],
        [tracked("WO-1", 0, state=state, execution_mode="operator" if operator else "agent",
                 job_id="job-1" if state != "pending" and not operator else None), tracked("WO-2", 1)],
    )


def job(*, status="completed", pr=True):
    return {
        "id": "job-1", "status": status, "branch": "ai/job-1", "source_commit": "a" * 40,
        "updated_at": datetime(2026, 9, 29, tzinfo=timezone.utc),
        "checkpoint": {}, "progress": {"model_calls": 2, "repair_iterations": 1, "verification_attempts": 2, "test_runs": 3},
        "result": {"commit": "b" * 40, "verification": {"passed": True, "phases": [
            {"phase": "targeted_tests", "passed": True, "stdout": "PRIVATE"},
        ]}, "review": {"verdict": "pass", "raw": "PRIVATE"}, "pm_evidence": {"outcome": "accepted"},
            "delivery": {"pull_request": {"number": 7, "head": "b" * 40, "url": "https://example.test/pr/7"}} if pr else {}},
    }


def test_started_commits_before_enqueue_and_restart_does_not_duplicate():
    service, storage, engine, store = fixture()
    async def enqueue(job_id):
        assert store.tracked[0]["state"] == "running"
        assert store.checkpoint_history[0]["kind"] == "started"
        assert store.checkpoint_history[0]["job_id"] == job_id
        engine.enqueued.append(job_id)
    engine.enqueue = enqueue
    asyncio.run(service.tick())
    assert len(store.checkpoint_history) == 1
    recreated = PlanOrchestrator(storage, engine, store=store)
    asyncio.run(recreated.tick())
    assert len(store.checkpoint_history) == 1
    assert len(engine.created) == len(engine.enqueued) == 1


def test_start_checkpoint_failure_does_not_enqueue_or_unlock(monkeypatch):
    service, storage, engine, store = fixture()
    def fail(**kwargs):
        raise RuntimeError("checkpoint unavailable")
    monkeypatch.setattr(store, "transition_work_order", fail)
    with pytest.raises(RuntimeError, match="unavailable"):
        asyncio.run(service.tick())
    assert [row["state"] for row in store.tracked] == ["pending", "pending"]
    assert engine.enqueued == []


def test_operator_ready_is_one_waiting_checkpoint():
    service, storage, engine, store = fixture(operator=True)
    asyncio.run(service.tick())
    asyncio.run(service.tick())
    assert [row["kind"] for row in store.checkpoint_history] == ["waiting_human"]
    assert store.checkpoint_history[0]["evidence"]["reason"] == "operator_execution_required"
    assert engine.created == []


@pytest.mark.parametrize("key", ["protected:scope:request-1", None])
def test_runtime_waiting_human_identity_and_unchanged_polls(key):
    service, storage, engine, store = fixture(state="running")
    storage.jobs["job-1"] = job(status="waiting_human")
    storage.jobs["job-1"]["checkpoint"] = {"pending_decision": {"key": key, "source": "reassessment", "decision": {"raw": "PRIVATE"}}}
    asyncio.run(service.tick())
    asyncio.run(service.tick())
    cp = store.checkpoint_history[0]
    assert cp["kind"] == "waiting_human"
    assert cp["evidence"].get("decision_key") == key
    assert cp["evidence"]["decision_source"] == "reassessment"
    assert len(store.checkpoint_history) == 1
    assert "PRIVATE" not in json.dumps(cp)


def test_accepted_does_not_unlock_but_merged_does_and_preserves_prior_evidence():
    service, storage, engine, store = fixture(state="running")
    storage.jobs["job-1"] = job()
    asyncio.run(service.tick())
    accepted = deepcopy(store.checkpoint_history[0])
    assert accepted["kind"] == "accepted"
    assert accepted["state"] == "awaiting_merge"
    assert accepted["evidence"]["next"] == []
    assert engine.created == []
    engine.ddev.prs[7] = {"number": 7, "state": "open", "merged": False}
    asyncio.run(service.tick())
    assert len(store.checkpoint_history) == 1
    engine.ddev.prs[7] = {"number": 7, "state": "closed", "merged": True, "head": "b" * 40,
                          "merge_commit_sha": "c" * 40, "merged_at": "2026-09-29T12:00:00Z"}
    asyncio.run(service.tick())
    merged = store.checkpoint_history[1]
    assert merged["kind"] == "merged"
    assert merged["evidence"]["next"] == ["WO-2"]
    assert merged["evidence"]["merge_commit"] == "c" * 40
    assert len(engine.created) == 1
    assert store.checkpoint_history[2]["evidence"]["dependencies"] == {"WO-1": "completed"}
    storage.jobs[store.tracked[1]["job_id"]].update(status="blocked", result={"reason": "later_failure"})
    asyncio.run(service.tick())
    assert store.checkpoint_history[0] == accepted
    assert store.checkpoint_history[1] == merged
    assert store.checkpoint_history[-1]["kind"] == "blocked"
    before = deepcopy(store.checkpoint_history)
    asyncio.run(service.tick())
    assert store.checkpoint_history == before


def test_no_pr_completion_checkpoints_and_unlocks():
    service, storage, engine, store = fixture(state="running")
    storage.jobs["job-1"] = job(pr=False)
    asyncio.run(service.tick())
    assert store.checkpoint_history[0]["kind"] == "completed"
    assert store.checkpoint_history[0]["evidence"]["next"] == ["WO-2"]


@pytest.mark.parametrize("action,kind", [("complete", "completed"), ("block", "blocked")])
def test_operator_resolution_checkpoints(action, kind):
    service, storage, engine, store = fixture(state="waiting_human", operator=True)
    storage.get_execution_plan = lambda plan_id: store.plan
    asyncio.run(service.resolve_operator(plan_id=store.plan["plan_id"], work_order_id="WO-1", action=action, note="operator evidence"))
    cp = store.checkpoint_history[0]
    assert cp["kind"] == kind
    assert cp["job_id"] is None
    if action == "block":
        assert cp["evidence"]["reason"] == "operator evidence"
        assert engine.created == []


@pytest.mark.parametrize("backed", [True, False])
def test_block_job_and_block_tracked_capture_bounded_evidence(backed):
    service, storage, engine, store = fixture(state="running")
    storage.jobs["job-1"] = job(status="blocked")
    storage.jobs["job-1"]["result"]["reason"] = "verification_failed"
    if backed:
        service._block_job(store.plan, deepcopy(store.tracked[0]), storage.jobs["job-1"])
    else:
        service._block_tracked(store.plan, deepcopy(store.tracked[0]), "definition_missing")
    cp = store.checkpoint_history[0]
    assert cp["kind"] == "blocked"
    assert cp["evidence"]["reason"] == ("verification_failed" if backed else "definition_missing")
    assert cp["evidence"]["source_commit"] == "a" * 40
    assert cp["evidence"]["verification"] == {"passed": True, "phases": [{"phase": "targeted_tests", "passed": True}]}
    assert "PRIVATE" not in json.dumps(cp)


def test_distinct_repair_and_block_episodes_survive_same_counters():
    service, storage, engine, store = fixture(state="awaiting_merge")
    store.tracked[0]["pr_number"] = 7
    storage.jobs["job-1"] = job(status="queued")
    for request in ("repair-1", "repair-2"):
        storage.jobs["job-1"]["checkpoint"]["pending_review_repair"] = {
            "request_id": request, "expected_commit": "b" * 40, "pr_number": 7,
        }
        asyncio.run(service.tick())
        cp = deepcopy(store.checkpoint_history[-1])
        assert cp["kind"] == "repair_reopened"
        assert cp["evidence"]["review_repair_request_id"] == request
        assert cp["evidence"]["expected_commit"] == "b" * 40
        asyncio.run(service.tick())
        assert store.checkpoint_history[-1] == cp
        storage.jobs["job-1"]["status"] = "blocked"
        service._block_job(store.plan, deepcopy(store.tracked[0]), storage.jobs["job-1"])
        # Existing recovery paths update the durable source row; counters may stay unchanged.
        store.update_work_order(store.plan["plan_id"], "WO-1", state="awaiting_merge")
        store.update_plan(store.plan["plan_id"], status="active")
        storage.jobs["job-1"]["status"] = "queued"
    assert [cp["kind"] for cp in store.checkpoint_history] == ["repair_reopened", "blocked"] * 2
    assert len({cp["checkpoint_key"] for cp in store.checkpoint_history}) == 4


def test_new_block_after_recovery_without_new_request_or_counter_is_distinct():
    service, storage, engine, store = fixture(state="running")
    storage.jobs["job-1"] = job(status="blocked")
    for _ in range(2):
        service._block_job(store.plan, deepcopy(store.tracked[0]), storage.jobs["job-1"])
        store.update_work_order(store.plan["plan_id"], "WO-1", state="running")
    assert len({cp["checkpoint_key"] for cp in store.checkpoint_history}) == 2


def test_resolved_pm_decision_can_remain_in_bounded_checkpoint_context():
    row = job(status="blocked")
    row["checkpoint"]["last_pm_reassessment"] = {
        "decision": {"action": "human_decision"},
    }
    row["result"]["reason"] = "provider_failure_without_fallback"
    evidence = checkpoint_evidence(
        {"work_order_id": "WO-1"}, row, reason=row["result"]["reason"],
    )
    assert "pending_decision" not in row["checkpoint"]
    assert evidence["pm_action"] == "human_decision"
    assert evidence["reason"] == "provider_failure_without_fallback"


def test_evidence_whitelist_drops_nested_secrets_and_bounds_known_fields():
    row = job(status="blocked")
    row["checkpoint"].update({"prompt": "PRIVATE", "review_repair_churn_epoch": {
        "latest_verification_summary": {"passed": False, "failure_text": "PRIVATE"},
    }})
    row["progress"]["provider_failures"] = [{"stdout": "PRIVATE"}]
    row["result"].update(stdout="PRIVATE", stderr="PRIVATE", evaluator="PRIVATE")
    row["result"].pop("verification")
    cp = checkpoint_evidence(tracked("WO-1", 0), row, reason="é" * 10000)
    assert "PRIVATE" not in json.dumps(cp)
    assert len(cp["reason"].encode("utf-8")) <= 1000
    assert cp["verification"] == {"passed": False}
    assert cp["reason_sha256"]
    assert len(json.dumps(cp).encode("utf-8")) < 16384


def test_checkpoint_evidence_uses_bounded_last_deterministic_verification():
    row = job(status="blocked")
    row["result"].pop("verification")
    row["checkpoint"]["last_verification_summary"] = {
        "passed": False,
        "failure_text": "PRIVATE FAILURE",
        "phases": [{
            "phase": "full_tests", "passed": False, "stdout": "PRIVATE STDOUT",
        }],
    }
    cp = checkpoint_evidence(
        tracked("WO-1", 0), row, reason="provider_failure_without_fallback",
    )
    assert cp["verification"] == {
        "passed": False, "phases": [{"phase": "full_tests", "passed": False}],
    }
    assert "PRIVATE" not in json.dumps(cp)


def test_transition_key_is_stable_across_object_order_and_new_service():
    source = tracked("WO-1", 0, updated_at="persisted-version")
    evidence = {"decision_key": "decision-1", "decision_source": "pm"}
    key = transition_key(source, "waiting_human", "job-1", evidence)
    assert key == transition_key(deepcopy(source), "waiting_human", "job-1", dict(reversed(list(evidence.items()))))
    assert key != transition_key(source, "waiting_human", "job-1", {**evidence, "decision_key": "decision-2"})
