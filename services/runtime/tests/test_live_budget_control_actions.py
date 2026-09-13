from __future__ import annotations

from copy import deepcopy

import pytest

from app.control_actions_live import ControlActionService


class FakeStorage:
    def __init__(self, job):
        self.jobs = {"job-1": deepcopy(job)}

    def get(self, job_id):
        value = self.jobs.get(job_id)
        return deepcopy(value) if value is not None else None

    def update(self, job_id, **fields):
        self.jobs[job_id].update(deepcopy(fields))


class FakeEngine:
    pass


class FakeStore:
    pass


def job(
    *,
    last_failure="model-call budget exhausted",
    model_calls=11,
    max_model_calls=14,
    elapsed_minutes=49.144,
    max_wall_time_minutes=50,
    tool_calls=25,
    max_tool_calls=160,
):
    return {
        "id": "job-1",
        "status": "blocked",
        "route": {
            "strategy": {
                "budget": {
                    "max_model_calls": max_model_calls,
                    "max_tool_calls": max_tool_calls,
                    "max_test_runs": 14,
                    "max_wall_time_minutes": max_wall_time_minutes,
                    "max_repair_iterations": 2,
                    "max_iterations": 8,
                }
            }
        },
        "progress": {
            "model_calls": model_calls,
            "tool_calls": tool_calls,
            "test_runs": 4,
            "elapsed_minutes": elapsed_minutes,
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
            "reason": "execution_budget_exhausted",
            "last_failure": last_failure,
        },
    }


def work_order():
    return {
        "plan_id": "plan-1",
        "work_order_id": "WO-1",
        "execution_mode": "agent",
        "state": "blocked",
        "job_id": "job-1",
    }


def service(current_job):
    storage = FakeStorage(current_job)
    return ControlActionService(storage, FakeEngine(), FakeStore()), storage


def budget_actions(advisory):
    return [
        item
        for item in advisory["action_specs"]
        if item.get("action_type") == "budget_extend"
    ]


def test_stale_model_failure_yields_live_wall_time_extension_for_real_c1_shape():
    controls, _ = service(job())

    advisory = controls.blocked_advisory(work_order(), job())

    actions = budget_actions(advisory)
    assert len(actions) == 1
    assert actions[0]["payload"] == {
        "dimension": "max_wall_time_minutes",
        "increment": 20,
    }
    assert "Wall time" in actions[0]["label"]
    assert all(
        item.get("payload", {}).get("dimension") != "max_model_calls"
        for item in advisory["action_specs"]
    )
    assert "live runtime counters" in advisory["cause"].lower()


def test_old_model_extension_action_is_rejected_against_live_wall_time_state():
    controls, _ = service(job())

    with pytest.raises(RuntimeError, match="current live exhausted dimension"):
        controls._apply_budget_extension(
            {
                "action_id": "old-model-action",
                "job_id": "job-1",
                "payload": {"dimension": "max_model_calls", "increment": 4},
            }
        )


def test_exact_live_model_call_exhaustion_still_selects_model_calls():
    current = job(model_calls=14, max_model_calls=14, elapsed_minutes=30)
    controls, _ = service(current)

    advisory = controls.blocked_advisory(work_order(), current)

    actions = budget_actions(advisory)
    assert len(actions) == 1
    assert actions[0]["payload"] == {
        "dimension": "max_model_calls",
        "increment": 4,
    }


def test_live_wall_time_extension_is_additive_and_preserves_usage():
    current = job()
    controls, storage = service(current)
    before = storage.get("job-1")

    result = controls._apply_budget_extension(
        {
            "action_id": "wall-action",
            "job_id": "job-1",
            "payload": {"dimension": "max_wall_time_minutes", "increment": 20},
        }
    )
    after = storage.get("job-1")

    assert result["previous_limit"] == 50.0
    assert result["new_limit"] == 70.0
    assert result["used"] == 49.144
    assert after["progress"] == before["progress"]
    assert after["checkpoint"]["work_order"] == before["checkpoint"]["work_order"]
    assert after["route"]["strategy"]["budget"]["max_wall_time_minutes"] == 70.0


def test_stale_hint_without_live_exhaustion_fails_closed():
    current = job(elapsed_minutes=40, model_calls=11, max_model_calls=14)
    controls, _ = service(current)

    advisory = controls.blocked_advisory(work_order(), current)

    assert budget_actions(advisory) == []
    assert "do not identify one safe extension dimension" in advisory["cause"].lower()
    assert [item["action_type"] for item in advisory["action_specs"]] == [
        "details",
        "keep_blocked",
    ]


def test_multiple_live_exhausted_dimensions_without_matching_hint_fail_closed():
    current = job(
        last_failure="unknown budget failure",
        model_calls=14,
        max_model_calls=14,
        tool_calls=160,
        max_tool_calls=160,
        elapsed_minutes=30,
    )
    controls, _ = service(current)

    advisory = controls.blocked_advisory(work_order(), current)

    assert budget_actions(advisory) == []
    assert [item["action_type"] for item in advisory["action_specs"]] == [
        "details",
        "keep_blocked",
    ]
