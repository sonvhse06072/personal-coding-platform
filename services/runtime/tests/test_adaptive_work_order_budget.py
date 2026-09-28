import pytest

from app.work_order import (
    WorkOrder,
    WorkOrderBudget,
    WorkOrderPolicyError,
    apply_work_order_budget,
)


def work_order_payload(*, mode=None):
    budget = {
        "max_profile": "standard",
        "max_model_calls": 5,
        "max_repair_iterations": 1,
        "max_wall_time_minutes": 15,
        "max_changed_files": 6,
    }
    if mode is not None:
        budget["mode"] = mode
    return {
        "id": "T-1",
        "parent_ticket": "GH-1",
        "objective": "Make one bounded change",
        "baseline_revision": "mvp-v1",
        "source_references": [{"path": "docs/project/constitution.md"}],
        "in_scope": ["bounded change"],
        "out_of_scope": ["production deployment"],
        "acceptance_criteria": [{"id": "AC1", "description": "Checks pass"}],
        "constraints": [],
        "requested_role": "developer",
        "verification": {"required_phases": ["targeted_tests"]},
        "risk": {"level": "standard", "flags": []},
        "budget": budget,
        "dependencies": [],
    }


def route_payload():
    return {
        "strategy": {
            "profile": "standard",
            "budget_mode": "adaptive",
            "budget": {
                "max_model_calls": 18,
                "max_tool_calls": 120,
                "max_iterations": 10,
                "max_repair_iterations": 6,
                "max_test_runs": 12,
                "max_wall_time_minutes": 80,
                "max_changed_files": 14,
            },
            "adaptive_budget": {
                "enabled": True,
                "effort_pressure": 0.5,
                "dimensions": {
                    "max_model_calls": {
                        "estimate": 8,
                        "working_target": 10,
                        "emergency_limit": 18,
                    },
                    "max_tool_calls": {
                        "estimate": 60,
                        "working_target": 80,
                        "emergency_limit": 120,
                    },
                    "max_iterations": {
                        "estimate": 5,
                        "working_target": 7,
                        "emergency_limit": 10,
                    },
                    "max_repair_iterations": {
                        "estimate": 2,
                        "working_target": 3,
                        "emergency_limit": 6,
                    },
                    "max_test_runs": {
                        "estimate": 6,
                        "working_target": 8,
                        "emergency_limit": 12,
                    },
                    "max_wall_time_minutes": {
                        "estimate": 30,
                        "working_target": 45,
                        "emergency_limit": 80,
                    },
                    "max_changed_files": {
                        "estimate": 10,
                        "working_target": 14,
                        "emergency_limit": 90,
                    },
                },
            },
        }
    }


def test_budget_mode_is_required_in_new_json_schema():
    schema = WorkOrderBudget.model_json_schema()
    assert "mode" in schema["required"]
    assert "adaptive" in schema["properties"]["mode"]["enum"]


def test_pre_adaptive_work_order_payload_stays_legacy_hard():
    work_order = WorkOrder.model_validate(work_order_payload())
    assert work_order.budget.mode == "legacy_hard"

    bounded = apply_work_order_budget(route_payload(), work_order)
    budget = bounded["strategy"]["budget"]
    assert bounded["strategy"]["budget_mode"] == "legacy_hard"
    assert budget["max_model_calls"] == 5
    assert budget["max_repair_iterations"] == 1
    assert budget["max_wall_time_minutes"] == 15
    assert budget["max_changed_files"] == 6


def test_explicit_adaptive_work_order_does_not_turn_estimates_into_hard_stops():
    work_order = WorkOrder.model_validate(work_order_payload(mode="adaptive"))
    bounded = apply_work_order_budget(route_payload(), work_order)
    budget = bounded["strategy"]["budget"]

    assert bounded["strategy"]["budget_mode"] == "adaptive"
    # Adaptive execution keeps bounded emergency headroom. The WorkOrder file
    # value is the changed-file working target, not an immediate hard stop.
    assert budget["max_model_calls"] == 18
    assert budget["max_tool_calls"] == 120
    assert budget["max_iterations"] == 10
    assert budget["max_repair_iterations"] == 6
    assert budget["max_test_runs"] == 12
    assert budget["max_wall_time_minutes"] == 80
    assert budget["max_changed_files"] == 12
    envelope = bounded["strategy"]["adaptive_budget"]["dimensions"]["max_changed_files"]
    assert envelope["working_target"] == 6.0
    assert envelope["emergency_limit"] == 12.0


