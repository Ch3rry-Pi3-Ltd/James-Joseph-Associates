"""
Run a batch of live JobAdder resume-extraction flows from the command line.

Why this script exists
----------------------
The single-candidate runner proves the extraction pipeline works for one
record. The next practical question is different:

    "How does the quality gate behave across a small real batch?"

This script answers that by reusing the same extraction and fallback logic
already present in `scripts/run_resume_extraction.py`, while adding:

- candidate-list handling
- per-candidate JSON output
- batch-level success/failure tracking
- one summary file for later review

What this script does
---------------------
It performs the following steps for each candidate:

1. run the first-pass extraction
2. apply the deterministic quality gate
3. optionally rerun with the stronger fallback model
4. write one JSON result file
5. record batch success/failure metadata

What this script does not do
----------------------------
It does not:

- write accepted structured data into the database
- define the final evaluation threshold policy
- replace later Supabase persistence or dashboards

This script is for batch calibration and inspection.

Examples
--------
Run three candidates through the quality-gated batch flow:

    uv run python scripts/run_resume_extraction_batch.py ^
        --jobadder-account 2236 ^
        --candidate-id 16496678 ^
        --candidate-id 12345678 ^
        --candidate-id 87654321

Run a batch from a file of candidate IDs:

    uv run python scripts/run_resume_extraction_batch.py ^
        --jobadder-account 2236 ^
        --candidate-ids-file temp\\candidate_ids.txt

In plain language:

- provide a batch of candidate IDs
- reuse the same extraction path as the single-run script
- keep the outputs separate for later scoring review
"""
# ruff: noqa: E402

from __future__ import annotations

import argparse
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
import re
import sys
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.llm.models import ModelProvider
from backend.llm.providers import LLMProviderConfigurationError
from backend.services.resume_extraction import ResumeExtractionError
from scripts.run_resume_extraction import (
    DEFAULT_QUALITY_GATE_FALLBACK_MODEL_NAME,
    DEFAULT_RESUME_EXTRACTION_MODEL_PROFILE,
    append_jsonl_log,
    build_json_ready_result,
    run_live_resume_extraction_with_optional_quality_gate,
    write_json_output,
)


def build_argument_parser() -> argparse.ArgumentParser:
    """
    Build the CLI argument parser for the batch extraction script.

    Example
    -------
    A caller can provide candidate IDs directly:

        --candidate-id 16496678 --candidate-id 12345678

    or through a file:

        --candidate-ids-file temp\\candidate_ids.txt
    """

    parser = argparse.ArgumentParser(
        description=(
            "Run a batch of live JobAdder resume-extraction flows and save "
            "one result JSON per candidate."
        )
    )
    parser.add_argument(
        "--jobadder-account",
        type=int,
        required=True,
        help="JobAdder account identifier used to resolve the stored OAuth connection.",
    )
    parser.add_argument(
        "--candidate-id",
        action="append",
        type=int,
        default=[],
        help="Candidate ID to include in the batch. Repeat the flag for multiple candidates.",
    )
    parser.add_argument(
        "--candidate-ids-file",
        type=Path,
        default=None,
        help="Optional file containing candidate IDs separated by commas, spaces, or newlines.",
    )
    parser.add_argument(
        "--provider",
        choices=[ModelProvider.OPENAI.value, ModelProvider.OPENROUTER.value],
        default=DEFAULT_RESUME_EXTRACTION_MODEL_PROFILE.provider.value,
        help="Model provider to use. The quality-gate fallback flow currently supports OpenAI only.",
    )
    parser.add_argument(
        "--model-name",
        default=None,
        help=(
            "Explicit first-pass model name. If omitted and quality gating is "
            "enabled, the batch defaults to gpt-4.1-mini."
        ),
    )
    parser.add_argument(
        "--temperature",
        type=float,
        default=DEFAULT_RESUME_EXTRACTION_MODEL_PROFILE.temperature,
        help="Temperature to use for the extraction model.",
    )
    parser.add_argument(
        "--max-output-tokens",
        type=int,
        default=DEFAULT_RESUME_EXTRACTION_MODEL_PROFILE.max_output_tokens,
        help="Maximum output tokens to allow for the extraction model.",
    )
    parser.add_argument(
        "--enable-quality-gate",
        action="store_true",
        help="Enable the deterministic quality gate plus fallback model routing.",
    )
    parser.add_argument(
        "--quality-pass-threshold",
        type=int,
        default=80,
        help="Score at or above this threshold is considered a pass.",
    )
    parser.add_argument(
        "--quality-rerun-threshold",
        type=int,
        default=65,
        help="Score below this threshold triggers the fallback model.",
    )
    parser.add_argument(
        "--fallback-model-name",
        default=DEFAULT_QUALITY_GATE_FALLBACK_MODEL_NAME,
        help="Fallback model name to use when the quality score requests a rerun.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("temp/resume_extraction_batch"),
        help="Directory to store per-candidate JSON results and the batch summary.",
    )
    parser.add_argument(
        "--quality-log-jsonl",
        type=Path,
        default=None,
        help="Optional JSONL path for quality-gate logs. Defaults inside the batch output directory.",
    )
    parser.add_argument(
        "--include-prompts",
        action="store_true",
        help="Include prompt material in each saved result JSON.",
    )
    parser.add_argument(
        "--stop-on-error",
        action="store_true",
        help="Stop the batch immediately when one candidate fails.",
    )
    return parser


