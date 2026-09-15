from app.work_order import WorkOrder, WorkOrderBudget, apply_work_order_budget


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
            "budget": {
                "max_model_calls": 18,
                "max_repair_iterations": 6,
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
                    "max_repair_iterations": {
                        "estimate": 2,
                        "working_target": 3,
                        "emergency_limit": 6,
                    },
                    "max_wall_time_minutes": {
                        "estimate": 30,
                        "working_target": 45,
                        "emergency_limit": 80,
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
    assert budget["max_model_calls"] == 5
    assert budget["max_repair_iterations"] == 1
    assert budget["max_wall_time_minutes"] == 15
    assert budget["max_changed_files"] == 6


def test_explicit_adaptive_work_order_does_not_turn_estimates_into_hard_stops():
    work_order = WorkOrder.model_validate(work_order_payload(mode="adaptive"))
    bounded = apply_work_order_budget(route_payload(), work_order)
    budget = bounded["strategy"]["budget"]

    # Adaptive execution keeps Router's bounded emergency envelope while scope
    # and profile remain WorkOrder hard policy boundaries.
    assert budget["max_model_calls"] == 18
    assert budget["max_repair_iterations"] == 6
    assert budget["max_wall_time_minutes"] == 80
    assert budget["max_changed_files"] == 6


def test_adaptive_mode_fails_closed_if_router_has_no_adaptive_metadata():
    work_order = WorkOrder.model_validate(work_order_payload(mode="adaptive"))
    route = route_payload()
    route["strategy"].pop("adaptive_budget")
    bounded = apply_work_order_budget(route, work_order)
    budget = bounded["strategy"]["budget"]
    assert budget["max_model_calls"] == 5
    assert budget["max_repair_iterations"] == 1
    assert budget["max_wall_time_minutes"] == 15
