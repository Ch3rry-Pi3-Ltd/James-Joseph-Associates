"""Tests for prompt-cache evaluation aggregation."""

import json
from pathlib import Path

from backend.llm.prompt_caching import (
    compare_prompt_cache_variants,
    summarize_prompt_cache_variant,
)


def _sample(
    index: int,
    *,
    cached_tokens: int,
    latency_ms: float,
) -> dict:
    return {
        "sample_index": index,
        "phase": "cold" if index == 1 else "warm",
        "status": "success",
        "model": "gpt-4.1-mini",
        "latency_ms": latency_ms,
        "input_tokens": 2000,
        "cached_input_tokens": cached_tokens,
        "output_tokens": 10,
        "total_tokens": 2010,
    }


def test_summary_compares_cold_and_warm_cache_effects() -> None:
    result = summarize_prompt_cache_variant(
        name="keyed",
        prompt_cache_key_supplied=True,
        samples=[
            _sample(1, cached_tokens=0, latency_ms=1000),
            _sample(2, cached_tokens=1600, latency_ms=600),
            _sample(3, cached_tokens=1600, latency_ms=500),
        ],
    )

    assert result["evaluation_complete"] is True
    assert result["warm"]["cache_hit_rate"] == 1.0
    assert result["warm"]["cached_token_ratio"] == 0.8
    assert result["warm"]["average_latency_ms"] == 550.0
    assert result["comparison"]["warm_average_latency_reduction_ratio"] == 0.45
    assert result["comparison"]["input_cost_saved_usd"] == 0.00096
    assert result["comparison"]["input_cost_reduction_ratio"] == 0.4
    assert all("estimated_cost_usd" in sample for sample in result["samples"])


def test_summary_marks_provider_errors_incomplete() -> None:
    failed = {
        "sample_index": 2,
        "phase": "warm",
        "status": "error",
        "model": "gpt-4.1-mini",
        "latency_ms": 50,
        "error_type": "TimeoutError",
    }
    result = summarize_prompt_cache_variant(
        name="automatic",
        prompt_cache_key_supplied=False,
        samples=[_sample(1, cached_tokens=0, latency_ms=1000), failed],
    )

    assert result["evaluation_complete"] is False
    assert result["failed_sample_count"] == 1
    assert result["completion_reasons"] == [
        "expected 2 successful samples, got 1",
        "expected 1 warm samples, got 0",
    ]


def test_summary_fails_closed_for_missing_usage_or_false_cold_start() -> None:
    missing_usage = _sample(2, cached_tokens=1600, latency_ms=500)
    missing_usage["cached_input_tokens"] = None
    result = summarize_prompt_cache_variant(
        name="keyed",
        prompt_cache_key_supplied=True,
        samples=[
            _sample(1, cached_tokens=128, latency_ms=1000),
            missing_usage,
        ],
    )

    assert result["evaluation_complete"] is False
    assert result["completion_reasons"] == [
        "1 successful samples lacked latency or token usage",
        "the isolated cold sample unexpectedly reported cached tokens",
    ]


def test_variant_comparison_reports_keyed_differences() -> None:
    keyed = summarize_prompt_cache_variant(
        name="keyed",
        prompt_cache_key_supplied=True,
        samples=[
            _sample(1, cached_tokens=0, latency_ms=1000),
            _sample(2, cached_tokens=1600, latency_ms=500),
        ],
    )
    automatic = summarize_prompt_cache_variant(
        name="automatic",
        prompt_cache_key_supplied=False,
        samples=[
            _sample(1, cached_tokens=0, latency_ms=1000),
            _sample(2, cached_tokens=800, latency_ms=750),
        ],
    )

    comparison = compare_prompt_cache_variants(keyed, automatic)

    assert comparison["keyed_minus_automatic_cache_hit_rate"] == 0.0
    assert comparison["keyed_minus_automatic_cached_token_ratio"] == 0.4
    assert comparison["keyed_to_automatic_warm_latency_ratio"] == 0.666667
    assert comparison["keyed_to_automatic_input_cost_ratio"] < 1


def test_committed_live_evaluation_is_complete_and_content_free() -> None:
    artifact_path = (
        Path(__file__).resolve().parents[2]
        / "docs"
        / "evaluation"
        / "prompt_caching_evaluation_2026-08-05.json"
    )
    artifact_text = artifact_path.read_text(encoding="utf-8")
    artifact = json.loads(artifact_text)

    assert artifact["evaluation_complete"] is True
    assert artifact["request_count"] == 16
    assert artifact["content_policy"] == {
        "cache_keys_in_artifact": False,
        "candidate_or_cv_data_used": False,
        "prompts_in_artifact": False,
        "recorded_fields": (
            "variant, phase, sample index, latency, token usage, estimated "
            "cost, cache-hit aggregates, and completion status"
        ),
        "responses_in_artifact": False,
        "synthetic_input_only": True,
    }
    assert all(
        variant["warm"]["cache_hit_count"] == 7
        for variant in artifact["variants"]
    )
    assert "Evaluation isolation marker" not in artifact_text
    assert "jja-cache-eval-" not in artifact_text
