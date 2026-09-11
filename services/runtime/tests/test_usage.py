from app.usage import normalize_usage, estimated_cost_usd


def test_normalize_usage_and_conservative_cost():
    usage = {"input_tokens": 100_000, "output_tokens": 10_000}
    normalized = normalize_usage(usage)
    assert normalized["input_tokens"] == 100_000
    assert normalized["output_tokens"] == 10_000
    # DeepSeek v4 Flash peak/cache-miss conservative registry price:
    # 0.1 * $0.44 + 0.01 * $1.32 = $0.0572
    assert estimated_cost_usd("deepseek_flash", usage) == 0.0572


def test_reported_provider_cost_wins():
    usage = {"input_tokens": 1000, "output_tokens": 100, "cost": 0.1234}
    assert estimated_cost_usd("claude_sonnet", usage) == 0.1234
