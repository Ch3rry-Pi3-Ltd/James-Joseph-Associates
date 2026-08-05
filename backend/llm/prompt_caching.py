"""Content-free aggregation for provider prompt-caching evaluations."""

from __future__ import annotations

from math import ceil
from typing import Any

from backend.llm.benchmarking import estimate_openai_cost_usd
from backend.llm.budgets import (
    GPT_4_1_MINI_CACHED_INPUT_USD_PER_MILLION,
    GPT_4_1_MINI_INPUT_USD_PER_MILLION,
)


def summarize_prompt_cache_variant(
    *,
    name: str,
    prompt_cache_key_supplied: bool,
    samples: list[dict[str, Any]],
) -> dict[str, Any]:
    """Compare one cold request with repeated stable-prefix requests."""

    enriched_samples = [_enrich_sample(sample) for sample in samples]
    successful = [
        sample for sample in enriched_samples if sample.get("status") == "success"
    ]
    cold_samples = [sample for sample in successful if sample.get("phase") == "cold"]
    warm_samples = [sample for sample in successful if sample.get("phase") == "warm"]
    cache_hits = [
        sample
        for sample in warm_samples
        if _non_negative_int(sample.get("cached_input_tokens")) > 0
    ]
    cold = cold_samples[0] if len(cold_samples) == 1 else None
    cold_latency_ms = _optional_float(cold.get("latency_ms")) if cold else None
    warm_latencies = [
        latency
        for sample in warm_samples
        if (latency := _optional_float(sample.get("latency_ms"))) is not None
    ]
    warm_average_latency_ms = _average(warm_latencies)
    warm_p50_latency_ms = _nearest_rank_percentile(warm_latencies, 0.50)
    warm_p95_latency_ms = _nearest_rank_percentile(warm_latencies, 0.95)
    warm_input_tokens = sum(
        _non_negative_int(sample.get("input_tokens")) for sample in warm_samples
    )
    warm_cached_tokens = sum(
        _non_negative_int(sample.get("cached_input_tokens"))
        for sample in warm_samples
    )
    actual_input_cost_usd = round(
        sum(float(sample["estimated_input_cost_usd"]) for sample in successful),
        9,
    )
    uncached_input_cost_usd = round(
        sum(
            float(sample["uncached_input_cost_usd"])
            for sample in successful
        ),
        9,
    )
    total_estimated_cost_usd = round(
        sum(
            float(cost)
            for sample in successful
            if (cost := sample.get("estimated_cost_usd")) is not None
        ),
        9,
    )
    expected_warm_samples = max(0, len(samples) - 1)
    reasons: list[str] = []
    if len(successful) != len(samples):
        reasons.append(
            f"expected {len(samples)} successful samples, got {len(successful)}"
        )
    if len(cold_samples) != 1:
        reasons.append(f"expected one cold sample, got {len(cold_samples)}")
    if len(warm_samples) != expected_warm_samples:
        reasons.append(
            f"expected {expected_warm_samples} warm samples, got {len(warm_samples)}"
        )
    missing_usage_count = sum(
        not _has_complete_measurement(sample) for sample in successful
    )
    if missing_usage_count:
        reasons.append(
            f"{missing_usage_count} successful samples lacked latency or token usage"
        )
    if cold is not None and _non_negative_int(cold.get("cached_input_tokens")) > 0:
        reasons.append("the isolated cold sample unexpectedly reported cached tokens")

    return {
        "name": name,
        "prompt_cache_key_supplied": prompt_cache_key_supplied,
        "sample_count": len(samples),
        "successful_sample_count": len(successful),
        "failed_sample_count": len(samples) - len(successful),
        "cold": {
            "latency_ms": cold_latency_ms,
            "input_tokens": cold.get("input_tokens") if cold else None,
            "cached_input_tokens": (
                cold.get("cached_input_tokens") if cold else None
            ),
            "estimated_input_cost_usd": (
                cold.get("estimated_input_cost_usd") if cold else None
            ),
        },
        "warm": {
            "sample_count": len(warm_samples),
            "cache_hit_count": len(cache_hits),
            "cache_hit_rate": _ratio(len(cache_hits), len(warm_samples)),
            "cached_token_ratio": _ratio(warm_cached_tokens, warm_input_tokens),
            "total_input_tokens": warm_input_tokens,
            "total_cached_input_tokens": warm_cached_tokens,
            "average_latency_ms": warm_average_latency_ms,
            "p50_latency_ms": warm_p50_latency_ms,
            "p95_latency_ms": warm_p95_latency_ms,
        },
        "comparison": {
            "warm_average_latency_reduction_ratio": _reduction_ratio(
                cold_latency_ms,
                warm_average_latency_ms,
            ),
            "actual_input_cost_usd": actual_input_cost_usd,
            "uncached_input_cost_usd": uncached_input_cost_usd,
            "input_cost_saved_usd": round(
                uncached_input_cost_usd - actual_input_cost_usd,
                9,
            ),
            "input_cost_reduction_ratio": _reduction_ratio(
                uncached_input_cost_usd,
                actual_input_cost_usd,
            ),
            "total_estimated_cost_usd": total_estimated_cost_usd,
        },
        "evaluation_complete": not reasons,
        "completion_reasons": reasons,
        "samples": enriched_samples,
    }


