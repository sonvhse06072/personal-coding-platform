from app.engine_antigravity import RuntimeEngine


def _choice(*, adapter="codex_cli", effort="medium"):
    registry = {
        "codex_cli": ("codex_terra", "openai", "gpt-5.6-terra"),
        "antigravity_host": (
            "antigravity_free",
            "google_antigravity",
            "gemini-3.8-flash-medium",
        ),
        "opencode": (
            "openrouter_qwen3_coder_free",
            "openrouter",
            "openrouter/cohere/north-mini-code:free",
        ),
    }
    model_id, provider, model = registry[adapter]
    return {
        "id": model_id,
        "provider": provider,
        "adapter": adapter,
        "model": model,
        "reasoning_effort": effort,
        "reasons": [],
    }


def test_next_reasoning_choice_increases_same_codex_model_to_ceiling():
    current = _choice(effort="medium")
    strategy = {"reasoning_ceiling": {"executor": "high"}}

    boosted = RuntimeEngine._next_reasoning_choice(current, strategy)

    assert boosted is not None
    assert boosted["id"] == current["id"]
    assert boosted["model"] == current["model"]
    assert boosted["reasoning_effort"] == "high"
    assert current["reasoning_effort"] == "medium"


def test_antigravity_reasoning_effort_can_escalate_without_changing_model():
    current = _choice(adapter="antigravity_host", effort="medium")
    strategy = {"reasoning_ceiling": {"executor": "high"}}

    boosted = RuntimeEngine._next_reasoning_choice(current, strategy)

    assert boosted is not None
    assert boosted["id"] == "antigravity_free"
    assert boosted["model"] == "gemini-3.8-flash-medium"
    assert boosted["reasoning_effort"] == "high"


def test_next_reasoning_choice_stops_at_ceiling():
    assert RuntimeEngine._next_reasoning_choice(
        _choice(effort="high"),
        {"reasoning_ceiling": {"executor": "high"}},
    ) is None


def test_codex_capability_can_advance_beyond_high_only_with_a_higher_ceiling():
    boosted = RuntimeEngine._next_reasoning_choice(
        _choice(effort="high"),
        {"reasoning_ceiling": {"executor": "max"}},
    )

    assert boosted is not None
    assert boosted["reasoning_effort"] == "xhigh"


def test_antigravity_capability_stops_at_high_even_with_max_ceiling():
    assert RuntimeEngine._next_reasoning_choice(
        _choice(adapter="antigravity_host", effort="high"),
        {"reasoning_ceiling": {"executor": "max"}},
    ) is None


def test_adapter_without_reasoning_control_is_not_overridden():
    assert RuntimeEngine._next_reasoning_choice(
        _choice(adapter="opencode", effort=None),
        {"reasoning_ceiling": {"executor": "high"}},
    ) is None
