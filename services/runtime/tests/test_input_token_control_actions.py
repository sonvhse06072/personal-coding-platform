from __future__ import annotations

import asyncio
from copy import deepcopy
from unittest.mock import AsyncMock

import pytest

from app.control_actions_attention import ControlActionService
from app.engine_telemetry import _apply_input_token_owner_authorizations


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


def live_job(
    *,
    input_tokens=2_274_574,
    max_input_tokens=2_000_000,
    reason="reassessment_stopped",
    reassess_reason="input-token budget exceeded",
    signals=None,
    last_failure="",
    budget_mode=None,
):
    result = {"reason": reason}
    if reason == "reassessment_stopped":
        result["reassess"] = {
            "action": "stop",
            "reason": reassess_reason,
            "signals": list(signals or ["hard_budget_overrun"]),
        }
    elif last_failure:
        result["last_failure"] = last_failure

    return {
        "id": "job-1",
        "project_id": "chonhac",
        "status": "blocked",
        "source_commit": "b143fbb001c2006ec82570619802b607085fbeb0",
        "branch": "ai/eec59b13651c",
        "workspace": "/home/sonvh/.coding-platform/workspaces/eec59b13651c54559c10ce204380a68e",
        "updated_at": "2026-09-17T06:00:00+00:00",
        "route": {
            "strategy": {
                "budget_mode": budget_mode,
                "budget": {
                    "max_model_calls": 30,
                    "max_input_tokens": max_input_tokens,
                    "max_output_tokens": 200_000,
                    "max_tool_calls": 200,
                    "max_test_runs": 20,
                    "max_wall_time_minutes": 140,
                    "max_repair_iterations": 8,
                    "max_iterations": 12,
                }
            }
        },
        "progress": {
            "model_calls": 24,
            "input_tokens": input_tokens,
            "output_tokens": 81_000,
            "tool_calls": 83,
            "test_runs": 17,
            "elapsed_minutes": 103.5,
            "repair_iterations": 5,
            "iteration": 7,
            "provider_failures": [],
        },
        "checkpoint": {
            "work_order": {
                "id": "DEC-025C-1-recovery-tooling-r2",
                "budget": {"mode": "legacy_hard"},
            },
            "route_history": [],
        },
        "result": result,
    }


def work_order_row():
    return {
        "plan_id": "pm-gh-5650852312",
        "work_order_id": "DEC-025C-1-recovery-tooling-r2",
        "execution_mode": "agent",
        "state": "blocked",
        "job_id": "job-1",
        "updated_at": "2026-09-17T06:00:00+00:00",
    }


def service(job):
    storage = FakeStorage(job)
    return ControlActionService(storage, FakeEngine(), FakeStore()), storage


def mutating_actions(advisory):
    return [
        item
        for item in advisory["action_specs"]
        if item.get("action_type") not in {"details", "keep_blocked"}
    ]


def test_live_dec025c_overrun_exposes_exact_bounded_input_token_recovery():
    current = live_job()
    controls, _ = service(current)

    advisory = controls.blocked_advisory(work_order_row(), current)

    assert advisory["reason"] == "reassessment_stopped"
    assert advisory["metrics"][0] == {
        "key": "max_input_tokens",
        "label": "Input token",
        "used": 2_274_574,
        "limit": 2_000_000,
    }
    assert mutating_actions(advisory) == [
        {
            "action_type": "budget_extend",
            "label": "➕ +1.000.000 input token",
            "payload": {
                "dimension": "max_input_tokens",
                "increment": 1_000_000,
            },
        }
    ]
    assert [item["action_type"] for item in advisory["action_specs"]] == [
        "budget_extend",
        "details",
        "keep_blocked",
    ]


def test_adaptive_dec_token_overrun_exposes_no_owner_token_extension():
    current = live_job(
        input_tokens=8_072_466,
        max_input_tokens=8_000_000,
        budget_mode="adaptive",
    )
    controls, _ = service(current)

    advisory = controls.blocked_advisory(work_order_row(), current)

    assert all(
        item.get("payload", {}).get("dimension") != "max_input_tokens"
        for item in advisory["action_specs"]
    )
    assert all("4.000.000" not in str(value) for value in advisory.values())


def test_direct_input_token_exhaustion_maps_to_same_recovery_dimension():
    current = live_job(
        input_tokens=2_000_000,
        reason="execution_budget_exhausted",
        last_failure="input-token budget exhausted",
    )
    controls, _ = service(current)

    advisory = controls.blocked_advisory(work_order_row(), current)

    action = mutating_actions(advisory)[0]
    assert action["payload"] == {
        "dimension": "max_input_tokens",
        "increment": 1_000_000,
    }


def test_input_token_extension_preserves_identity_usage_and_uses_existing_resume_path():
    current = live_job()
    controls, storage = service(current)
    controls._resume = AsyncMock(return_value={"id": "job-1", "status": "queued"})
    before = storage.get("job-1")

    result = asyncio.run(
        controls._dispatch(
            {
                "action_id": "input-token-owner-action",
                "action_type": "budget_extend",
                "job_id": "job-1",
                "payload": {
                    "dimension": "max_input_tokens",
                    "increment": 1_000_000,
                },
            }
        )
    )
    after = storage.get("job-1")

    assert after["route"]["strategy"]["budget"]["max_input_tokens"] == 3_000_000
    assert after["progress"] == before["progress"]
    assert after["source_commit"] == before["source_commit"]
    assert after["workspace"] == before["workspace"]
    assert after["branch"] == before["branch"]
    assert after["checkpoint"]["work_order"] == before["checkpoint"]["work_order"]
    authorization = after["checkpoint"]["budget_authorizations"][-1]
    assert authorization["dimension"] == "max_input_tokens"
    assert authorization["previous_limit"] == 2_000_000
    assert authorization["new_limit"] == 3_000_000
    assert authorization["used"] == 2_274_574
    assert result["budget_authorization"]["new_limit"] == 3_000_000
    controls._resume.assert_awaited_once_with(
        "job-1",
        reset_transient_provider_failures=False,
        reroute=False,
    )