def test_adaptive_mode_reconciles_effective_budget_to_advertised_emergency_limits():
    work_order = WorkOrder.model_validate(work_order_payload(mode="adaptive"))
    route = route_payload()

    # Reproduce the live DEC-025C version-skew shape: Router metadata advertises
    # healthy adaptive headroom while selected effective fields still carry the
    # persisted legacy ceiling.
    route["strategy"]["budget"].update(
        {
            "max_model_calls": 22,
            "max_tool_calls": 305,
            "max_iterations": 18,
            "max_repair_iterations": 5,
            "max_test_runs": 29,
            "max_wall_time_minutes": 110,
        }
    )
    dimensions = route["strategy"]["adaptive_budget"]["dimensions"]
    dimensions.update(
        {
            "max_model_calls": {
                "estimate": 16,
                "working_target": 20,
                "emergency_limit": 30,
            },
            "max_tool_calls": {
                "estimate": 162,
                "working_target": 203,
                "emergency_limit": 305,
            },
            "max_iterations": {
                "estimate": 9,
                "working_target": 12,
                "emergency_limit": 18,
            },
            "max_repair_iterations": {
                "estimate": 5,
                "working_target": 7,
                "emergency_limit": 11,
            },
            "max_test_runs": {
                "estimate": 15,
                "working_target": 19,
                "emergency_limit": 29,
            },
            "max_wall_time_minutes": {
                "estimate": 61,
                "working_target": 77,
                "emergency_limit": 116,
            },
        }
    )

    bounded = apply_work_order_budget(route, work_order)
    budget = bounded["strategy"]["budget"]

    assert budget["max_model_calls"] == 30
    assert budget["max_tool_calls"] == 305
    assert budget["max_iterations"] == 18
    assert budget["max_repair_iterations"] == 11
    assert budget["max_test_runs"] == 29
    assert budget["max_wall_time_minutes"] == 116
    assert budget["max_changed_files"] == 12


def test_adaptive_mode_fails_closed_if_router_has_no_adaptive_metadata():
    work_order = WorkOrder.model_validate(work_order_payload(mode="adaptive"))
    route = route_payload()
    route["strategy"].pop("adaptive_budget")
    bounded = apply_work_order_budget(route, work_order)
    budget = bounded["strategy"]["budget"]
    assert bounded["strategy"]["budget_mode"] == "legacy_hard"
    assert budget["max_model_calls"] == 5
    assert budget["max_repair_iterations"] == 1
    assert budget["max_wall_time_minutes"] == 15


def test_adaptive_mode_fails_closed_if_enabled_metadata_omits_a_dimension():
    work_order = WorkOrder.model_validate(work_order_payload(mode="adaptive"))
    route = route_payload()
    del route["strategy"]["adaptive_budget"]["dimensions"]["max_model_calls"]

    with pytest.raises(WorkOrderPolicyError, match="missing envelope"):
        apply_work_order_budget(route, work_order)


def test_adaptive_mode_never_widens_above_advertised_emergency_limit():
    work_order = WorkOrder.model_validate(work_order_payload(mode="adaptive"))
    route = route_payload()
    route["strategy"]["budget"]["max_model_calls"] = 19

    with pytest.raises(WorkOrderPolicyError, match="exceeds its advertised emergency limit"):
        apply_work_order_budget(route, work_order)


def test_adaptive_mode_rejects_non_monotonic_envelope():
    work_order = WorkOrder.model_validate(work_order_payload(mode="adaptive"))
    route = route_payload()
    route["strategy"]["adaptive_budget"]["dimensions"]["max_test_runs"] = {
        "estimate": 10,
        "working_target": 9,
        "emergency_limit": 12,
    }

    with pytest.raises(WorkOrderPolicyError, match="not monotonic"):
        apply_work_order_budget(route, work_order)


def test_adaptive_changed_file_envelope_fails_closed_when_router_metadata_is_old():
    work_order = WorkOrder.model_validate(work_order_payload(mode="adaptive"))
    route = route_payload()
    del route["strategy"]["adaptive_budget"]["dimensions"]["max_changed_files"]

    bounded = apply_work_order_budget(route, work_order)

    assert bounded["strategy"]["budget_mode"] == "adaptive"
    assert bounded["strategy"]["budget"]["max_changed_files"] == 6
