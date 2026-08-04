"""Deterministic summaries and regression gates for live model benchmarks."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from math import ceil
from typing import Any

from backend.llm.budgets import (
    GPT_4_1_MINI_CACHED_INPUT_USD_PER_MILLION,
    GPT_4_1_MINI_INPUT_USD_PER_MILLION,
    GPT_4_1_MINI_OUTPUT_USD_PER_MILLION,
    TEXT_EMBEDDING_3_LARGE_INPUT_USD_PER_MILLION,
)


PRICE_CARD_EFFECTIVE_DATE = "2026-08-03"


@dataclass(frozen=True, slots=True)
class BenchmarkScenario:
    """Content-free definition and alert ceilings for one benchmark workload."""

    name: str
    operation: str
    workload: str
    repetitions: int
    concurrency: int
    input_characters: int
    input_items: int
    max_output_tokens: int | None
    max_p95_latency_ms: float
    max_average_cost_usd: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def estimate_openai_cost_usd(measurement: dict[str, Any]) -> float | None:
    """Estimate one request cost from provider-returned usage and versioned rates."""

    model = measurement.get("model")
    input_tokens = _optional_non_negative_int(measurement.get("input_tokens"))
    cached_input_tokens = _optional_non_negative_int(
        measurement.get("cached_input_tokens")
    )
    output_tokens = _optional_non_negative_int(measurement.get("output_tokens"))

    if model == "gpt-4.1-mini":
        if input_tokens is None or output_tokens is None:
            return None
        bounded_cached_tokens = min(cached_input_tokens or 0, input_tokens)
        uncached_input_tokens = input_tokens - bounded_cached_tokens
        cost = (
            uncached_input_tokens * GPT_4_1_MINI_INPUT_USD_PER_MILLION
            + bounded_cached_tokens * GPT_4_1_MINI_CACHED_INPUT_USD_PER_MILLION
            + output_tokens * GPT_4_1_MINI_OUTPUT_USD_PER_MILLION
        ) / 1_000_000
        return round(cost, 9)

    if model == "text-embedding-3-large":
        if input_tokens is None:
            return None
        return round(
            input_tokens * TEXT_EMBEDDING_3_LARGE_INPUT_USD_PER_MILLION / 1_000_000,
            9,
        )

    return None


def summarize_benchmark_scenario(
    scenario: BenchmarkScenario,
    measurements: list[dict[str, Any]],
) -> dict[str, Any]:
    """Return a content-free aggregate with fixed latency and cost gates."""

    samples: list[dict[str, Any]] = []
    for measurement in measurements:
        sample = dict(measurement)
        sample["estimated_cost_usd"] = estimate_openai_cost_usd(measurement)
        samples.append(sample)

    successful_samples = [
        sample for sample in samples if sample.get("status") == "success"
    ]
    latencies = [
        float(sample["end_to_end_ms"])
        for sample in successful_samples
        if isinstance(sample.get("end_to_end_ms"), (int, float))
    ]
    costs = [
        float(sample["estimated_cost_usd"])
        for sample in successful_samples
        if isinstance(sample.get("estimated_cost_usd"), (int, float))
    ]
    p50_latency_ms = _nearest_rank_percentile(latencies, 0.50)
    p95_latency_ms = _nearest_rank_percentile(latencies, 0.95)
    average_cost_usd = round(sum(costs) / len(costs), 9) if costs else None
    total_cost_usd = round(sum(costs), 9) if costs else None
    reasons: list[str] = []

    if len(successful_samples) != scenario.repetitions:
        reasons.append(
            f"expected {scenario.repetitions} successful samples, got "
            f"{len(successful_samples)}"
        )
    if p95_latency_ms is None:
        reasons.append("no successful latency samples were returned")
    elif p95_latency_ms > scenario.max_p95_latency_ms:
        reasons.append(
            f"p95 latency {p95_latency_ms:.3f} ms exceeded "
            f"{scenario.max_p95_latency_ms:.3f} ms"
        )
    if average_cost_usd is None:
        reasons.append("provider usage was unavailable for cost estimation")
    elif average_cost_usd > scenario.max_average_cost_usd:
        reasons.append(
            f"average cost ${average_cost_usd:.9f} exceeded "
            f"${scenario.max_average_cost_usd:.9f}"
        )

    return {
        "definition": scenario.to_dict(),
        "summary": {
            "sample_count": len(samples),
            "successful_sample_count": len(successful_samples),
            "failed_sample_count": len(samples) - len(successful_samples),
            "p50_latency_ms": p50_latency_ms,
            "p95_latency_ms": p95_latency_ms,
            "maximum_latency_ms": round(max(latencies), 3) if latencies else None,
            "average_cost_usd": average_cost_usd,
            "total_cost_usd": total_cost_usd,
            "total_input_tokens": _sum_optional_ints(
                successful_samples,
                "input_tokens",
            ),
            "total_cached_input_tokens": _sum_optional_ints(
                successful_samples,
                "cached_input_tokens",
            ),
            "total_output_tokens": _sum_optional_ints(
                successful_samples,
                "output_tokens",
            ),
        },
        "regression_gate": {
            "passed": not reasons,
            "reasons": reasons,
        },
        "samples": samples,
    }


def compare_benchmark_reports(
    current_scenarios: list[dict[str, Any]],
    baseline_scenarios: list[dict[str, Any]],
    *,
    maximum_latency_ratio: float = 1.25,
    maximum_cost_ratio: float = 1.10,
) -> dict[str, Any]:
    """Compare like-for-like scenario aggregates with a versioned baseline."""

    baseline_by_name = {
        scenario.get("definition", {}).get("name"): scenario
        for scenario in baseline_scenarios
    }
    comparisons: list[dict[str, Any]] = []
    for current in current_scenarios:
        name = current.get("definition", {}).get("name")
        baseline = baseline_by_name.get(name)
        if not isinstance(name, str) or baseline is None:
            comparisons.append(
                {
                    "scenario": name,
                    "comparable": False,
                    "passed": False,
                    "reasons": ["matching baseline scenario was not found"],
                }
            )
            continue

        current_summary = current.get("summary", {})
        baseline_summary = baseline.get("summary", {})
        latency_ratio = _ratio(
            current_summary.get("p95_latency_ms"),
            baseline_summary.get("p95_latency_ms"),
        )
        cost_ratio = _ratio(
            current_summary.get("average_cost_usd"),
            baseline_summary.get("average_cost_usd"),
        )
        reasons: list[str] = []
        if latency_ratio is None:
            reasons.append("p95 latency was not comparable")
        elif latency_ratio > maximum_latency_ratio:
            reasons.append(
                f"p95 latency ratio {latency_ratio:.3f} exceeded "
                f"{maximum_latency_ratio:.3f}"
            )
        if cost_ratio is None:
            reasons.append("average cost was not comparable")
        elif cost_ratio > maximum_cost_ratio:
            reasons.append(
                f"average cost ratio {cost_ratio:.3f} exceeded {maximum_cost_ratio:.3f}"
            )
        comparisons.append(
            {
                "scenario": name,
                "comparable": True,
                "passed": not reasons,
                "p95_latency_ratio": latency_ratio,
                "average_cost_ratio": cost_ratio,
                "reasons": reasons,
            }
        )

    return {
        "maximum_latency_ratio": maximum_latency_ratio,
        "maximum_cost_ratio": maximum_cost_ratio,
        "passed": all(comparison["passed"] for comparison in comparisons),
        "comparisons": comparisons,
    }


def _nearest_rank_percentile(
    values: list[float],
    percentile: float,
) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = max(0, ceil(len(ordered) * percentile) - 1)
    return round(ordered[index], 3)


def _optional_non_negative_int(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return max(0, int(value))


def _sum_optional_ints(samples: list[dict[str, Any]], key: str) -> int | None:
    values = [
        value
        for sample in samples
        if (value := _optional_non_negative_int(sample.get(key))) is not None
    ]
    return sum(values) if values else None


def _ratio(current: Any, baseline: Any) -> float | None:
    if (
        isinstance(current, bool)
        or isinstance(baseline, bool)
        or not isinstance(current, (int, float))
        or not isinstance(baseline, (int, float))
        or baseline <= 0
    ):
        return None
    return round(float(current) / float(baseline), 6)


__all__ = [
    "BenchmarkScenario",
    "PRICE_CARD_EFFECTIVE_DATE",
    "compare_benchmark_reports",
    "estimate_openai_cost_usd",
    "summarize_benchmark_scenario",
]
