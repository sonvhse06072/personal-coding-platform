from __future__ import annotations

from copy import deepcopy

import pytest
from pydantic import ValidationError

from app.engine import RuntimeEngine
from app.work_order import WorkOrder


def contract(**overrides) -> dict:
    value = {
        "id": "WO-9",
        "objective": "Fix bounded behavior",
        "baseline_revision": "v1",
        "source_references": [{"path": "docs/requirements.md"}],
        "in_scope": ["bounded behavior"],
        "out_of_scope": ["unrelated refactor"],
        "acceptance_criteria": [{"id": "AC-1", "description": "Behavior is correct"}],
        "constraints": ["no new dependency"],
        "requested_role": "backend_developer",
        "verification": {"required_phases": ["targeted_tests"]},
        "risk": {"level": "standard", "flags": ["material_change_required"]},
        "budget": {
            "max_profile": "standard",
            "max_model_calls": 5,
            "max_repair_iterations": 1,
            "max_wall_time_minutes": 20,
            "max_changed_files": 8,
        },
        "dependencies": ["WO-8"],
    }
    value.update(overrides)
    return value


class Storage:
    def __init__(self, row: dict) -> None:
        self.rows = {row["id"]: deepcopy(row)}

    def get(self, job_id: str):
        row = self.rows.get(job_id)
        return deepcopy(row) if row else None

    def update(self, job_id: str, **fields) -> None:
        self.rows[job_id].update(deepcopy(fields))


def test_restore_rehydrates_authoritative_contract_but_keeps_analyzer_signals() -> None:
    work_order = WorkOrder.model_validate(contract())
    storage = Storage(
        {
            "id": "job1",
            "checkpoint": {"work_order": work_order.model_dump(mode="json")},
            "task": {
                "title": "drifted title",
                "description": "drifted free-form meaning",
                "task_type": "unknown",
                "semantic": {"risk": 1, "architecture_impact": 77},
                "flags": ["security_boundary_change"],
            },
        }
    )
    engine = RuntimeEngine(storage)

    engine._restore_work_order_task("job1")

    restored = storage.rows["job1"]["task"]
    assert restored["title"] == "Fix bounded behavior"
    assert "AUTHORITATIVE WORKORDER / TASK CONTRACT" in restored["description"]
    assert "drifted free-form meaning" not in restored["description"]
    assert restored["task_type"] == "backend_developer"
    assert restored["semantic"]["risk"] == 40
    assert restored["semantic"]["architecture_impact"] == 77
    assert restored["flags"] == ["material_change_required", "security_boundary_change"]


def test_restore_keeps_work_order_semantic_floor_and_higher_analyzer_signal() -> None:
    work_order = WorkOrder.model_validate(contract())
    storage = Storage(
        {
            "id": "job-routing-floor",
            "checkpoint": {"work_order": work_order.model_dump(mode="json")},
            "task": {
                "title": "temporary",
                "semantic": {
                    "reasoning_requirement": 10,
                    "verification_difficulty": 88,
                },
            },
        }
    )
    engine = RuntimeEngine(storage)

    engine._restore_work_order_task("job-routing-floor")

    semantic = storage.rows["job-routing-floor"]["task"]["semantic"]
    assert semantic["reasoning_requirement"] == 40
    assert semantic["verification_difficulty"] == 88
    assert semantic["risk"] == 40


def test_dependency_ids_and_scope_must_be_unambiguous() -> None:
    with pytest.raises(ValidationError, match="Invalid WorkOrder dependency id"):
        WorkOrder.model_validate(contract(dependencies=["not a valid id"]))

    with pytest.raises(ValidationError, match="scope is contradictory"):
        WorkOrder.model_validate(
            contract(in_scope=["same item"], out_of_scope=["same item"])
        )