def load_candidate_ids(
    *,
    explicit_candidate_ids: list[int],
    candidate_ids_file: Path | None,
) -> list[int]:
    """
    Load and deduplicate candidate IDs from CLI flags and an optional file.

    Example
    -------
    A file containing:

        16496678
        12345678, 87654321

    becomes:

        [16496678, 12345678, 87654321]
    """

    candidate_ids = list(explicit_candidate_ids)

    if candidate_ids_file is not None:
        raw_text = candidate_ids_file.read_text(encoding="utf-8")
        for token in re.split(r"[\s,]+", raw_text):
            stripped_token = token.strip()
            if stripped_token == "":
                continue
            candidate_ids.append(int(stripped_token))

    deduplicated: list[int] = []
    seen: set[int] = set()

    for candidate_id in candidate_ids:
        if candidate_id in seen:
            continue
        seen.add(candidate_id)
        deduplicated.append(candidate_id)

    return deduplicated


def build_candidate_output_path(*, output_dir: Path, candidate_id: int) -> Path:
    """
    Return the per-candidate output JSON path for the batch.
    """

    return output_dir / f"candidate_{candidate_id}.json"


def build_failure_record(
    *,
    candidate_id: int,
    exc: Exception,
) -> dict[str, Any]:
    """
    Build one structured failure record for the batch summary.
    """

    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "candidate_id": candidate_id,
        "error_type": type(exc).__name__,
        "message": str(exc),
        "stage": getattr(exc, "stage", None),
        "details": getattr(exc, "details", None),
    }


def build_batch_summary(
    *,
    candidate_ids: list[int],
    successes: list[dict[str, Any]],
    failures: list[dict[str, Any]],
    output_dir: Path,
    quality_log_jsonl: Path | None,
) -> dict[str, Any]:
    """
    Build one structured batch summary payload.

    Example
    -------
    The summary includes:

        - how many candidates were requested
        - how many succeeded
        - how many failed
        - how many fallback reruns were triggered
    """

    quality_status_counts: dict[str, int] = {}
    fallback_count = 0

    for success in successes:
        quality_status = success.get("quality_status")
        if quality_status is not None:
            quality_status_counts[quality_status] = (
                quality_status_counts.get(quality_status, 0) + 1
            )
        if success.get("fallback_invoked"):
            fallback_count += 1

    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "requested_candidate_ids": candidate_ids,
        "requested_count": len(candidate_ids),
        "success_count": len(successes),
        "failure_count": len(failures),
        "fallback_count": fallback_count,
        "quality_status_counts": quality_status_counts,
        "output_dir": str(output_dir),
        "quality_log_jsonl": str(quality_log_jsonl) if quality_log_jsonl is not None else None,
        "successes": successes,
        "failures": failures,
    }


