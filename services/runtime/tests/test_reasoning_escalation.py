from app.engine import RuntimeEngine


def _choice(*, adapter="codex_cli", effort="medium"):
    return {
        "id": "codex_terra" if adapter == "codex_cli" else "antigravity_free",
        "provider": "openai" if adapter == "codex_cli" else "google_antigravity",
        "adapter": adapter,
        "model": "gpt-5.6-terra" if adapter == "codex_cli" else "auto",
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


def test_next_reasoning_choice_stops_at_ceiling():
    assert RuntimeEngine._next_reasoning_choice(
        _choice(effort="high"),
        {"reasoning_ceiling": {"executor": "high"}},
    ) is None


def test_non_codex_provider_never_gets_codex_reasoning_override():
    assert RuntimeEngine._next_reasoning_choice(
        _choice(adapter="antigravity_host", effort=None),
        {"reasoning_ceiling": {"executor": "high"}},
    ) is None
