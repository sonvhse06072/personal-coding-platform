from __future__ import annotations

from copy import deepcopy

import pytest

from app.control_actions_attention import ControlActionService


class FakeStorage:
    def __init__(self, job):
        self.job = deepcopy(job)

    def get(self, job_id):
        assert job_id == "job-1"
        return deepcopy(self.job)


def token_overrun_job(status: str):
    return {
        "id": "job-1",
        "status": status,
        "route": {
            "strategy": {
                "budget": {
                    "max_input_tokens": 2_000_000,
                }
            }
        },
        "progress": {"input_tokens": 2_274_574},
        "checkpoint": {},
        "result": {
            "reason": "reassessment_stopped",
            "reassess": {
                "action": "stop",
                "reason": "input-token budget exceeded",
                "signals": ["hard_budget_overrun"],
            },
        },
    }


def test_input_token_owner_recovery_requires_live_blocked_job_immediately_before_mutation():
    current = token_overrun_job("executing")
    controls = ControlActionService(FakeStorage(current), object(), object())

    assert controls._input_token_budget_block(current) is False
    with pytest.raises(RuntimeError, match="live blocked state"):
        controls._apply_budget_extension(
            {
                "action_id": "stale-after-resume",
                "job_id": "job-1",
                "payload": {
                    "dimension": "max_input_tokens",
                    "increment": 1_000_000,
                },
            }
        )
