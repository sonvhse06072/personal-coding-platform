from pathlib import Path

import pytest

from app.state import (
    checkpoint_from_row,
    clear_transient_provider_failures,
    decision_key,
    merge_progress,
    validate_workspace,
)


def test_merge_progress_preserves_consumed_budget():
    defaults = {"model_calls": 0, "iteration": 0, "agent_attempts": []}
    merged = merge_progress(defaults, {"model_calls": 5, "iteration": 3})
    assert merged["model_calls"] == 5
    assert merged["iteration"] == 3
    assert merged["agent_attempts"] == []


def test_checkpoint_migrates_legacy_initial_job_shape():
    checkpoint = checkpoint_from_row({
        "checkpoint": None,
        "repo_analysis": {
            "hints": {"estimated_files": 2},
            "provider_state": {"provider:openai": {"available": False}},
        },
    })
    assert checkpoint["hints"]["estimated_files"] == 2
    assert checkpoint["provider_state"]["provider:openai"]["available"] is False


def test_reset_provider_failures_keeps_model_level_failures():
    checkpoint = {
        "provider_state": {
            "provider:openai": {"available": False},
            "codex_plus": {"available": False},
        }
    }
    updated = clear_transient_provider_failures(checkpoint)
    assert "provider:openai" not in updated["provider_state"]
    assert updated["provider_state"]["codex_plus"]["available"] is False


def test_decision_key_is_order_independent():
    a = decision_key({"triggers": ["production_write", "architecture_choice"]})
    b = decision_key({"triggers": ["architecture_choice", "production_write"]})
    assert a == b


def test_validate_workspace_requires_exact_job_directory(tmp_path: Path):
    root = tmp_path / "workspaces"
    workspace = root / "job12345"
    (workspace / ".git").mkdir(parents=True)
    assert validate_workspace(root, "job12345", workspace) == workspace.resolve()

    other = root / "other"
    (other / ".git").mkdir(parents=True)
    with pytest.raises(RuntimeError):
        validate_workspace(root, "job12345", other)