def compare_prompt_cache_variants(
    keyed: dict[str, Any],
    automatic: dict[str, Any],
) -> dict[str, Any]:
    """Compare warm cache effectiveness with and without a cache key."""

    keyed_warm = keyed["warm"]
    automatic_warm = automatic["warm"]
    return {
        "keyed_minus_automatic_cache_hit_rate": _difference(
            keyed_warm.get("cache_hit_rate"),
            automatic_warm.get("cache_hit_rate"),
        ),
        "keyed_minus_automatic_cached_token_ratio": _difference(
            keyed_warm.get("cached_token_ratio"),
            automatic_warm.get("cached_token_ratio"),
        ),
        "keyed_to_automatic_warm_latency_ratio": _ratio(
            keyed_warm.get("average_latency_ms"),
            automatic_warm.get("average_latency_ms"),
        ),
        "keyed_to_automatic_input_cost_ratio": _ratio(
            keyed["comparison"].get("actual_input_cost_usd"),
            automatic["comparison"].get("actual_input_cost_usd"),
        ),
    }


def _enrich_sample(sample: dict[str, Any]) -> dict[str, Any]:
    enriched = dict(sample)
    input_tokens = _non_negative_int(sample.get("input_tokens"))
    cached_tokens = min(
        _non_negative_int(sample.get("cached_input_tokens")),
        input_tokens,
    )
    uncached_tokens = input_tokens - cached_tokens
    enriched["estimated_cost_usd"] = estimate_openai_cost_usd(sample)
    enriched["estimated_input_cost_usd"] = round(
        (
            uncached_tokens * GPT_4_1_MINI_INPUT_USD_PER_MILLION
            + cached_tokens
            * GPT_4_1_MINI_CACHED_INPUT_USD_PER_MILLION
        )
        / 1_000_000,
        9,
    )
    enriched["uncached_input_cost_usd"] = round(
        input_tokens * GPT_4_1_MINI_INPUT_USD_PER_MILLION / 1_000_000,
        9,
    )
    return enriched


def _non_negative_int(value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return 0
    return max(0, int(value))


def _has_complete_measurement(sample: dict[str, Any]) -> bool:
    return all(
        not isinstance(sample.get(key), bool)
        and isinstance(sample.get(key), (int, float))
        for key in (
            "latency_ms",
            "input_tokens",
            "cached_input_tokens",
            "output_tokens",
        )
    )


def _optional_float(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _average(values: list[float]) -> float | None:
    if not values:
        return None
    return round(sum(values) / len(values), 3)


def _nearest_rank_percentile(
    values: list[float],
    percentile: float,
) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = max(0, ceil(len(ordered) * percentile) - 1)
    return round(ordered[index], 3)


def _ratio(numerator: Any, denominator: Any) -> float | None:
    numerator_value = _optional_float(numerator)
    denominator_value = _optional_float(denominator)
    if numerator_value is None or denominator_value is None or denominator_value <= 0:
        return None
    return round(numerator_value / denominator_value, 6)


def _reduction_ratio(baseline: Any, current: Any) -> float | None:
    baseline_value = _optional_float(baseline)
    current_value = _optional_float(current)
    if baseline_value is None or current_value is None or baseline_value <= 0:
        return None
    return round((baseline_value - current_value) / baseline_value, 6)


def _difference(left: Any, right: Any) -> float | None:
    left_value = _optional_float(left)
    right_value = _optional_float(right)
    if left_value is None or right_value is None:
        return None
    return round(left_value - right_value, 6)


__all__ = [
    "compare_prompt_cache_variants",
    "summarize_prompt_cache_variant",
]