def test_second_live_authorization_can_advance_only_to_four_million():
    current = live_job(input_tokens=3_274_574, max_input_tokens=3_000_000)
    controls, storage = service(current)

    result = controls._apply_budget_extension(
        {
            "action_id": "second-input-token-owner-action",
            "job_id": "job-1",
            "payload": {
                "dimension": "max_input_tokens",
                "increment": 1_000_000,
            },
        }
    )

    assert result == {
        "dimension": "max_input_tokens",
        "previous_limit": 3_000_000,
        "new_limit": 4_000_000,
        "used": 3_274_574,
    }
    assert storage.get("job-1")["route"]["strategy"]["budget"]["max_input_tokens"] == 4_000_000


def test_hard_max_exposes_no_mutating_recovery_and_execution_fails_closed():
    current = live_job(input_tokens=4_000_000, max_input_tokens=4_000_000)
    controls, _ = service(current)

    advisory = controls.blocked_advisory(work_order_row(), current)

    assert mutating_actions(advisory) == []
    assert [item["action_type"] for item in advisory["action_specs"]] == [
        "details",
        "keep_blocked",
    ]
    with pytest.raises(RuntimeError, match="hard maximum"):
        controls._apply_budget_extension(
            {
                "action_id": "too-far",
                "job_id": "job-1",
                "payload": {
                    "dimension": "max_input_tokens",
                    "increment": 1_000_000,
                },
            }
        )


def test_extension_is_not_offered_when_one_increment_cannot_restore_headroom():
    current = live_job(input_tokens=4_200_000, max_input_tokens=3_000_000)
    controls, _ = service(current)

    advisory = controls.blocked_advisory(work_order_row(), current)

    assert mutating_actions(advisory) == []
    with pytest.raises(RuntimeError, match="hard maximum"):
        controls._apply_budget_extension(
            {
                "action_id": "insufficient-headroom",
                "job_id": "job-1",
                "payload": {
                    "dimension": "max_input_tokens",
                    "increment": 1_000_000,
                },
            }
        )


def test_stale_token_reason_without_live_exhaustion_fails_closed():
    current = live_job(input_tokens=1_900_000, max_input_tokens=2_000_000)
    controls, _ = service(current)

    advisory = controls.blocked_advisory(work_order_row(), current)

    assert all(
        item.get("payload", {}).get("dimension") != "max_input_tokens"
        for item in advisory["action_specs"]
    )
    with pytest.raises(RuntimeError, match="no longer matches"):
        controls._apply_budget_extension(
            {
                "action_id": "stale-token-action",
                "job_id": "job-1",
                "payload": {
                    "dimension": "max_input_tokens",
                    "increment": 1_000_000,
                },
            }
        )


def test_non_token_reassessment_keeps_existing_budget_recovery_behavior():
    current = live_job(
        input_tokens=1_800_000,
        reassess_reason="model-call budget exhausted",
        signals=["hard_budget_guard"],
    )
    current["progress"]["model_calls"] = 30
    controls, _ = service(current)

    advisory = controls.blocked_advisory(work_order_row(), current)

    assert mutating_actions(advisory)[0]["payload"] == {
        "dimension": "max_model_calls",
        "increment": 4,
    }
    assert all(
        item.get("payload", {}).get("dimension") != "max_input_tokens"
        for item in advisory["action_specs"]
    )


def test_input_token_authorizations_survive_fresh_route_without_mutating_route_input():
    route = {
        "strategy": {
            "budget": {
                "max_input_tokens": 2_000_000,
                "max_output_tokens": 200_000,
            }
        }
    }
    checkpoint = {
        "budget_authorizations": [
            {
                "action_id": "first",
                "channel": "telegram",
                "dimension": "max_input_tokens",
                "previous_limit": 2_000_000,
                "new_limit": 3_000_000,
                "used": 2_274_574,
            },
            {
                "action_id": "second",
                "channel": "telegram",
                "dimension": "max_input_tokens",
                "previous_limit": 3_000_000,
                "new_limit": 4_000_000,
                "used": 3_274_574,
            },
        ]
    }

    updated = _apply_input_token_owner_authorizations(route, checkpoint)

    assert route["strategy"]["budget"]["max_input_tokens"] == 2_000_000
    assert updated["strategy"]["budget"]["max_input_tokens"] == 4_000_000


def test_input_token_reroute_overlay_clamps_untrusted_authorization_to_hard_max():
    route = {"strategy": {"budget": {"max_input_tokens": 2_000_000}}}
    checkpoint = {
        "budget_authorizations": [
            {
                "action_id": "unexpected",
                "channel": "telegram",
                "dimension": "max_input_tokens",
                "previous_limit": 2_000_000,
                "new_limit": 9_000_000,
            }
        ]
    }

    updated = _apply_input_token_owner_authorizations(route, checkpoint)

    assert updated["strategy"]["budget"]["max_input_tokens"] == 4_000_000
