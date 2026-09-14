from app.engine_antigravity import RuntimeEngine


def _choice(*, model_id="antigravity_free", quota_group="antigravity_gemini"):
    return {
        "id": model_id,
        "provider": "google_antigravity",
        "adapter": "antigravity_host",
        "model": "gemini-3.8-flash-medium",
        "quota_group": quota_group,
    }


def test_antigravity_quota_exhaustion_marks_only_quota_group():
    state = {}

    RuntimeEngine._mark_provider_failure(state, _choice(), "quota_exhausted")

    assert "provider:google_antigravity" not in state
    assert state["quota:antigravity_gemini"] == {
        "healthy": False,
        "available": False,
        "error_rate": 1.0,
        "quota_pressure": 1.0,
    }


def test_antigravity_rate_limit_marks_only_quota_group():
    state = {}

    RuntimeEngine._mark_provider_failure(state, _choice(), "rate_limited")

    assert "provider:google_antigravity" not in state
    assert state["quota:antigravity_gemini"]["available"] is False


def test_antigravity_bridge_failure_remains_provider_wide():
    state = {}

    RuntimeEngine._mark_provider_failure(state, _choice(), "provider_unavailable")

    assert state["provider:google_antigravity"]["available"] is False
    assert "quota:antigravity_gemini" not in state


def test_other_provider_quota_failure_keeps_existing_provider_wide_semantics():
    state = {}
    choice = {
        "id": "openrouter_qwen3_coder_free",
        "provider": "openrouter",
        "adapter": "opencode",
        "model": "openrouter/cohere/north-mini-code:free",
        "quota_group": "openrouter_free",
    }

    RuntimeEngine._mark_provider_failure(state, choice, "quota_exhausted")

    assert state["provider:openrouter"]["available"] is False
    assert "quota:openrouter_free" not in state
