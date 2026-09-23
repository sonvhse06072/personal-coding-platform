from __future__ import annotations

import json
from copy import deepcopy

import pytest

from app.control_actions import ControlActionService
from app.engine import _apply_owner_budget_authorizations


class FakeStorage:
    def __init__(self, jobs=None):
        self.jobs = deepcopy(jobs or {})

    def get(self, job_id):
        value = self.jobs.get(job_id)
        return deepcopy(value) if value is not None else None

    def update(self, job_id, **fields):
        self.jobs[job_id].update(deepcopy(fields))


class FakeEngine:
    pass


class FakeStore:
    pass


def base_job(*, reason="execution_budget_exhausted", last_failure="model-call budget exhausted"):
    return {
        "id": "job-1",
        "status": "blocked",
        "updated_at": "2026-09-14T00:00:00+00:00",
        "route": {
            "strategy": {
                "budget": {
                    "max_model_calls": 10,
                    "max_tool_calls": 160,
                    "max_test_runs": 14,
                    "max_wall_time_minutes": 50,
                    "max_repair_iterations": 2,
                    "max_iterations": 8,
                }
            }
        },
        "progress": {
            "model_calls": 10,
            "tool_calls": 4,
            "test_runs": 2,
            "elapsed_minutes": 12.5,
            "repair_iterations": 1,
            "iteration": 3,
            "provider_failures": [],
        },
        "checkpoint": {
            "work_order": {
                "id": "WO-1",
                "budget": {"max_model_calls": 10},
            },
            "route_history": [],
        },
        "result": {
            "reason": reason,
            "last_failure": last_failure,
        },
    }


def row():
    return {
        "plan_id": "plan-1",
        "work_order_id": "WO-1",
        "execution_mode": "agent",
        "state": "blocked",
        "job_id": "job-1",
        "updated_at": "2026-09-14T00:00:00+00:00",
    }


def service(job=None):
    storage = FakeStorage({"job-1": job or base_job()})
    return ControlActionService(storage, FakeEngine(), FakeStore()), storage


def action_types(advisory):
    return [item["action_type"] for item in advisory["action_specs"]]


def test_model_call_budget_block_is_actionable_without_resetting_usage():
    controls, _ = service()

    advisory = controls.blocked_advisory(row(), base_job())

    assert advisory["reason"] == "execution_budget_exhausted"
    assert "not a provider" in advisory["cause"].lower()
    model_metric = next(item for item in advisory["metrics"] if item.get("key") == "max_model_calls")
    assert model_metric["used"] == 10
    assert model_metric["limit"] == 10
    extension = advisory["action_specs"][0]
    assert extension["action_type"] == "budget_extend"
    assert extension["payload"] == {"dimension": "max_model_calls", "increment": 4}
    assert "keep_blocked" in action_types(advisory)


def test_provider_quota_block_gets_quota_reset_action_but_sanitizes_raw_failure():
    job = base_job(
        reason="provider_failure_without_fallback",
        last_failure="RAW provider error with supersecret-token and /private/path",
    )
    job["progress"]["provider_failures"] = [
        {"model": "codex_terra", "provider": "openai", "kind": "quota_exhausted"}
    ]
    controls, _ = service(job)

    advisory = controls.blocked_advisory(row(), job)
    serialized = json.dumps(advisory, ensure_ascii=False)

    assert advisory["reason"] == "provider_failure_without_fallback"
    assert action_types(advisory)[:2] == ["provider_quota_reset", "reroute_provider"]
    assert "supersecret-token" not in serialized
    assert "/private/path" not in serialized
    assert "raw provider error" not in serialized.lower()


def test_unknown_block_reason_fails_closed_without_mutating_recovery_action():
    job = base_job(reason="unknown_future_block", last_failure="do something unsafe")
    controls, _ = service(job)

    advisory = controls.blocked_advisory(row(), job)

    assert action_types(advisory) == ["details", "keep_blocked"]
    assert "resume_same" not in action_types(advisory)
    assert "force_complete" not in action_types(advisory)


