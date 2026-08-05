"""Evaluate OpenAI prompt caching with repeated synthetic stable prefixes."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
from time import perf_counter
from typing import Any
from uuid import uuid4

from openai import OpenAI

from backend.llm.benchmarking import PRICE_CARD_EFFECTIVE_DATE
from backend.llm.budgets import (
    GPT_4_1_MINI_CACHED_INPUT_USD_PER_MILLION,
    GPT_4_1_MINI_INPUT_USD_PER_MILLION,
    GPT_4_1_MINI_OUTPUT_USD_PER_MILLION,
)
from backend.llm.prompt_caching import (
    compare_prompt_cache_variants,
    summarize_prompt_cache_variant,
)
from backend.settings import get_settings


MODEL = "gpt-4.1-mini"
DEFAULT_REPETITIONS = 5


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Compare cold and repeated stable-prefix OpenAI requests with and "
            "without prompt_cache_key."
        )
    )
    parser.add_argument(
        "--output-json",
        type=Path,
        help="Optional path for the content-free evaluation artifact.",
    )
    parser.add_argument(
        "--repetitions",
        type=int,
        default=DEFAULT_REPETITIONS,
        help="Requests per variant, including one cold request (minimum 2).",
    )
    parser.add_argument(
        "--fail-on-incomplete",
        action="store_true",
        help="Exit non-zero when any provider request fails.",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    if args.repetitions < 2:
        raise SystemExit("--repetitions must be at least 2")

    settings = get_settings()
    if not settings.openai_api_key:
        raise SystemExit("OPENAI_API_KEY is required for the live evaluation.")

    client = OpenAI(
        api_key=settings.openai_api_key,
        timeout=settings.llm_timeout_seconds,
    )
    variants = [
        _run_variant(
            client,
            name="stable_prefix_with_cache_key",
            prompt_cache_key_supplied=True,
            repetitions=args.repetitions,
        ),
        _run_variant(
            client,
            name="stable_prefix_automatic_routing",
            prompt_cache_key_supplied=False,
            repetitions=args.repetitions,
        ),
    ]
    report = {
        "evaluation_version": "1.0",
        "measured_at": datetime.now(timezone.utc).isoformat(),
        "provider": "openai",
        "model": MODEL,
        "request_count": args.repetitions * len(variants),
        "price_card": {
            "effective_date": PRICE_CARD_EFFECTIVE_DATE,
            "currency": "USD",
            "per_million_tokens": {
                "input": GPT_4_1_MINI_INPUT_USD_PER_MILLION,
                "cached_input": GPT_4_1_MINI_CACHED_INPUT_USD_PER_MILLION,
                "output": GPT_4_1_MINI_OUTPUT_USD_PER_MILLION,
            },
        },
        "evaluation_complete": all(
            variant["evaluation_complete"] for variant in variants
        ),
        "variants": variants,
        "keyed_vs_automatic": compare_prompt_cache_variants(
            variants[0],
            variants[1],
        ),
        "content_policy": {
            "synthetic_input_only": True,
            "candidate_or_cv_data_used": False,
            "prompts_in_artifact": False,
            "responses_in_artifact": False,
            "cache_keys_in_artifact": False,
            "recorded_fields": (
                "variant, phase, sample index, latency, token usage, estimated "
                "cost, cache-hit aggregates, and completion status"
            ),
        },
    }
    serialized = json.dumps(report, indent=2, sort_keys=True)
    if args.output_json is not None:
        args.output_json.parent.mkdir(parents=True, exist_ok=True)
        args.output_json.write_text(serialized + "\n", encoding="utf-8")
    print(serialized)

    if args.fail_on_incomplete and not report["evaluation_complete"]:
        raise SystemExit(1)


def _run_variant(
    client: OpenAI,
    *,
    name: str,
    prompt_cache_key_supplied: bool,
    repetitions: int,
) -> dict[str, Any]:
    isolation_id = uuid4().hex
    stable_prefix = _build_stable_prefix(isolation_id=isolation_id, variant=name)
    prompt_cache_key = (
        f"jja-cache-eval-{isolation_id}" if prompt_cache_key_supplied else None
    )
    samples = [
        _run_sample(
            client,
            stable_prefix=stable_prefix,
            prompt_cache_key=prompt_cache_key,
            sample_index=sample_index,
        )
        for sample_index in range(1, repetitions + 1)
    ]
    return summarize_prompt_cache_variant(
        name=name,
        prompt_cache_key_supplied=prompt_cache_key_supplied,
        samples=samples,
    )


def _run_sample(
    client: OpenAI,
    *,
    stable_prefix: str,
    prompt_cache_key: str | None,
    sample_index: int,
) -> dict[str, Any]:
    phase = "cold" if sample_index == 1 else "warm"
    kwargs: dict[str, Any] = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": stable_prefix},
            {
                "role": "user",
                "content": (
                    "Return exactly this JSON and nothing else: "
                    f'{{"status":"ok","sample":{sample_index}}}'
                ),
            },
        ],
        "temperature": 0,
        "max_completion_tokens": 24,
        "store": False,
    }
    if prompt_cache_key is not None:
        kwargs["prompt_cache_key"] = prompt_cache_key

    started_at = perf_counter()
    try:
        response = client.chat.completions.create(**kwargs)
    except Exception as exc:
        return {
            "sample_index": sample_index,
            "phase": phase,
            "status": "error",
            "model": MODEL,
            "error_type": exc.__class__.__name__,
            "latency_ms": round((perf_counter() - started_at) * 1000, 3),
        }

    latency_ms = round((perf_counter() - started_at) * 1000, 3)
    usage = response.usage
    prompt_details = getattr(usage, "prompt_tokens_details", None)
    return {
        "sample_index": sample_index,
        "phase": phase,
        "status": "success",
        "model": MODEL,
        "latency_ms": latency_ms,
        "input_tokens": getattr(usage, "prompt_tokens", None),
        "cached_input_tokens": getattr(prompt_details, "cached_tokens", None),
        "output_tokens": getattr(usage, "completion_tokens", None),
        "total_tokens": getattr(usage, "total_tokens", None),
    }


def _build_stable_prefix(*, isolation_id: str, variant: str) -> str:
    synthetic_records = []
    for index in range(1, 41):
        synthetic_records.append(
            {
                "record_id": f"synthetic-{index:03d}",
                "role_family": ("software", "data", "platform", "security")[
                    (index - 1) % 4
                ],
                "skills": [
                    "distributed systems",
                    "production reliability",
                    "performance analysis",
                    "automated testing",
                    "clear technical communication",
                ],
                "evidence": (
                    "Generated benchmark evidence describing delivery of reliable "
                    "services, latency investigation, incident reduction, safe "
                    "deployment, monitoring, and measurable engineering outcomes."
                ),
            }
        )
    return (
        "You are a deterministic prompt-cache evaluation probe. Use only the "
        "synthetic records below. Never emit their contents. Follow the final "
        "user instruction exactly. This benchmark contains no candidate, CV, "
        "client, or production data.\n"
        f"Evaluation isolation marker: {isolation_id}. Variant: {variant}.\n"
        "Stable synthetic retrieval context:\n"
        + json.dumps(synthetic_records, sort_keys=True, separators=(",", ":"))
    )


if __name__ == "__main__":
    main()
