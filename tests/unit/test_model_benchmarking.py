from __future__ import annotations

import json
from pathlib import Path

from backend.llm.benchmarking import (
    BenchmarkScenario,
    compare_benchmark_reports,
    estimate_openai_cost_usd,
    summarize_benchmark_scenario,
)


def _scenario(**overrides: object) -> BenchmarkScenario:
    values: dict[str, object] = {
        "name": "chat_short",
        "operation": "chat",
        "workload": "short_chat",
        "repetitions": 3,
        "concurrency": 1,
        "input_characters": 100,
        "input_items": 2,
        "max_output_tokens": 32,
        "max_p95_latency_ms": 500,
        "max_average_cost_usd": 0.001,
    }
    values.update(overrides)
    return BenchmarkScenario(**values)  # type: ignore[arg-type]


def test_estimate_openai_cost_uses_cached_and_uncached_chat_rates() -> None:
    cost = estimate_openai_cost_usd(
        {
            "model": "gpt-4.1-mini",
            "input_tokens": 1000,
            "cached_input_tokens": 400,
            "output_tokens": 100,
        }
    )

    assert cost == 0.00044


def test_estimate_openai_cost_supports_embeddings_and_missing_usage() -> None:
    assert (
        estimate_openai_cost_usd(
            {"model": "text-embedding-3-large", "input_tokens": 1000}
        )
        == 0.00013
    )
    assert (
        estimate_openai_cost_usd(
            {"model": "gpt-4.1-mini", "input_tokens": None, "output_tokens": 2}
        )
        is None
    )


def test_summarize_benchmark_scenario_applies_nearest_rank_gates() -> None:
    measurements = [
        {
            "status": "success",
            "model": "gpt-4.1-mini",
            "end_to_end_ms": latency,
            "input_tokens": 20,
            "cached_input_tokens": 0,
            "output_tokens": 2,
        }
        for latency in (100, 200, 300)
    ]

    result = summarize_benchmark_scenario(_scenario(), measurements)

    assert result["summary"]["p50_latency_ms"] == 200
    assert result["summary"]["p95_latency_ms"] == 300
    assert result["summary"]["total_input_tokens"] == 60
    assert result["regression_gate"] == {"passed": True, "reasons": []}
    assert all("estimated_cost_usd" in sample for sample in result["samples"])


def test_summarize_benchmark_scenario_fails_closed_on_errors_and_cost() -> None:
    scenario = _scenario(
        repetitions=2,
        max_p95_latency_ms=100,
        max_average_cost_usd=0.000001,
    )
    measurements = [
        {
            "status": "success",
            "model": "gpt-4.1-mini",
            "end_to_end_ms": 200,
            "input_tokens": 100,
            "cached_input_tokens": 0,
            "output_tokens": 10,
        },
        {
            "status": "error",
            "model": "gpt-4.1-mini",
            "end_to_end_ms": 50,
            "error_type": "TimeoutError",
        },
    ]

    result = summarize_benchmark_scenario(scenario, measurements)

    assert result["regression_gate"]["passed"] is False
    assert len(result["regression_gate"]["reasons"]) == 3


def test_compare_benchmark_reports_flags_relative_latency_regression() -> None:
    baseline = [
        {
            "definition": {"name": "chat_short"},
            "summary": {"p95_latency_ms": 100, "average_cost_usd": 0.001},
        }
    ]
    current = [
        {
            "definition": {"name": "chat_short"},
            "summary": {"p95_latency_ms": 140, "average_cost_usd": 0.00105},
        }
    ]

    result = compare_benchmark_reports(current, baseline)

    assert result["passed"] is False
    assert result["comparisons"][0]["p95_latency_ratio"] == 1.4
    assert result["comparisons"][0]["average_cost_ratio"] == 1.05
    assert result["comparisons"][0]["reasons"] == [
        "p95 latency ratio 1.400 exceeded 1.250"
    ]


def test_committed_live_baseline_is_content_free_and_passes_every_gate() -> None:
    repository_root = Path(__file__).resolve().parents[2]
    artifact = json.loads(
        (
            repository_root
            / "docs"
            / "evaluation"
            / "model_workload_benchmark_2026-08-04.json"
        ).read_text(encoding="utf-8")
    )

    assert artifact["overall_passed"] is True
    assert artifact["content_policy"] == {
        "candidate_or_cv_data_used": False,
        "prompts_in_artifact": False,
        "recorded_fields": (
            "scenario shape, concurrency, timings, token usage, estimated cost, "
            "run identifiers, and pass/fail gates"
        ),
        "responses_in_artifact": False,
    }
    assert {scenario["definition"]["name"] for scenario in artifact["scenarios"]} == {
        "chat_short_serial_32",
        "chat_long_serial_1200",
        "chat_short_concurrency_2_32",
        "embedding_query_serial",
        "embedding_batch_25_serial",
    }
    assert all(
        scenario["regression_gate"]["passed"] for scenario in artifact["scenarios"]
    )
