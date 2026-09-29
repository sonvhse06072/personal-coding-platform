from itertools import combinations
import inspect

import pytest

from app import intake_policy
from app.intake_policy import classify_intake
from app.schemas import RepoHints, SemanticSignals


def small_semantic():
    return {name: 10 for name in SemanticSignals.model_fields}


def small_hints():
    return {
        "estimated_files": 2, "affected_components": 1, "dependency_depth": 0,
        "tests_available": True, "existing_pattern": True, "historical_churn": 0,
        **{name: False for name in intake_policy.HARD_BOUNDARIES},
    }


def classify(*, semantic=None, hints=None, bounded_direct=True):
    return classify_intake(
        bounded_direct=bounded_direct,
        semantic=SemanticSignals(**(small_semantic() if semantic is None else semantic)),
        repo_hints=RepoHints(**(small_hints() if hints is None else hints)),
    )


def test_direct_requires_explicit_intent_and_complete_evidence():
    assert classify().mode == "direct"
    assert classify().decomposition_required is False
    assert classify(bounded_direct=False).mode == "planning"
    unknown = classify_intake(bounded_direct=True, semantic=None, repo_hints=RepoHints())
    assert unknown.mode == "planning"
    assert unknown.decomposition_required is False
    assert classify(semantic={}).mode == "planning"


@pytest.mark.parametrize("field", list(SemanticSignals.model_fields))
def test_defaulted_semantic_values_are_not_evidence(field):
    values = small_semantic()
    del values[field]
    result = classify(semantic=values)
    assert result.mode == "planning"
    assert f"missing:semantic.{field}" in result.reasons


@pytest.mark.parametrize("field", intake_policy.REQUIRED_HINTS)
@pytest.mark.parametrize("unknown", ["absent", None])
def test_unknown_repo_hints_fail_safe(field, unknown):
    values = small_hints()
    if unknown == "absent":
        del values[field]
    else:
        values[field] = unknown
    result = classify(hints=values)
    assert result.mode == "planning"
    assert f"missing:repo_hints.{field}" in result.reasons


@pytest.mark.parametrize("field", intake_policy.HARD_BOUNDARIES)
def test_each_protected_boundary_requires_planning(field):
    result = classify(hints={**small_hints(), field: True})
    assert result.mode == "planning"
    assert result.decomposition_required is True
    assert f"hard:{field}" in result.reasons


@pytest.mark.parametrize("depth", [1, 10])
def test_dependencies_require_planning(depth):
    result = classify(hints={**small_hints(), "dependency_depth": depth})
    assert result.mode == "planning" and result.decomposition_required


def test_multi_unit_shape_and_unknown_zero_surface():
    assert classify(hints={**small_hints(), "affected_components": 3}).decomposition_required
    for field in ("affected_components", "estimated_files"):
        assert classify(hints={**small_hints(), field: 0}).mode == "planning"


@pytest.mark.parametrize("files", [10, 500])
def test_high_file_count_alone_never_forces_large_ticket(files):
    result = classify(hints={**small_hints(), "estimated_files": files})
    assert result.mode == "direct"
    assert result.material_signals == ["estimated_files"]
    assert result.decomposition_required is False


@pytest.mark.parametrize("name,threshold", intake_policy.SEMANTIC_THRESHOLDS.items())
def test_material_thresholds_need_an_independent_second_signal(name, threshold):
    values = {**small_semantic(), name: threshold}
    assert classify(semantic=values).mode == "direct"
    hints = {**small_hints(), "estimated_files": 10}
    result = classify(semantic=values, hints=hints)
    assert result.mode == "planning" and result.decomposition_required
    assert result.material_signals == [name, "estimated_files"]
    assert classify(semantic={**values, name: threshold - 1}, hints=hints).mode == "direct"


@pytest.mark.parametrize("pair", list(combinations(("affected_components", "historical_churn", "verification_shape", "estimated_files"), 2)))
def test_independent_repository_material_signals(pair):
    changes = {
        "affected_components": {"affected_components": 2},
        "historical_churn": {"historical_churn": 50},
        "verification_shape": {"tests_available": False},
        "estimated_files": {"estimated_files": 10},
    }
    hints = small_hints()
    for name in pair:
        hints.update(changes[name])
    assert classify(hints=hints).mode == "planning"


def test_tests_and_pattern_absence_count_as_one_signal():
    result = classify(hints={**small_hints(), "tests_available": False, "existing_pattern": False})
    assert result.mode == "direct"
    assert result.material_signals == ["verification_shape"]


def test_policy_is_deterministic_and_has_no_staffing_or_io_authority():
    source = inspect.getsource(intake_policy).lower()
    for forbidden in ("provider", "openai", "codex", "gpt-", "router", "http", "async", "open("):
        assert forbidden not in source
    assert classify().model_dump() == classify().model_dump()
    assert classify().policy_version == 1
