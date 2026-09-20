from app.engine_antigravity import RuntimeEngine


def _choice(*, model_id="antigravity_free", quota_group="antigravity_gemini"):
    return {
        "id": model_id,
        "provider": "google_antigravity",
        "adapter": "antigravity_host",
        "model": "gemini-3.8-flash-medium",
        "quota_group": quota_group,
    }


def test_antigravity_quota_exhaustion_marks_only_selected_model_quota():
    state = {}

    RuntimeEngine._mark_provider_failure(state, _choice(), "quota_exhausted")

    assert "provider:google_antigravity" not in state
    assert "quota:antigravity_gemini" not in state
    marker = state["quota:model:antigravity_free"]
    assert marker["healthy"] is False
    assert marker["available"] is False
    assert marker["error_rate"] == 1.0
    assert marker["quota_pressure"] == 1.0
    assert marker["failure_kind"] == "quota_exhausted"
    assert marker["failed_at"]


def test_antigravity_rate_limit_marks_only_selected_model_quota():
    state = {}

    RuntimeEngine._mark_provider_failure(state, _choice(), "rate_limited")

    assert "provider:google_antigravity" not in state
    assert state["quota:model:antigravity_free"]["available"] is False


def test_antigravity_bridge_failure_remains_provider_wide():
    state = {}

    RuntimeEngine._mark_provider_failure(state, _choice(), "provider_unavailable")

    assert state["provider:google_antigravity"]["available"] is False
    assert "quota:model:antigravity_free" not in state


def test_registered_shared_quota_failure_uses_quota_group_not_provider_scope():
    state = {}
    choice = {
        "id": "openrouter_qwen3_coder_free",
        "provider": "openrouter",
        "adapter": "opencode",
        "model": "openrouter/cohere/north-mini-code:free",
        "quota_group": "openrouter_free",
    }

    RuntimeEngine._mark_provider_failure(state, choice, "quota_exhausted")

    assert "provider:openrouter" not in state
    assert state["quota:openrouter_free"]["available"] is False
    assert state["quota:openrouter_free"]["failure_kind"] == "quota_exhausted"

def test_codex_quota_exhaustion_uses_shared_subscription_quota_group():
    state = {}
    choice = {
        "id": "codex_terra",
        "provider": "openai",
        "adapter": "codex_cli",
        "model": "gpt-5.6-terra",
        "quota_group": "codex_chatgpt_plus",
    }

    RuntimeEngine._mark_provider_failure(state, choice, "quota_exhausted")

    assert "provider:openai" not in state
    assert state["quota:codex_chatgpt_plus"]["available"] is False
    assert state["quota:codex_chatgpt_plus"]["failure_kind"] == "quota_exhausted"

