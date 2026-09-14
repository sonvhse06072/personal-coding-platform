from __future__ import annotations

import asyncio
from copy import deepcopy

import pytest

from app.control_actions_live import ControlActionService as LiveControlActionService
from app.control_actions_reroute import ControlActionService


class FakeStorage:
    def __init__(self, job=None):
        self.job = deepcopy(job)

    def get(self, job_id):
        if job_id != "job-1" or self.job is None:
            return None
        return deepcopy(self.job)

    def update(self, job_id, **changes):
        if job_id != "job-1" or self.job is None:
            raise RuntimeError("Unknown job")
        self.job.update(deepcopy(changes))


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
        "checkpoint": {},
        "result": {
            "reason": "evaluator_provider_failure_without_fallback",
            "last_failure": "provider quota exhausted",
        },
    }


def provider_multi_budget_block() -> dict:
    job = provider_wall_block()
    job["status"] = "failed"
    job["error"] = "RuntimeError: Job wall-time budget exhausted before next operation"
    job["progress"]["iteration"] = 12
    return job


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

    assert controls._provider_budget_dimensions(job) == ["max_wall_time_minutes"]
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


def test_provider_block_with_wall_and_iteration_exhaustion_offers_one_atomic_bundle():
    job = provider_multi_budget_block()
    controls = Harness(job)

    advisory = controls.blocked_advisory({}, job)
    actions = advisory["action_specs"]
    mutation_actions = [
        item for item in actions
        if item.get("action_type") not in {"details", "keep_blocked"}
    ]

    assert controls._provider_budget_dimensions(job) == [
        "max_wall_time_minutes",
        "max_iterations",
    ]
    assert controls._provider_budget_dimension(job) is None
    assert len(mutation_actions) == 1
    assert mutation_actions[0] == {
        "action_type": "budget_extend_bundle",
        "label": "➕ +20 phút, +2 vòng lặp + chuyển provider",
        "payload": {
            "extensions": [
                {"dimension": "max_wall_time_minutes", "increment": 20},
                {"dimension": "max_iterations", "increment": 2},
            ]
        },
    }
    metric_keys = {
        item.get("key") for item in advisory.get("metrics") or []
        if isinstance(item, dict)
    }
    assert "max_wall_time_minutes" in metric_keys
    assert "max_iterations" in metric_keys


def test_provider_budget_recovery_revision_invalidates_old_action_fingerprint():
    controls = Harness(provider_multi_budget_block())
    job = provider_multi_budget_block()
    plan = {"plan_id": "plan-1", "status": "blocked", "updated_at": "plan-v1"}
    work_order = {
        "work_order_id": "wo-1",
        "state": "blocked",
        "updated_at": "wo-v1",
    }

    legacy = LiveControlActionService.state_fingerprint(
        controls,
        plan,
        work_order,
        job,
    )
    current = controls.state_fingerprint(plan, work_order, job)

    assert current != legacy

    no_budget_job = provider_wall_block()
    no_budget_job["progress"]["elapsed_minutes"] = 80
    assert controls._provider_budget_dimensions(no_budget_job) == []
    assert controls.state_fingerprint(plan, work_order, no_budget_job) == (
        LiveControlActionService.state_fingerprint(
            controls,
            plan,
            work_order,
            no_budget_job,
        )
    )


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


def test_multi_budget_bundle_updates_all_limits_once_then_reroutes_once():
    controls = Harness(provider_multi_budget_block())
    result = asyncio.run(
        controls._dispatch(
            action(
                "budget_extend_bundle",
                {
                    "extensions": [
                        {"dimension": "max_wall_time_minutes", "increment": 20},
                        {"dimension": "max_iterations", "increment": 2},
                    ]
                },
            )
        )
    )

    budget = controls.storage.job["route"]["strategy"]["budget"]
    assert budget["max_wall_time_minutes"] == 110
    assert budget["max_iterations"] == 14
    authorizations = controls.storage.job["checkpoint"]["budget_authorizations"]
    assert [item["dimension"] for item in authorizations] == [
        "max_wall_time_minutes",
        "max_iterations",
    ]
    assert all(item["action_id"] == "action-budget_extend_bundle" for item in authorizations)
    assert all(item["bundle"] is True for item in authorizations)
    assert controls.calls == [
        {
            "job_id": "job-1",
            "reset_transient_provider_failures": False,
            "reroute": True,
        }
    ]
    assert len(result["budget_authorizations"]) == 2
    assert "atomically" in result["message"]


def test_multi_budget_bundle_rejects_stale_dimension_set_before_resume():
    controls = Harness(provider_multi_budget_block())
    before = deepcopy(controls.storage.job["route"])

    with pytest.raises(RuntimeError, match="no longer matches live exhausted dimensions"):
        asyncio.run(
            controls._dispatch(
                action(
                    "budget_extend_bundle",
                    {
                        "extensions": [
                            {"dimension": "max_wall_time_minutes", "increment": 20},
                            {"dimension": "max_repair_iterations", "increment": 1},
                        ]
                    },
                )
            )
        )

    assert controls.storage.job["route"] == before
    assert controls.calls == []
