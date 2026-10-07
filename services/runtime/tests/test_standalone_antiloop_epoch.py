from copy import deepcopy

from app.standalone_antiloop_epoch import (
    EPOCH_KEY,
    effective_reassessment_progress,
    start_pm_antiloop_epoch,
)


def progress():
    return {
        "iteration": 10,
        "repair_iterations": 12,
        "model_calls": 15,
        "tool_calls": 30,
        "test_runs": 25,
        "elapsed_minutes": 20.0,
        "changed_files": 4,
        "unexpected_scope": False,
        "failure_fingerprints": ["old", "old", "old", "pm-control"],
        "progress_markers": ["old", "old", "old", "pm-control"],
        "diff_hashes": ["diff-a", "diff-b"],
    }


def checkpoint(signature="sig-1", diff_hash="diff-b"):
    return {
        "deterministic_verification_failure_streak": {
            "count": 1,
            "limit": 2,
            "signature": signature,
            "diff_hash": diff_hash,
            "failing_phases": ["targeted_tests"],
        }
    }


def test_epoch_preserves_durable_history_but_hides_pre_authorization_tail():
    durable = progress()
    original = deepcopy(durable)
    state = checkpoint()

    epoch = start_pm_antiloop_epoch(
        state,
        durable,
        blocker_generation="generation-1",
        diff_hash="diff-b",
        selectors=["no_progress", "repeated_failure"],
    )
    effective, changed = effective_reassessment_progress(state, durable)

    assert changed is False
    assert durable == original
    assert effective["failure_fingerprints"] == []
    assert effective["progress_markers"] == []
    assert effective["diff_hashes"] == []
    assert effective["repair_iterations"] == 12
    assert effective["test_runs"] == 25
    assert epoch["failure_fingerprint_start"] == 4
    assert epoch["progress_marker_start"] == 4
    assert epoch["diff_hash_start"] == 2


def test_changed_verification_signature_advances_epoch_baseline():
    durable = progress()
    state = checkpoint()
    start_pm_antiloop_epoch(
        state,
        durable,
        blocker_generation="generation-1",
        diff_hash="diff-b",
        selectors=["all_current"],
    )

    durable["failure_fingerprints"].extend(["same", "same"])
    durable["progress_markers"].extend(["same", "same"])
    durable["diff_hashes"].append("diff-c")
    state["deterministic_verification_failure_streak"] = {
        "count": 1,
        "limit": 2,
        "signature": "sig-2",
        "diff_hash": "diff-c",
        "failing_phases": ["targeted_tests"],
    }

    effective, changed = effective_reassessment_progress(state, durable)

    assert changed is True
    assert effective["failure_fingerprints"] == []
    assert effective["progress_markers"] == []
    assert effective["diff_hashes"] == []
    assert durable["failure_fingerprints"][-2:] == ["same", "same"]
    epoch = state[EPOCH_KEY]
    assert epoch["latest_verification_signature"] == "sig-2"
    assert epoch["latest_diff_hash"] == "diff-c"
    assert len(epoch["progress_advances"]) == 1
    assert epoch["progress_advances"][0]["kind"] == "verification_signature"


def test_same_verification_signature_does_not_hide_diff_churn():
    durable = progress()
    state = checkpoint()
    start_pm_antiloop_epoch(
        state,
        durable,
        blocker_generation="generation-1",
        diff_hash="diff-b",
        selectors=["all_current"],
    )

    durable["failure_fingerprints"].extend(["same", "same", "same"])
    durable["progress_markers"].extend(["same", "same", "same"])
    durable["diff_hashes"].extend(["diff-c", "diff-d"])
    state["deterministic_verification_failure_streak"]["diff_hash"] = "diff-d"

    effective, changed = effective_reassessment_progress(state, durable)

    assert changed is False
    assert effective["failure_fingerprints"] == ["same", "same", "same"]
    assert effective["progress_markers"] == ["same", "same", "same"]
    assert effective["diff_hashes"] == ["diff-c", "diff-d"]
    assert state[EPOCH_KEY]["latest_verification_signature"] == "sig-1"


def test_diff_hash_is_progress_fallback_only_when_signature_is_absent():
    durable = progress()
    state = checkpoint(signature="")
    start_pm_antiloop_epoch(
        state,
        durable,
        blocker_generation="generation-1",
        diff_hash="diff-b",
        selectors=["all_current"],
    )

    durable["failure_fingerprints"].append("failure")
    durable["progress_markers"].append("failure")
    durable["diff_hashes"].append("diff-c")
    state["deterministic_verification_failure_streak"] = {
        "count": 0,
        "limit": 2,
        "signature": "",
        "diff_hash": "diff-c",
        "failing_phases": [],
    }

    effective, changed = effective_reassessment_progress(state, durable)

    assert changed is True
    assert effective["failure_fingerprints"] == []
    assert effective["progress_markers"] == []
    assert state[EPOCH_KEY]["progress_advances"][-1]["kind"] == "diff_hash"


def test_no_epoch_preserves_existing_reassessment_behavior():
    durable = progress()
    effective, changed = effective_reassessment_progress({}, durable)

    assert changed is False
    assert effective == durable
    assert effective is not durable
