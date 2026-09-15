from __future__ import annotations

from copy import deepcopy

from app.telemetry import (
    aggregate_calibration,
    classify_attention_event,
    classify_budget_attention,
    task_telemetry_snapshot,
)


def completed_row() -> dict:
    return {
        "id": "job-telemetry-1",
        "project_id": "project-a",
        "status": "completed",
        "task": {"title": "Add test", "task_type": "test"},
        "checkpoint": {
            "work_order": {"id": "WO-1", "requested_role": "backend_developer"},
            "executor_choice": {
                "id": "codex_terra",
                "provider": "openai",
                "adapter": "codex_cli",
            },
        },
        "route": {
            "strategy": {
                "profile": "standard",
                "executor": {"id": "codex_terra", "provider": "openai"},
                "budget": {
                    "max_model_calls": 12,
                    "max_tool_calls": 100,
                    "max_iterations": 8,
                    "max_repair_iterations": 4,
                    "max_test_runs": 12,
                    "max_wall_time_minutes": 45,
                },
                "adaptive_budget": {
                    "enabled": True,
                    "dimensions": {
                        "max_model_calls": {"estimate": 6, "working_target": 8, "emergency_limit": 12},
                        "max_tool_calls": {"estimate": 40, "working_target": 60, "emergency_limit": 100},
                        "max_iterations": {"estimate": 4, "working_target": 6, "emergency_limit": 8},
                        "max_repair_iterations": {"estimate": 2, "working_target": 3, "emergency_limit": 4},
                        "max_test_runs": {"estimate": 6, "working_target": 8, "emergency_limit": 12},
                        "max_wall_time_minutes": {"estimate": 20, "working_target": 30, "emergency_limit": 45},
                    },
                },
            }
        },
        "progress": {
            "iteration": 1,
            "repair_iterations": 0,
            "verification_attempts": 1,
            "verification_retry_attempts": 0,
            "ci_failures": 0,
            "model_calls": 4,
            "tool_calls": 18,
            "test_runs": 4,
            "elapsed_minutes": 12.5,
            "input_tokens": 12000,
            "output_tokens": 2200,
            "cost_usd": 0.4,
            "review_runs": 1,
            "review_findings": 2,
            "review_findings_actioned": 1,
            "review_useful_finding_yield": 0.5,
            "review_input_tokens": 800,
            "review_output_tokens": 150,
            "review_cost_usd": 0.03,
            "provider_failures": [
                {"model": "codex_terra", "provider": "openai", "kind": "rate_limited"}
            ],
        },
        "result": {
            "status": "accepted",
            "verification": {
                "passed": True,
                "phases": [
                    {"phase": "targeted_tests", "verification_layer": "intermediate", "passed": True},
                    {"phase": "full_tests", "verification_layer": "final", "passed": True},
                ],
            },
            "delivery": {"enabled": True, "state": "ci_success"},
        },
    }


def test_task_snapshot_captures_outcome_verification_review_and_resources() -> None:
    snapshot = task_telemetry_snapshot(completed_row())

    assert snapshot["terminal"] is True
    assert snapshot["task_outcome"] == "accepted"
    assert snapshot["first_pass_success"] is True
    assert snapshot["role"] == "backend_developer"
    assert snapshot["model_id"] == "codex_terra"
    assert snapshot["verification"]["targeted_runs"] == 1
    assert snapshot["verification"]["full_runs"] == 1
    assert snapshot["ci_pass"] is True
    assert snapshot["review"]["findings_actioned"] == 1
    assert snapshot["resources"]["estimated"]["max_model_calls"] == 6.0
    assert snapshot["resources"]["actual"]["max_model_calls"] == 4.0
    assert snapshot["quota_failures"] == 1


def test_sparse_calibration_falls_back_then_uses_bounded_observed_ratios() -> None:
    base = task_telemetry_snapshot(completed_row())
    sparse = [deepcopy(base) for _ in range(4)]
    result = aggregate_calibration(sparse, minimum_sample_size=5)

    assert result["sufficient_sample"] is False
    assert result["resource_multipliers"] == {}
    assert result["model_success"] == {}
    assert result["fallback"] == "policy_defaults"

    samples = [deepcopy(base) for _ in range(5)]
    for sample in samples:
        sample["resources"]["actual"]["max_model_calls"] = 9.0
    result = aggregate_calibration(samples, minimum_sample_size=5)

    assert result["sufficient_sample"] is True
    assert result["resource_multipliers"]["max_model_calls"] == 1.5
    assert result["model_success"]["codex_terra"] == {"sample_size": 5, "success_rate": 1.0}
    assert result["fallback"] is None


def test_attention_classification_separates_protected_decisions_from_routine_operations() -> None:
    adaptive = completed_row()
    legacy = completed_row()
    legacy["route"]["strategy"].pop("adaptive_budget")

    assert classify_attention_event("human_decision", adaptive) == {
        "category": "decision_boundary",
        "avoidable": False,
    }
    assert classify_budget_attention(legacy) == {
        "category": "routine_operational",
        "avoidable": True,
    }
    assert classify_budget_attention(adaptive) == {
        "category": "routine_operational",
        "avoidable": False,
    }


def test_blocked_snapshot_surfaces_budget_without_useful_outcome_but_is_not_calibration_terminal() -> None:
    row = completed_row()
    row["status"] = "blocked"
    row["result"] = {"reason": "execution_budget_exhausted"}
    row["progress"]["model_calls"] = 8

    snapshot = task_telemetry_snapshot(row)

    assert snapshot["terminal"] is False
    assert snapshot["task_outcome"] == "blocked"
    assert snapshot["resources"]["budget_without_useful_outcome"] is True
