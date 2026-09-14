from __future__ import annotations

import asyncio
from copy import deepcopy

from app.control_actions_reroute import ControlActionService


class FakeStorage:
    def __init__(self, job=None):
        self.job = deepcopy(job)

    def get(self, job_id):
        if job_id != "job-1" or self.job is None:
            return None
        return deepcopy(self.job)


class Harness(ControlActionService):
    def __init__(self, job=None):
        self.calls: list[dict] = []
        self.extensions: list[dict] = []
        self.storage = FakeStorage(job)

    async def _resume(
        self,
        job_id: str,
        *,
        reset_transient_provider_failures: bool,
        reroute: bool,
    ) -> dict:
        self.calls.append(
            {
                "job_id": job_id,
                "reset_transient_provider_failures": reset_transient_provider_failures,
                "reroute": reroute,
            }
        )
        return {"id": job_id, "status": "queued"}

    def _apply_budget_extension(self, action: dict) -> dict:
        payload = deepcopy(action.get("payload") or {})
        self.extensions.append(payload)
        return {
            "dimension": payload.get("dimension"),
            "previous_limit": 90,
            "new_limit": 110,
            "used": 90.047,
        }


def action(action_type: str, payload=None) -> dict:
    return {
        "action_id": f"action-{action_type}",
        "action_type": action_type,
        "job_id": "job-1",
        "payload": deepcopy(payload or {}),
    }


def provider_wall_block() -> dict:
    return {
        "id": "job-1",
        "status": "blocked",
        "route": {
            "strategy": {
                "budget": {
                    "max_model_calls": 22,
                    "max_tool_calls": 160,
                    "max_test_runs": 14,
                    "max_wall_time_minutes": 90,
                    "max_repair_iterations": 4,
                    "max_iterations": 12,
                }
            }
        },
        "progress": {
            "model_calls": 20,
            "tool_calls": 60,
            "test_runs": 12,
            "elapsed_minutes": 90.047,
            "repair_iterations": 3,
            "iteration": 10,
            "provider_failures": [
                {
                    "model": "antigravity_free",
                    "provider": "google_antigravity",
                    "kind": "quota_exhausted",
                }
            ],
        },
        "result": {
            "reason": "evaluator_provider_failure_without_fallback",
            "last_failure": "provider quota exhausted",
        },
    }


def test_reroute_provider_preserves_failed_provider_state():
    controls = Harness()

    result = asyncio.run(controls._dispatch(action("reroute_provider")))

    assert controls.calls == [
        {
            "job_id": "job-1",
            "reset_transient_provider_failures": False,
            "reroute": True,
        }
    ]
    assert result["job_id"] == "job-1"
    assert result["job_status"] == "queued"
    assert "preserving failed-provider state" in result["message"]


def test_explicit_quota_reset_still_clears_provider_state_before_fresh_route():
    controls = Harness()

    asyncio.run(controls._dispatch(action("provider_quota_reset")))

    assert controls.calls == [
        {
            "job_id": "job-1",
            "reset_transient_provider_failures": True,
            "reroute": True,
        }
    ]


def test_resume_reroute_and_no_effect_reroute_also_preserve_provider_state():
    for action_type in ("resume_reroute", "reroute_retry"):
        controls = Harness()
        asyncio.run(controls._dispatch(action(action_type)))
        assert controls.calls[0]["reset_transient_provider_failures"] is False
        assert controls.calls[0]["reroute"] is True


def test_provider_block_with_exhausted_wall_budget_offers_only_combined_mutation():
    job = provider_wall_block()
    controls = Harness(job)

    advisory = controls.blocked_advisory({}, job)
    actions = advisory["action_specs"]
    mutation_actions = [
        item for item in actions
        if item.get("action_type") not in {"details", "keep_blocked"}
    ]

    assert controls._provider_budget_dimension(job) == "max_wall_time_minutes"
    assert len(mutation_actions) == 1
    assert mutation_actions[0]["action_type"] == "budget_extend"
    assert mutation_actions[0]["payload"] == {
        "dimension": "max_wall_time_minutes",
        "increment": 20,
    }
    assert mutation_actions[0]["label"] == "➕ +20 phút + chuyển provider"
    assert all(item.get("action_type") != "reroute_provider" for item in actions)
    assert all(item.get("action_type") != "provider_quota_reset" for item in actions)


def test_combined_budget_action_extends_then_reroutes_same_job_without_clearing_provider_state():
    controls = Harness(provider_wall_block())
    result = asyncio.run(
        controls._dispatch(
            action(
                "budget_extend",
                {"dimension": "max_wall_time_minutes", "increment": 20},
            )
        )
    )

    assert controls.extensions == [
        {"dimension": "max_wall_time_minutes", "increment": 20}
    ]
    assert controls.calls == [
        {
            "job_id": "job-1",
            "reset_transient_provider_failures": False,
            "reroute": True,
        }
    ]
    assert result["budget_authorization"]["new_limit"] == 110
    assert result["job_id"] == "job-1"
    assert "rerouted" in result["message"]
