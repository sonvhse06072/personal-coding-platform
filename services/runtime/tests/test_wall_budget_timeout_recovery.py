from __future__ import annotations

from copy import deepcopy

import pytest

from app.engine import RuntimeEngine
from app.shell import CommandTimeoutError


class FakeStorage:
    def __init__(self, row):
        self.rows = {row["id"]: deepcopy(row)}

    def get(self, job_id):
        value = self.rows.get(job_id)
        return deepcopy(value) if value else None

    def update(self, job_id, **fields):
        self.rows[job_id].update(deepcopy(fields))


def row(*, status: str, elapsed_minutes: float, wall_limit: float = 70.0, budget_mode: str | None = None):
    return {
        "id": "job-1",
        "status": status,
        "route": {
            "strategy": {
                "budget_mode": budget_mode,
                "budget": {"max_wall_time_minutes": wall_limit},
            }
        },
        "progress": {
            "elapsed_minutes": elapsed_minutes,
            "model_calls": 10,
            "tool_calls": 20,
            "test_runs": 4,
            "repair_iterations": 1,
            "iteration": 4,
            "provider_failures": [],
            "agent_attempts": [],
        },
        "checkpoint": {"route_history": []},
        "result": None,
        "error": None,
    }


@pytest.mark.parametrize(
    ("status", "timeout", "expected_reason"),
    [
        ("planning", 1500, "planner_budget_exhausted"),
        ("executing", 390, "execution_budget_exhausted"),
        ("evaluating", 900, "execution_budget_exhausted"),
    ],
)
def test_wall_budget_bounded_agent_timeout_becomes_recoverable_block(
    status: str,
    timeout: int,
    expected_reason: str,
):
    current = row(status=status, elapsed_minutes=70 - timeout / 60)
    storage = FakeStorage(current)
    engine = RuntimeEngine(storage)

    handled = engine._block_wall_budget_command_timeout(
        "job-1",
        CommandTimeoutError(timeout=timeout, argv=["agent", "run"]),
    )

    updated = storage.get("job-1")
    assert handled is True
    assert updated["status"] == "blocked"
    assert updated["result"]["reason"] == expected_reason
    assert updated["result"]["last_failure"] == "wall-time budget exhausted"
    assert updated["progress"]["elapsed_minutes"] >= 70.0
    assert updated["error"] is None


def test_per_call_timeout_with_wall_time_remaining_is_not_reclassified():
    current = row(status="executing", elapsed_minutes=20.0)
    storage = FakeStorage(current)
    engine = RuntimeEngine(storage)

    handled = engine._block_wall_budget_command_timeout(
        "job-1",
        CommandTimeoutError(timeout=2400, argv=["agent", "run"]),
    )

    assert handled is False
    assert storage.get("job-1")["status"] == "executing"

def test_adaptive_command_timeout_is_not_reclassified_as_total_wall_budget():
    current = row(
        status="executing",
        elapsed_minutes=70.0,
        wall_limit=70.0,
        budget_mode="adaptive",
    )
    storage = FakeStorage(current)
    engine = RuntimeEngine(storage)

    handled = engine._block_wall_budget_command_timeout(
        "job-1",
        CommandTimeoutError(timeout=2400, argv=["agent", "run"]),
    )

    assert handled is False
    assert storage.get("job-1")["status"] == "executing"

