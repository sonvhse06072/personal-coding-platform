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


def c1_reassessment_job():
    return {
        "id": "job-1",
        "status": "blocked",
        "updated_at": "2026-09-14T09:00:00+00:00",
        "route": {
            "strategy": {
                "budget": {
                    "max_model_calls": 14,
                    "max_tool_calls": 160,
                    "max_test_runs": 14,
                    "max_wall_time_minutes": 70,
                    "max_repair_iterations": 2,
                    "max_iterations": 8,
                }
            }
        },
        "progress": {
            "model_calls": 14,
            "tool_calls": 30,
            "test_runs": 6,
            "elapsed_minutes": 61.97,
            "repair_iterations": 2,
            "iteration": 8,
            "provider_failures": [],
        },
        "checkpoint": {
            "work_order": {
                "id": "DEC-025C-1-recovery-tooling-r2",
                "budget": {
                    "max_model_calls": 10,
                    "max_repair_iterations": 2,
                    "max_wall_time_minutes": 50,
                },
            },
            "route_history": [],
        },
        "result": {
            "reason": "reassessment_stopped",
            "last_failure": "Evaluator failed: sanitized failure summary",
            "reassess": {
                "action": "stop",
                "reason": "model-call budget exhausted",
                "signals": ["hard_budget_guard"],
                "remaining": {
                    "model_calls": 0,
                    "repair_iterations": 0,
                    "iterations": 0,
                    "wall_time_minutes": 8.03,
                },
            },
        },
    }


def work_order(*, execution_mode="agent"):
    return {
        "plan_id": "plan-1",
        "work_order_id": "DEC-025C-1-recovery-tooling-r2",
        "execution_mode": execution_mode,
        "state": "blocked" if execution_mode == "agent" else "waiting_human",
        "job_id": "job-1" if execution_mode == "agent" else None,
        "updated_at": "2026-09-14T09:00:00+00:00",
    }


def service(job=None):
    storage = FakeStorage(job or c1_reassessment_job())
    return ControlActionService(storage, FakeEngine(), FakeStore()), storage


def test_reassessment_hard_budget_guard_offers_only_current_model_extension_first():
    job = c1_reassessment_job()
    controls, _ = service(job)

    advisory = controls.blocked_advisory(work_order(), job)
    extensions = [item for item in advisory["action_specs"] if item["action_type"] == "budget_extend"]

    assert advisory["title"] == "WORKORDER BỊ CHẶN"
    assert "Definition of Done" in advisory["summary"]
    assert "hard_budget_guard" in advisory["cause"]
    assert extensions == [{
        "action_type": "budget_extend",
        "label": "➕ +4 lượt gọi model",
        "payload": {"dimension": "max_model_calls", "increment": 4},
    }]
    assert not any(item["action_type"] == "force_complete" for item in advisory["action_specs"])


def test_reassessment_budget_extension_is_revalidated_and_preserves_usage():
    controls, storage = service()
    before = storage.get("job-1")

    result = controls._apply_budget_extension({
        "action_id": "opaque-c1-action",
        "job_id": "job-1",
        "payload": {"dimension": "max_model_calls", "increment": 4},
    })
    after = storage.get("job-1")

    assert result == {
        "dimension": "max_model_calls",
        "previous_limit": 14,
        "new_limit": 18,
        "used": 14,
    }
    assert after["route"]["strategy"]["budget"]["max_model_calls"] == 18
    assert after["progress"] == before["progress"]
    assert after["checkpoint"]["work_order"] == before["checkpoint"]["work_order"]
    assert after["checkpoint"]["budget_authorizations"][-1]["action_id"] == "opaque-c1-action"


def test_reassessment_without_structured_hard_budget_guard_stays_fail_closed():
    job = c1_reassessment_job()
    job["result"]["reassess"] = {
        "action": "stop",
        "reason": "model-call budget exhausted",
        "signals": ["decision_boundary"],
    }
    controls, _ = service(job)

    advisory = controls.blocked_advisory(work_order(), job)

    assert not any(item["action_type"] == "budget_extend" for item in advisory["action_specs"])
    with pytest.raises(RuntimeError, match="no longer matches"):
        controls._apply_budget_extension({
            "action_id": "stale-action",
            "job_id": "job-1",
            "payload": {"dimension": "max_model_calls", "increment": 4},
        })


def test_budget_action_rejects_wrong_live_dimension_even_with_valid_reassessment_guard():
    controls, _ = service()

    with pytest.raises(RuntimeError, match="stale or does not match"):
        controls._apply_budget_extension({
            "action_id": "wrong-dimension",
            "job_id": "job-1",
            "payload": {"dimension": "max_repair_iterations", "increment": 1},
        })


def test_owner_attention_advisories_and_action_labels_are_vietnamese():
    controls, _ = service()

    operator = controls.waiting_human_advisory(work_order(execution_mode="operator"), None)
    assert operator["title"] == "CẦN OPERATOR THỰC HIỆN"
    assert operator["action_specs"][0]["label"] == "✅ Đánh dấu hoàn tất"
    assert operator["action_specs"][1]["label"] == "⛔ Đánh dấu bị chặn"

    merge = controls.manual_merge_advisory("https://github.com/example/repo/pull/1")
    assert merge["title"] == "CẦN MERGE THỦ CÔNG"
    assert merge["action_specs"][0]["label"] == "🔗 Mở PR"
    assert "merge thủ công" in merge["recommended"]