def print_batch_summary(summary: dict[str, Any]) -> None:
    """
    Print a concise human-readable batch summary.
    """

    lines = [
        "Batch resume extraction completed.",
        "",
        f"Requested candidates: {summary['requested_count']}",
        f"Successful candidates: {summary['success_count']}",
        f"Failed candidates: {summary['failure_count']}",
        f"Fallback reruns: {summary['fallback_count']}",
        f"Output directory: {summary['output_dir']}",
    ]

    quality_status_counts = summary.get("quality_status_counts", {})
    if quality_status_counts:
        lines.append(
            "Quality statuses: "
            + ", ".join(
                f"{status}={count}"
                for status, count in sorted(quality_status_counts.items())
            )
        )

    failures = summary.get("failures", [])
    if failures:
        first_failure = failures[0]
        lines.extend(
            [
                "",
                f"First failure candidate ID: {first_failure.get('candidate_id')}",
                f"First failure stage: {first_failure.get('stage')}",
                f"First failure message: {first_failure.get('message')}",
            ]
        )

    print("\n".join(lines))


def main(argv: list[str] | None = None) -> int:
    """
    Run the batch extraction CLI entrypoint.
    """

    parser = build_argument_parser()
    args = parser.parse_args(argv)

    try:
        candidate_ids = load_candidate_ids(
            explicit_candidate_ids=args.candidate_id,
            candidate_ids_file=args.candidate_ids_file,
        )
        if not candidate_ids:
            raise RuntimeError(
                "No candidate IDs were supplied. Use --candidate-id and/or "
                "--candidate-ids-file."
            )

        batch_output_dir = args.output_dir / datetime.now(timezone.utc).strftime(
            "%Y%m%dT%H%M%SZ"
        )
        batch_output_dir.mkdir(parents=True, exist_ok=True)

        if args.quality_log_jsonl is None:
            args.quality_log_jsonl = batch_output_dir / "quality_log.jsonl"

        successes: list[dict[str, Any]] = []
        failures: list[dict[str, Any]] = []

        for index, candidate_id in enumerate(candidate_ids, start=1):
            print(f"[{index}/{len(candidate_ids)}] Candidate {candidate_id}")

            candidate_args = argparse.Namespace(**deepcopy(vars(args)))
            candidate_args.candidate_id = candidate_id

            try:
                result = run_live_resume_extraction_with_optional_quality_gate(
                    candidate_args
                )
                json_payload = build_json_ready_result(
                    result=result,
                    include_prompts=args.include_prompts,
                )
                output_path = build_candidate_output_path(
                    output_dir=batch_output_dir,
                    candidate_id=candidate_id,
                )
                write_json_output(payload=json_payload, output_path=output_path)

                quality_assessment = result.get("quality_assessment", {})
                quality_gate = result.get("quality_gate", {})
                successes.append(
                    {
                        "candidate_id": candidate_id,
                        "output_json": str(output_path),
                        "model_name": result.get("model_profile", {}).get("model_name"),
                        "quality_score": quality_assessment.get("quality_score"),
                        "quality_status": quality_assessment.get("status"),
                        "fallback_invoked": quality_gate.get("fallback_invoked", False),
                        "final_model_name": quality_gate.get(
                            "final_model_name",
                            result.get("model_profile", {}).get("model_name"),
                        ),
                    }
                )

            except (
                ResumeExtractionError,
                LLMProviderConfigurationError,
                RuntimeError,
            ) as exc:
                failure_record = build_failure_record(
                    candidate_id=candidate_id,
                    exc=exc,
                )
                failures.append(failure_record)
                append_jsonl_log(
                    payload=failure_record,
                    output_path=batch_output_dir / "batch_failures.jsonl",
                )

                print(f"  Failed candidate {candidate_id}: {exc}")
                if args.stop_on_error:
                    break

        summary = build_batch_summary(
            candidate_ids=candidate_ids,
            successes=successes,
            failures=failures,
            output_dir=batch_output_dir,
            quality_log_jsonl=args.quality_log_jsonl,
        )
        summary_path = batch_output_dir / "batch_summary.json"
        write_json_output(payload=summary, output_path=summary_path)
        print_batch_summary(summary)

        return 0 if not failures else 1

    except Exception as exc:
        print("Batch resume extraction failed unexpectedly.", file=sys.stderr)
        print(str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