def test_ci_infrastructure_block_offers_only_preserved_delivery_recovery():
    job = base_job(
        reason="github_ci_infrastructure_failure",
        last_failure="quality failed before runner assignment",
    )
    job["result"]["accepted_result"] = {
        "status": "accepted",
        "commit": "b" * 40,
        "delivery": {"pull_request": {"number": 18}},
    }
    controls, _ = service(job)

    advisory = controls.blocked_advisory(row(), job)

    assert "before repository execution" in advisory["cause"]
    assert action_types(advisory) == [
        "retry_delivery",
        "recheck_ci",
        "details",
        "keep_blocked",
    ]
    assert "reroute_retry" not in action_types(advisory)


def test_budget_extension_is_additive_audited_and_preserves_work_order_and_progress():
    controls, storage = service()
    before = storage.get("job-1")
    action = {
        "action_id": "opaque-action",
        "job_id": "job-1",
        "payload": {"dimension": "max_model_calls", "increment": 4},
    }

    result = controls._apply_budget_extension(action)
    after = storage.get("job-1")

    assert result == {
        "dimension": "max_model_calls",
        "previous_limit": 10,
        "new_limit": 14,
        "used": 10,
    }
    assert after["route"]["strategy"]["budget"]["max_model_calls"] == 14
    assert after["progress"] == before["progress"]
    assert after["checkpoint"]["work_order"] == before["checkpoint"]["work_order"]
    audit = after["checkpoint"]["budget_authorizations"][-1]
    assert audit["channel"] == "telegram"
    assert audit["previous_limit"] == 10
    assert audit["new_limit"] == 14
    assert audit["used"] == 10


def test_owner_budget_authorization_survives_a_fresh_route_without_mutating_work_order():
    route = {"strategy": {"budget": {"max_model_calls": 10, "max_tool_calls": 80}}}
    checkpoint = {
        "work_order": {"id": "WO-1", "budget": {"max_model_calls": 10}},
        "budget_authorizations": [
            {
                "action_id": "opaque-action",
                "channel": "telegram",
                "dimension": "max_model_calls",
                "previous_limit": 10,
                "new_limit": 14,
                "used": 10,
            }
        ],
    }

    updated = _apply_owner_budget_authorizations(route, checkpoint)

    assert route["strategy"]["budget"]["max_model_calls"] == 10
    assert updated["strategy"]["budget"]["max_model_calls"] == 14
    assert checkpoint["work_order"]["budget"]["max_model_calls"] == 10


def test_owner_budget_overlay_ignores_untrusted_or_non_monotonic_checkpoint_data():
    route = {"strategy": {"budget": {"max_model_calls": 10}}}
    checkpoint = {
        "budget_authorizations": [
            {
                "action_id": "bad-channel",
                "channel": "unknown",
                "dimension": "max_model_calls",
                "previous_limit": 10,
                "new_limit": 99,
            },
            {
                "action_id": "bad-direction",
                "channel": "telegram",
                "dimension": "max_model_calls",
                "previous_limit": 10,
                "new_limit": 9,
            },
        ]
    }

    updated = _apply_owner_budget_authorizations(route, checkpoint)

    assert updated["strategy"]["budget"]["max_model_calls"] == 10


def test_budget_extension_fails_closed_at_platform_hard_max():
    job = base_job()
    job["route"]["strategy"]["budget"]["max_model_calls"] = 100
    controls, _ = service(job)

    with pytest.raises(RuntimeError, match="hard maximum"):
        controls._apply_budget_extension(
            {
                "action_id": "opaque-action",
                "job_id": "job-1",
                "payload": {"dimension": "max_model_calls", "increment": 4},
            }
        )


def test_state_fingerprint_changes_when_block_generation_changes():
    controls, _ = service()
    plan = {"plan_id": "plan-1", "status": "blocked", "updated_at": "t1"}
    work_order = row()
    job = base_job()

    first = controls.state_fingerprint(plan, work_order, job)
    job["updated_at"] = "t2"
    second = controls.state_fingerprint(plan, work_order, job)

    assert first != second
