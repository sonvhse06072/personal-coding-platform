from app.engine_core import RuntimeEngineCore
from app.engine_execution import reusable_passed_review


def test_success_rehabilitation_removes_only_exact_provider_and_model_markers() -> None:
    state = {
        "provider:google_antigravity": {
            "healthy": False,
            "available": False,
        },
        "antigravity_flash_high": {
            "healthy": False,
            "available": False,
        },
        "quota:antigravity_gemini": {
            "healthy": False,
            "available": False,
            "quota_pressure": 1.0,
        },
        "quota:openrouter_free": {
            "healthy": False,
            "available": False,
            "quota_pressure": 1.0,
        },
        "codex_gpt6_sol": {
            "healthy": False,
            "available": False,
        },
    }

    removed = RuntimeEngineCore._rehabilitate_successful_choice(
        state,
        {
            "id": "antigravity_flash_high",
            "provider": "google_antigravity",
        },
    )

    assert removed == [
        "provider:google_antigravity",
        "antigravity_flash_high",
    ]
    assert "provider:google_antigravity" not in state
    assert "antigravity_flash_high" not in state
    assert "quota:antigravity_gemini" in state
    assert "quota:openrouter_free" in state
    assert "codex_gpt6_sol" in state


def test_reusable_passed_review_requires_same_diff_and_fresh_verification_pass() -> None:
    checkpoint = {
        "reuse_passed_review_once": {
            "diff_hash": "same-diff",
            "model": "antigravity_flash_high",
            "provider": "google_antigravity",
            "source_reason": "pm_reassessment_failed",
        },
        "last_review_report": {
            "verdict": "pass",
            "protocol_valid": True,
        },
    }

    assert reusable_passed_review(
        checkpoint,
        {"passed": True},
        diff_hash="same-diff",
    )
    assert not reusable_passed_review(
        checkpoint,
        {"passed": True},
        diff_hash="different-diff",
    )
    assert not reusable_passed_review(
        checkpoint,
        {"passed": False},
        diff_hash="same-diff",
    )


def test_reusable_passed_review_rejects_failed_or_invalid_prior_review() -> None:
    for review in (
        {"verdict": "fail", "protocol_valid": True},
        {"verdict": "pass", "protocol_valid": False},
    ):
        checkpoint = {
            "reuse_passed_review_once": {"diff_hash": "same-diff"},
            "last_review_report": review,
        }
        assert not reusable_passed_review(
            checkpoint,
            {"passed": True},
            diff_hash="same-diff",
        )
