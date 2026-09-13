from __future__ import annotations

from typing import Any

from .config import model_config


_INPUT_KEYS = ("input_tokens", "inputTokens", "prompt_tokens", "promptTokenCount")
_CACHED_INPUT_KEYS = ("cached_input_tokens", "cachedInputTokens", "cached_tokens")
_OUTPUT_KEYS = ("output_tokens", "outputTokens", "completion_tokens", "candidatesTokenCount")
_COST_KEYS = ("cost_usd", "costUSD", "cost")


def _number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _first_number(mapping: dict[str, Any], keys: tuple[str, ...]) -> float | None:
    for key in keys:
        value = _number(mapping.get(key))
        if value is not None:
            return value
    return None


def _find_nested(mapping: dict[str, Any], keys: tuple[str, ...]) -> float:
    direct = _first_number(mapping, keys)
    if direct is not None:
        return direct
    # Only descend when no aggregate exists at the current level. This avoids
    # double-counting providers that expose both totals and per-model details.
    values: list[float] = []
    for value in mapping.values():
        if isinstance(value, dict):
            found = _find_nested(value, keys)
            if found:
                values.append(found)
        elif isinstance(value, list):
            for item in value:
                if isinstance(item, dict):
                    found = _find_nested(item, keys)
                    if found:
                        values.append(found)
    return sum(values)


def normalize_usage(raw: dict[str, Any] | None) -> dict[str, float | int]:
    data = raw or {}
    gross_input_tokens = int(max(0, _find_nested(data, _INPUT_KEYS)))
    cached_input_tokens = int(max(0, _find_nested(data, _CACHED_INPUT_KEYS)))
    # Providers such as Codex report cached_input_tokens as a subset of the
    # aggregate input_tokens count. Runtime input-token budgets are intended to
    # bound new/cache-miss context growth, not repeatedly reused cached prefixes.
    # Preserve both values for observability while exposing the budget-bearing
    # cache-miss count as input_tokens. Providers that do not report cache usage
    # keep the previous behavior because cached_input_tokens remains zero.
    cached_input_tokens = min(gross_input_tokens, cached_input_tokens)
    input_tokens = gross_input_tokens - cached_input_tokens
    output_tokens = int(max(0, _find_nested(data, _OUTPUT_KEYS)))
    reported_cost = max(0.0, _find_nested(data, _COST_KEYS))
    return {
        "input_tokens": input_tokens,
        "gross_input_tokens": gross_input_tokens,
        "cached_input_tokens": cached_input_tokens,
        "output_tokens": output_tokens,
        "reported_cost_usd": round(reported_cost, 8),
    }


def estimated_cost_usd(model_id: str, raw_usage: dict[str, Any] | None) -> float:
    usage = normalize_usage(raw_usage)
    reported = float(usage["reported_cost_usd"])
    if reported > 0:
        return reported
    cfg = model_config(model_id)
    pricing = cfg.get("pricing_usd_per_million") or {}
    input_rate = float(pricing.get("input", 0.0))
    output_rate = float(pricing.get("output", 0.0))
    # Keep cost estimation conservative and backward-compatible: unless a
    # provider reports an explicit cost, price the provider's full aggregate
    # input count. Cached-token discounts are not inferred from budget semantics.
    return round(
        (int(usage["gross_input_tokens"]) / 1_000_000) * input_rate
        + (int(usage["output_tokens"]) / 1_000_000) * output_rate,
        8,
    )
