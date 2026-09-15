from __future__ import annotations

from app.config import clear_config_cache, get_config
from app.engine_review import RouterEngine
from app.schemas import RoutingRequest


def make_engine() -> RouterEngine:
    clear_config_cache()
    return RouterEngine(get_config())


def request(*, semantic, repo=None, flags=None, provider_state=None) -> RoutingRequest:
    return RoutingRequest(
        job_id="review-policy-job",
        project_id="default",
        repository="repo",
        source_commit="abcd1234",
        task={
            "title": "Review policy task",
            "task_type": "feature",
            "flags": flags or [],
            "semantic": semantic,
        },
        repo=repo or {
            "estimated_files": 1,
            "affected_components": 1,
            "dependency_depth": 1,
            "tests_available": True,
            "existing_pattern": True,
        },
        provider_state=provider_state or {},
    )


def test_fast_prepares_lightweight_alternate_reviewer_but_allows_runtime_skip() -> None:
    result = make_engine().route(
        request(
            semantic={
                "ambiguity": 5,
                "architecture_impact": 5,
                "verification_difficulty": 5,
                "risk": 5,
                "context_requirement": 10,
                "novelty": 5,
                "reasoning_requirement": 10,
            }
        )
    )

    assert result.strategy.profile == "fast"
    assert result.strategy.review_policy.level == "lightweight"
    assert result.strategy.review_policy.required is False
    assert result.strategy.review_policy.conditional_on_strong_evidence is True
    assert result.strategy.evaluator is not None
    assert result.strategy.evaluator.id != result.strategy.executor.id


def test_standard_gets_bounded_independent_review() -> None:
    result = make_engine().route(
        request(
            semantic={
                "ambiguity": 35,
                "architecture_impact": 20,
                "verification_difficulty": 35,
                "risk": 25,
                "context_requirement": 45,
                "novelty": 35,
                "reasoning_requirement": 50,
            },
            repo={
                "estimated_files": 5,
                "affected_components": 2,
                "dependency_depth": 2,
                "tests_available": True,
                "existing_pattern": True,
            },
        )
    )

    assert result.strategy.profile == "standard"
    assert result.strategy.review_policy.level == "standard"
    assert result.strategy.review_policy.required is True
    assert result.strategy.review_policy.independent is True
    assert result.strategy.evaluator is not None


def test_complex_prefers_a_different_model_reviewer() -> None:
    result = make_engine().route(
        request(
            semantic={
                "ambiguity": 60,
                "architecture_impact": 45,
                "verification_difficulty": 65,
                "risk": 45,
                "context_requirement": 75,
                "novelty": 55,
                "reasoning_requirement": 85,
            },
            repo={
                "estimated_files": 10,
                "affected_components": 4,
                "dependency_depth": 6,
                "tests_available": True,
                "existing_pattern": False,
                "external_api": True,
            },
        )
    )

    assert result.strategy.profile == "complex"
    assert result.strategy.review_policy.level == "strong"
    assert result.strategy.review_policy.different_model_required is True
    assert result.strategy.evaluator is not None
    assert result.strategy.evaluator.id != result.strategy.executor.id


def test_security_or_architecture_work_gets_cross_provider_review_when_eligible() -> None:
    result = make_engine().route(
        request(
            semantic={
                "ambiguity": 65,
                "architecture_impact": 90,
                "verification_difficulty": 80,
                "risk": 90,
                "context_requirement": 85,
                "novelty": 70,
                "reasoning_requirement": 90,
            },
            flags=["security_sensitive"],
            repo={
                "estimated_files": 12,
                "affected_components": 5,
                "dependency_depth": 6,
                "tests_available": True,
                "existing_pattern": False,
                "security_sensitive": True,
            },
        )
    )

    assert result.strategy.review_policy.level == "critical"
    assert result.strategy.review_policy.different_provider_required is True
    assert result.strategy.evaluator is not None
    assert result.strategy.evaluator.provider != result.strategy.executor.provider
    assert result.strategy.review_policy.independence_satisfied is True


def test_cross_provider_requirement_records_degradation_when_only_same_provider_is_eligible() -> None:
    result = make_engine().route(
        request(
            semantic={
                "ambiguity": 65,
                "architecture_impact": 90,
                "verification_difficulty": 80,
                "risk": 90,
                "context_requirement": 85,
                "novelty": 70,
                "reasoning_requirement": 90,
            },
            flags=["security_sensitive"],
            repo={
                "estimated_files": 12,
                "affected_components": 5,
                "dependency_depth": 6,
                "tests_available": True,
                "existing_pattern": False,
                "security_sensitive": True,
            },
            provider_state={
                "provider:google_antigravity": {"available": False, "healthy": False},
                "provider:openrouter": {"available": False, "healthy": False},
            },
        )
    )

    assert result.strategy.review_policy.different_provider_required is True
    assert result.strategy.evaluator is not None
    assert result.strategy.review_policy.independence_satisfied is False
