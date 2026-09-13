from app.usage import normalize_usage, estimated_cost_usd


def test_normalize_usage_and_conservative_cost():
    usage = {"input_tokens": 100_000, "output_tokens": 10_000}
    normalized = normalize_usage(usage)
    assert normalized["input_tokens"] == 100_000
    assert normalized["gross_input_tokens"] == 100_000
    assert normalized["cached_input_tokens"] == 0
    assert normalized["output_tokens"] == 10_000
    # DeepSeek v4 Flash peak/cache-miss conservative registry price:
    # 0.1 * $0.44 + 0.01 * $1.32 = $0.0572
    assert estimated_cost_usd("deepseek_flash", usage) == 0.0572


def test_cached_input_is_preserved_but_only_cache_miss_counts_toward_budget():
    usage = {
        "input_tokens": 7_568_037,
        "cached_input_tokens": 7_200_000,
        "output_tokens": 56_960,
    }
    normalized = normalize_usage(usage)

    assert normalized["input_tokens"] == 368_037
    assert normalized["gross_input_tokens"] == 7_568_037
    assert normalized["cached_input_tokens"] == 7_200_000
    assert normalized["output_tokens"] == 56_960


def test_nested_cached_input_shape_is_supported():
    usage = {
        "input_tokens": 1000,
        "input_tokens_details": {"cached_tokens": 800},
        "output_tokens": 100,
    }
    normalized = normalize_usage(usage)

    assert normalized["input_tokens"] == 200
    assert normalized["gross_input_tokens"] == 1000
    assert normalized["cached_input_tokens"] == 800


def test_conservative_cost_still_uses_gross_input_when_cache_is_reported():
    usage = {
        "input_tokens": 100_000,
        "cached_input_tokens": 90_000,
        "output_tokens": 10_000,
    }

    # Cost remains conservative: gross input is priced until a provider reports
    # an explicit cost or the registry carries a provider-specific cache price.
    assert estimated_cost_usd("deepseek_flash", usage) == 0.0572


def test_reported_provider_cost_wins():
    usage = {"input_tokens": 1000, "output_tokens": 100, "cost": 0.1234}
    assert estimated_cost_usd("claude_sonnet", usage) == 0.1234
