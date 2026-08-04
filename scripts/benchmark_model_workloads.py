"""Benchmark synthetic short, long, bounded-output, and concurrent model calls."""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import json
from pathlib import Path
from time import perf_counter
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from backend.llm.benchmarking import (
    BenchmarkScenario,
    PRICE_CARD_EFFECTIVE_DATE,
    compare_benchmark_reports,
    summarize_benchmark_scenario,
)
from backend.llm.budgets import (
    GPT_4_1_MINI_CACHED_INPUT_USD_PER_MILLION,
    GPT_4_1_MINI_INPUT_USD_PER_MILLION,
    GPT_4_1_MINI_OUTPUT_USD_PER_MILLION,
    TEXT_EMBEDDING_3_LARGE_INPUT_USD_PER_MILLION,
)
from backend.llm.models import ModelProfile, ModelProvider, ModelPurpose
from backend.llm.providers import build_langchain_chat_model
from backend.llm.telemetry import invoke_with_model_telemetry
from backend.services.document_embeddings import embed_texts_with_telemetry
from backend.settings import get_settings


SHORT_SYSTEM_PROMPT = "You are a deterministic API latency probe."
SHORT_USER_PROMPT = 'Return exactly this JSON object and nothing else: {"status":"ok"}'
LONG_SYSTEM_PROMPT = (
    "You are a recruitment ranking benchmark. Use only the supplied synthetic "
    "candidate evidence. Return concise JSON containing the five strongest "
    "synthetic candidate IDs and one evidence-backed reason for each."
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Run bounded, synthetic model workloads and evaluate latency/cost gates."
        )
    )
    parser.add_argument(
        "--output-json",
        type=Path,
        help="Optional path for the content-free benchmark artifact.",
    )
    parser.add_argument(
        "--baseline-json",
        type=Path,
        help="Optional earlier artifact for relative regression comparison.",
    )
    parser.add_argument(
        "--fail-on-regression",
        action="store_true",
        help="Exit non-zero if a fixed or relative regression gate fails.",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    settings = get_settings()
    long_user_prompt = _build_long_user_prompt()
    embedding_batch = _build_embedding_batch()
    scenarios = _build_scenarios(
        long_user_prompt=long_user_prompt,
        embedding_batch=embedding_batch,
    )

    scenario_results = [
        _run_scenario(
            scenario,
            long_user_prompt=long_user_prompt,
            embedding_batch=embedding_batch,
            embedding_model=settings.openai_embedding_model,
        )
        for scenario in scenarios
    ]
    baseline_comparison: dict[str, Any] | None = None
    if args.baseline_json is not None:
        baseline = json.loads(args.baseline_json.read_text(encoding="utf-8"))
        baseline_comparison = compare_benchmark_reports(
            scenario_results,
            baseline.get("scenarios", []),
        )

    fixed_gates_passed = all(
        result["regression_gate"]["passed"] for result in scenario_results
    )
    overall_passed = fixed_gates_passed and (
        baseline_comparison is None or baseline_comparison["passed"]
    )
    report = {
        "benchmark_version": "1.0",
        "measured_at": datetime.now(timezone.utc).isoformat(),
        "representative_production_data": False,
        "synthetic_recruitment_shaped_inputs": True,
        "provider": "openai",
        "chat_model": "gpt-4.1-mini",
        "embedding_model": settings.openai_embedding_model,
        "price_card": {
            "effective_date": PRICE_CARD_EFFECTIVE_DATE,
            "currency": "USD",
            "per_million_tokens": {
                "gpt-4.1-mini_input": GPT_4_1_MINI_INPUT_USD_PER_MILLION,
                "gpt-4.1-mini_cached_input": (
                    GPT_4_1_MINI_CACHED_INPUT_USD_PER_MILLION
                ),
                "gpt-4.1-mini_output": GPT_4_1_MINI_OUTPUT_USD_PER_MILLION,
                "text-embedding-3-large_input": (
                    TEXT_EMBEDDING_3_LARGE_INPUT_USD_PER_MILLION
                ),
            },
        },
        "fixed_regression_gates_passed": fixed_gates_passed,
        "baseline_comparison": baseline_comparison,
        "overall_passed": overall_passed,
        "scenarios": scenario_results,
        "content_policy": {
            "prompts_in_artifact": False,
            "responses_in_artifact": False,
            "candidate_or_cv_data_used": False,
            "recorded_fields": (
                "scenario shape, concurrency, timings, token usage, estimated cost, "
                "run identifiers, and pass/fail gates"
            ),
        },
    }

    serialized_report = json.dumps(report, indent=2, sort_keys=True)
    if args.output_json is not None:
        args.output_json.parent.mkdir(parents=True, exist_ok=True)
        args.output_json.write_text(serialized_report + "\n", encoding="utf-8")
    print(serialized_report)

    if args.fail_on_regression and not overall_passed:
        raise SystemExit(1)


def _build_scenarios(
    *,
    long_user_prompt: str,
    embedding_batch: list[str],
) -> list[BenchmarkScenario]:
    short_characters = len(SHORT_SYSTEM_PROMPT) + len(SHORT_USER_PROMPT)
    long_characters = len(LONG_SYSTEM_PROMPT) + len(long_user_prompt)
    embedding_batch_characters = sum(len(item) for item in embedding_batch)
    return [
        BenchmarkScenario(
            name="chat_short_serial_32",
            operation="chat",
            workload="short_chat",
            repetitions=2,
            concurrency=1,
            input_characters=short_characters,
            input_items=2,
            max_output_tokens=32,
            max_p95_latency_ms=8_000,
            max_average_cost_usd=0.001,
        ),
        BenchmarkScenario(
            name="chat_long_serial_1200",
            operation="chat",
            workload="long_chat",
            repetitions=2,
            concurrency=1,
            input_characters=long_characters,
            input_items=2,
            max_output_tokens=1_200,
            max_p95_latency_ms=30_000,
            max_average_cost_usd=0.02,
        ),
        BenchmarkScenario(
            name="chat_short_concurrency_2_32",
            operation="chat",
            workload="short_chat",
            repetitions=4,
            concurrency=2,
            input_characters=short_characters,
            input_items=2,
            max_output_tokens=32,
            max_p95_latency_ms=12_000,
            max_average_cost_usd=0.001,
        ),
        BenchmarkScenario(
            name="embedding_query_serial",
            operation="embedding",
            workload="embedding_query",
            repetitions=2,
            concurrency=1,
            input_characters=len("senior rust engineer low-latency trading"),
            input_items=1,
            max_output_tokens=None,
            max_p95_latency_ms=8_000,
            max_average_cost_usd=0.001,
        ),
        BenchmarkScenario(
            name="embedding_batch_25_serial",
            operation="embedding",
            workload="embedding_batch",
            repetitions=2,
            concurrency=1,
            input_characters=embedding_batch_characters,
            input_items=len(embedding_batch),
            max_output_tokens=None,
            max_p95_latency_ms=15_000,
            max_average_cost_usd=0.01,
        ),
    ]


def _run_scenario(
    scenario: BenchmarkScenario,
    *,
    long_user_prompt: str,
    embedding_batch: list[str],
    embedding_model: str,
) -> dict[str, Any]:
    measurements: list[tuple[int, dict[str, Any]]] = []
    with ThreadPoolExecutor(max_workers=scenario.concurrency) as executor:
        futures = {
            executor.submit(
                _run_sample,
                scenario,
                sample_index,
                long_user_prompt=long_user_prompt,
                embedding_batch=embedding_batch,
                embedding_model=embedding_model,
            ): sample_index
            for sample_index in range(1, scenario.repetitions + 1)
        }
        for future in as_completed(futures):
            measurements.append(future.result())

    ordered_measurements = [
        {**measurement, "sample_index": sample_index}
        for sample_index, measurement in sorted(measurements)
    ]
    return summarize_benchmark_scenario(scenario, ordered_measurements)


def _run_sample(
    scenario: BenchmarkScenario,
    sample_index: int,
    *,
    long_user_prompt: str,
    embedding_batch: list[str],
    embedding_model: str,
) -> tuple[int, dict[str, Any]]:
    started_at = perf_counter()
    try:
        if scenario.operation == "chat":
            measurement = _run_chat_sample(scenario, long_user_prompt)
        else:
            measurement = _run_embedding_sample(
                scenario,
                embedding_batch=embedding_batch,
            )
        return sample_index, measurement
    except Exception as exc:
        return sample_index, {
            "workflow": f"benchmark_{scenario.name}",
            "provider": "openai",
            "model": (
                "gpt-4.1-mini" if scenario.operation == "chat" else embedding_model
            ),
            "operation": scenario.operation,
            "status": "error",
            "error_type": exc.__class__.__name__,
            "end_to_end_ms": round((perf_counter() - started_at) * 1000, 3),
        }


def _run_chat_sample(
    scenario: BenchmarkScenario,
    long_user_prompt: str,
) -> dict[str, Any]:
    profile = ModelProfile(
        provider=ModelProvider.OPENAI,
        model_name="gpt-4.1-mini",
        purpose=ModelPurpose.REASONING,
        temperature=0,
        max_output_tokens=scenario.max_output_tokens or 32,
    )
    chat_model = build_langchain_chat_model(profile=profile)
    if scenario.workload == "long_chat":
        messages = [
            SystemMessage(content=LONG_SYSTEM_PROMPT),
            HumanMessage(content=long_user_prompt),
        ]
    else:
        messages = [
            SystemMessage(content=SHORT_SYSTEM_PROMPT),
            HumanMessage(content=SHORT_USER_PROMPT),
        ]
    _, measurement = invoke_with_model_telemetry(
        chat_model,
        messages,
        workflow=f"benchmark_{scenario.name}",
        provider=profile.provider.value,
        model=profile.model_name,
    )
    return measurement


def _run_embedding_sample(
    scenario: BenchmarkScenario,
    *,
    embedding_batch: list[str],
) -> dict[str, Any]:
    texts = (
        ["senior rust engineer low-latency trading"]
        if scenario.workload == "embedding_query"
        else embedding_batch
    )
    _, measurement = embed_texts_with_telemetry(
        texts,
        workflow=f"benchmark_{scenario.name}",
    )
    if measurement is None:
        raise RuntimeError("Embedding telemetry was unexpectedly unavailable.")
    return measurement


def _build_long_user_prompt() -> str:
    candidates = []
    role_families = ("Rust", "Python", "C++", "Java", "Platform")
    for index in range(1, 26):
        family = role_families[(index - 1) % len(role_families)]
        candidates.append(
            {
                "candidate_id": f"synthetic-{index:03d}",
                "current_title": f"Senior {family} Engineer",
                "skills": [
                    family,
                    "distributed systems",
                    "cloud infrastructure",
                    "observability",
                    "performance tuning",
                    "automated testing",
                ],
                "evidence": (
                    f"Synthetic candidate {index:03d} designed fault-tolerant "
                    "services, investigated latency regressions, reduced "
                    "operational toil, and documented measurable delivery "
                    "outcomes. This is generated benchmark text, not a person."
                ),
            }
        )
    role_brief = {
        "title": "Synthetic senior low-latency platform engineer",
        "requirements": [
            "systems programming",
            "distributed service design",
            "latency investigation",
            "production reliability",
            "clear evidence of delivery",
        ],
    }
    return (
        "<synthetic_role>\n"
        + json.dumps(role_brief, ensure_ascii=False)
        + "\n</synthetic_role>\n<synthetic_candidates>\n"
        + json.dumps(candidates, ensure_ascii=False)
        + "\n</synthetic_candidates>"
    )


def _build_embedding_batch() -> list[str]:
    return [
        (
            f"Synthetic profile block {index:02d}. Senior software engineer with "
            "evidence in distributed systems, cloud platforms, performance "
            "analysis, observability, incident response, automated testing, and "
            "reliable delivery. Generated only for provider latency benchmarking. "
        )
        * 4
        for index in range(1, 26)
    ]


if __name__ == "__main__":
    main()
