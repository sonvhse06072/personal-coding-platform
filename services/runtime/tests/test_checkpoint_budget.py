from app.engine import RuntimeEngine


def test_progress_defaults_are_monotonic_budget_counters():
    progress = RuntimeEngine._new_progress()
    for key in (
        "model_calls", "input_tokens", "output_tokens", "tool_calls", "test_runs",
        "iteration", "repair_iterations", "provider_failovers", "model_failovers",
    ):
        assert progress[key] == 0
