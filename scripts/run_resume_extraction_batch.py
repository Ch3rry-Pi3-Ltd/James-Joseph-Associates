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
- a manifest-based skip layer so unchanged candidates are not reprocessed
- a narrow stable-failure skip for unchanged no-resume cases

What this script does
---------------------
It performs the following steps for each candidate:

1. run the first-pass extraction
2. apply the deterministic quality gate
3. optionally rerun with the stronger fallback model
4. write one JSON result file
5. record batch success/failure metadata
6. skip later identical reruns when the source fingerprint is unchanged
7. skip unchanged terminal no-resume failures without paying for another run

What this script does not do
----------------------------
It does not, by default:

- write accepted structured data into the database
- define the final evaluation threshold policy
- replace later Supabase persistence or dashboards
- guarantee zero source-system reads for skipped candidates

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

Run a batch and persist accepted outputs into the canonical schema:

    uv run python scripts/run_resume_extraction_batch.py ^
        --jobadder-account 2236 ^
        --candidate-id 16496678 ^
        --candidate-id 12345678 ^
        --enable-quality-gate ^
        --persist-accepted-output

Force a reprocess even if the manifest says the candidate has already been
handled successfully with the same fingerprint:

    uv run python scripts/run_resume_extraction_batch.py ^
        --jobadder-account 2236 ^
        --candidate-id 16496678 ^
        --force-reprocess

In plain language:

- provide a batch of candidate IDs
- reuse the same extraction path as the single-run script
- keep the outputs separate for later scoring review
- avoid paying for duplicate LLM runs when the candidate inputs did not change
- avoid repeating known no-resume failures when the upstream source state is unchanged
"""
# ruff: noqa: E402

from __future__ import annotations

import argparse
from copy import deepcopy
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import sys
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.core.idempotency import hash_payload
from backend.llm.models import ModelProvider
from backend.llm.providers import LLMProviderConfigurationError
from backend.services.jobadder_ingest import (
    JobAdderIngestPreparationError,
    build_jobadder_candidate_ingest_shell,
)
from backend.services.resume_extraction import ResumeExtractionError
from backend.services.resume_extraction_persistence import (
    persist_accepted_resume_extraction_result,
)
from scripts.run_resume_extraction import (
    DEFAULT_QUALITY_GATE_FALLBACK_MODEL_NAME,
    DEFAULT_RESUME_EXTRACTION_MODEL_PROFILE,
    append_jsonl_log,
    build_json_ready_result,
    build_runtime_model_profile,
    run_live_resume_extraction_with_optional_quality_gate,
    write_json_output,
)

DEFAULT_BATCH_MANIFEST_JSONL_PATH = Path("temp/resume_extraction_batch_manifest.jsonl")
BATCH_MANIFEST_SCHEMA_VERSION = "resume_extraction_batch_manifest_v1"
BATCH_FINGERPRINT_RELEVANT_FILES = (
    Path("backend/services/resume_extraction.py"),
    Path("backend/services/extraction_quality.py"),
    Path("backend/services/text_cleaning.py"),
    Path("backend/services/resume_text.py"),
    Path("scripts/run_resume_extraction.py"),
)


def build_argument_parser() -> argparse.ArgumentParser:
    """
    Build the CLI argument parser for the batch extraction script.

    Returns
    -------
    argparse.ArgumentParser
        Configured parser for batch extraction runs.

    Notes
    -----
    This parser deliberately mirrors the single-run script where possible so
    operators do not have to learn two unrelated command surfaces.

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
        "--manifest-jsonl",
        type=Path,
        default=DEFAULT_BATCH_MANIFEST_JSONL_PATH,
        help=(
            "JSONL manifest used to skip already-processed candidates when "
            "their source fingerprint and extraction contract are unchanged."
        ),
    )
    parser.add_argument(
        "--force-reprocess",
        action="store_true",
        help=(
            "Bypass manifest-based skip checks and process the supplied "
            "candidates even when an identical successful fingerprint already exists."
        ),
    )
    parser.add_argument(
        "--include-prompts",
        action="store_true",
        help="Include prompt material in each saved result JSON.",
    )
    parser.add_argument(
        "--persist-accepted-output",
        action="store_true",
        help=(
            "Persist accepted quality-gated candidate outputs into the "
            "canonical Supabase/Postgres schema."
        ),
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

    Parameters
    ----------
    explicit_candidate_ids : list[int]
        Candidate IDs supplied directly through repeated `--candidate-id`
        flags.

    candidate_ids_file : Path | None
        Optional file containing candidate IDs separated by whitespace and/or
        commas.

    Returns
    -------
    list[int]
        Deduplicated candidate IDs preserving first-seen order.

    Notes
    -----
    The batch runner needs one simple, forgiving way to accept candidate lists
    from:

    - quick CLI experiments
    - copied spreadsheet exports
    - temporary text files

    So this helper accepts a deliberately loose delimiter rule rather than
    enforcing one strict file format.

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

    Parameters
    ----------
    output_dir : Path
        Timestamped batch output directory.

    candidate_id : int
        Candidate identifier for the current batch item.

    Returns
    -------
    Path
        Per-candidate JSON result path.

    Example
    -------
    A call such as:

        build_candidate_output_path(
            output_dir=Path("temp/resume_extraction_batch/20260509T120000Z"),
            candidate_id=16496678,
        )

    returns:

        temp/resume_extraction_batch/20260509T120000Z/candidate_16496678.json
    """

    return output_dir / f"candidate_{candidate_id}.json"


def build_extraction_contract_fingerprint(
    *,
    args: argparse.Namespace,
) -> str:
    """
    Build one deterministic fingerprint for the current extraction contract.

    Parameters
    ----------
    args : argparse.Namespace
        Parsed batch-runner arguments for the current invocation.

    Returns
    -------
    str
        Stable SHA-256 fingerprint representing:

        - the selected first-pass model configuration
        - quality-gate thresholds and fallback model settings
        - the current source text of the extraction-critical local files

    Notes
    -----
    The goal is not to create a perfect formal "prompt version" system yet.
    The goal is to make reprocessing behaviour sane in practice.

    A candidate should be reprocessed automatically when either:

    - the upstream candidate materials changed
    - the extraction contract changed enough that a rerun is justified

    The second category is approximated here by hashing the local files that
    currently define:

    - resume extraction schema and prompt rules
    - input text cleaning
    - resume text extraction
    - quality-gate scoring
    - the single-run extraction orchestration

    Example
    -------
    Two separate batch runs with the same:

        - provider
        - model
        - thresholds
        - fallback model
        - local extraction files

    produce the same contract fingerprint.
    """

    model_profile = build_runtime_model_profile(args)
    relevant_file_hashes: dict[str, str] = {}

    # Fingerprint file content rather than only using file paths or modified
    # times.
    #
    # The reason is pragmatic: if the prompt contract changes in a meaningful
    # way, we want the batch runner to stop pretending that an old successful
    # extraction is still equivalent. Hashing the content gives us that without
    # requiring a separate manual version-bump step for every prompt edit.
    for relative_path in BATCH_FINGERPRINT_RELEVANT_FILES:
        absolute_path = PROJECT_ROOT / relative_path
        relevant_file_hashes[str(relative_path)] = hash_payload(
            absolute_path.read_text(encoding="utf-8")
        )

    return hash_payload(
        {
            "schema_version": BATCH_MANIFEST_SCHEMA_VERSION,
            "provider": model_profile.provider.value,
            "model_name": model_profile.model_name,
            "temperature": model_profile.temperature,
            "max_output_tokens": model_profile.max_output_tokens,
            "quality_gate_enabled": args.enable_quality_gate,
            "quality_pass_threshold": args.quality_pass_threshold,
            "quality_rerun_threshold": args.quality_rerun_threshold,
            "fallback_model_name": (
                args.fallback_model_name if args.enable_quality_gate else None
            ),
            "relevant_file_hashes": relevant_file_hashes,
        }
    )


def _select_latest_note_timestamp(note_items: list[dict[str, Any]]) -> str | None:
    """
    Return the latest note timestamp from a list of raw JobAdder note items.

    Parameters
    ----------
    note_items : list[dict[str, Any]]
        Raw note items returned by the JobAdder ingest preparation layer.

    Returns
    -------
    str | None
        Latest available note timestamp as an ISO-like string, or `None` when
        no usable note timestamps exist.

    Notes
    -----
    The JobAdder notes payload can expose both `updatedAt` and `createdAt`.
    We prefer `updatedAt` when present, but fall back to `createdAt` so older
    notes still contribute to the upstream-change signal.

    Example
    -------
    If the note list contains:

        - one note with `createdAt="2025-07-01T10:00:00Z"`
        - one note with `updatedAt="2025-09-05T07:36:44Z"`

    this helper returns:

        "2025-09-05T07:36:44Z"
    """

    timestamps: list[str] = []

    for note in note_items:
        for key in ("updatedAt", "createdAt"):
            raw_value = note.get(key)
            if isinstance(raw_value, str) and raw_value.strip() != "":
                timestamps.append(raw_value.strip())
                break

    if not timestamps:
        return None

    return max(timestamps)


def build_candidate_processing_fingerprint(
    *,
    ingest_payload: dict[str, Any],
    contract_fingerprint: str,
) -> tuple[str, str, dict[str, Any]]:
    """
    Build deterministic source and processing fingerprints for one candidate.

    Parameters
    ----------
    ingest_payload : dict[str, Any]
        Ingest-preparation payload returned by
        `build_jobadder_candidate_ingest_shell(...)`.

    contract_fingerprint : str
        Batch-run contract fingerprint returned by
        `build_extraction_contract_fingerprint(...)`.

    Returns
    -------
    tuple[str, str, dict[str, Any]]
        Tuple containing:

        - the source-only fingerprint
        - the full candidate processing fingerprint
        - the smaller source-marker payload used to build it

    Notes
    -----
    We intentionally distinguish between two related but different identities:

    - the source-only fingerprint
    - the full processing fingerprint

    That distinction matters because the batch runner has two skip policies:

    - successful re-runs should depend on both source state and extraction contract
    - stable no-resume failures should depend only on source state

    We still avoid fingerprinting the full raw provider payload. Instead we use
    the smaller set of source markers that answer the operational question:

        "Would re-running this candidate now likely produce a materially
        different extraction result?"

    Example
    -------
    If a candidate receives:

    - a newer CV attachment
    - additional notes
    - or an upstream candidate-profile update

    then both returned fingerprints change and the batch runner will no longer
    skip that candidate automatically.
    """

    candidate_payload = ingest_payload.get("candidate", {})
    latest_resume = ingest_payload.get("latest_resume")
    notes_payload = ingest_payload.get("notes", {})
    note_items = notes_payload.get("items", []) if isinstance(notes_payload, dict) else []

    latest_resume_payload = latest_resume if isinstance(latest_resume, dict) else {}
    source_markers = {
        "source_system": ingest_payload.get("source_system"),
        "jobadder_account": ingest_payload.get("jobadder_account"),
        "candidate_id": ingest_payload.get("source_candidate_id"),
        "candidate_updated_at": candidate_payload.get("updatedAt"),
        "candidate_status": candidate_payload.get("status"),
        "latest_resume_attachment_id": latest_resume_payload.get("attachmentId"),
        "latest_resume_created_at": latest_resume_payload.get("createdAt"),
        "latest_resume_file_name": latest_resume_payload.get("fileName"),
        "resume_attachment_count": ingest_payload.get("attachments", {}).get(
            "resume_attachment_count"
        ),
        "note_count": notes_payload.get("note_count") if isinstance(notes_payload, dict) else None,
        "latest_note_timestamp": _select_latest_note_timestamp(note_items),
    }

    source_fingerprint = hash_payload(_source_markers_without_contract(source_markers))
    candidate_processing_fingerprint = hash_payload(
        {
            "contract_fingerprint": contract_fingerprint,
            "source_fingerprint": source_fingerprint,
        }
    )

    return source_fingerprint, candidate_processing_fingerprint, source_markers


def load_batch_manifest_records(*, manifest_path: Path) -> list[dict[str, Any]]:
    """
    Load previously recorded batch-manifest rows from JSONL.

    Parameters
    ----------
    manifest_path : Path
        JSONL manifest path to read.

    Returns
    -------
    list[dict[str, Any]]
        Manifest records in file order.

    Notes
    -----
    - Missing manifest files are treated as "no prior batch history".
    - Blank lines are ignored.
    - Malformed JSON is treated as an operator-visible error rather than
      silently skipped, because a corrupted manifest should not quietly change
      reprocessing behaviour.

    Example
    -------
    When the manifest file does not exist yet, this helper simply returns `[]`.
    """

    if not manifest_path.exists():
        return []

    records: list[dict[str, Any]] = []
    with manifest_path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            stripped_line = line.strip()
            if stripped_line == "":
                continue

            try:
                decoded = json.loads(stripped_line)
            except json.JSONDecodeError as exc:
                raise RuntimeError(
                    f"Batch manifest is malformed at line {line_number}: "
                    f"{manifest_path}"
                ) from exc

            if not isinstance(decoded, dict):
                raise RuntimeError(
                    f"Batch manifest record at line {line_number} is not a JSON object: "
                    f"{manifest_path}"
                )

            records.append(decoded)

    return records


def find_success_manifest_record(
    *,
    manifest_records: list[dict[str, Any]],
    candidate_fingerprint: str,
) -> dict[str, Any] | None:
    """
    Return the most recent successful manifest record for one fingerprint.

    Parameters
    ----------
    manifest_records : list[dict[str, Any]]
        Previously loaded manifest rows.

    candidate_fingerprint : str
        Candidate processing fingerprint built for the current run.

    Returns
    -------
    dict[str, Any] | None
        Matching successful manifest row, or `None` when the candidate should
        be processed again.

    Notes
    -----
    We only skip when a prior record was both:

    - the exact same fingerprint
    - a successful completed processing run

    This helper intentionally answers only the narrower question:

    - "Was there a prior identical success?"

    The broader skip policy now lives in `find_skip_manifest_record(...)`,
    which can also admit a very small class of stable source-side failures.

    Example
    -------
    If the manifest contains:

        - a failure row for fingerprint `abc`
        - a later success row for fingerprint `abc`

    this helper returns the later success row, because that is the only prior
    record that justifies skipping a fresh batch attempt.
    """

    for record in reversed(manifest_records):
        if record.get("candidate_fingerprint") != candidate_fingerprint:
            continue
        if record.get("processing_outcome") != "success":
            continue
        return record

    return None


def is_stable_source_failure_manifest_record(record: dict[str, Any]) -> bool:
    """
    Return whether one manifest failure row is safe to skip on an unchanged rerun.

    Parameters
    ----------
    record : dict[str, Any]
        One manifest row previously written by the batch runner.

    Returns
    -------
    bool
        `True` when the failure describes a stable upstream source-data absence
        that is unlikely to change without an external update.

    Notes
    -----
    This helper is intentionally narrow.

    We currently treat only one failure pattern as skip-worthy:

    - `stage == "resume_selection"`
    - failure message indicates that no likely JobAdder resume attachment exists

    That narrowness is deliberate:

    - missing resume attachments are usually an upstream data problem
    - rerunning the same unchanged candidate does not help
    - other failures, such as parsing or model issues, may become fixable after
      code changes and should remain replayable

    Example
    -------
    A manifest row like:

        {
            "processing_outcome": "failure",
            "failure_stage": "resume_selection",
            "failure_message": "No likely JobAdder resume attachment was found for this candidate.",
        }

    returns `True`.
    """

    if record.get("processing_outcome") != "failure":
        return False

    failure_stage = record.get("failure_stage")
    failure_message = record.get("failure_message")

    if failure_stage != "resume_selection":
        return False

    if not isinstance(failure_message, str):
        return False

    return (
        failure_message.strip()
        == "No likely JobAdder resume attachment was found for this candidate."
    )


def _source_markers_without_contract(source_markers: dict[str, Any]) -> dict[str, Any]:
    """
    Return a copy of source markers with any contract-only keys removed.

    Parameters
    ----------
    source_markers : dict[str, Any]
        Source-marker payload stored in or derived for a manifest row.

    Returns
    -------
    dict[str, Any]
        Source-marker payload suitable for source-only fingerprinting.

    Notes
    -----
    Older manifest rows were written before `source_fingerprint` existed and
    stored only `source_markers`, which at that time still included
    `contract_fingerprint`. This helper strips that contract-only key so old
    rows can still participate in the newer source-only stable-failure skip
    logic.

    Example
    -------
    A payload such as:

        {
            "candidate_id": 16496678,
            "contract_fingerprint": "old-contract",
        }

    becomes:

        {
            "candidate_id": 16496678,
        }
    """

    return {
        key: value
        for key, value in source_markers.items()
        if key != "contract_fingerprint"
    }


def get_manifest_record_source_fingerprint(record: dict[str, Any]) -> str | None:
    """
    Return the source-only fingerprint for one manifest row when available.

    Parameters
    ----------
    record : dict[str, Any]
        One manifest row previously written by the batch runner.

    Returns
    -------
    str | None
        Source-only fingerprint for that row, or `None` when it cannot be
        derived safely.

    Notes
    -----
    This helper exists for manifest backward compatibility.

    Newer rows store `source_fingerprint` explicitly. Older rows do not, so we
    derive it from `source_markers` after stripping any contract-only keys.

    Example
    -------
    A modern row may already contain:

        {"source_fingerprint": "abc123", ...}

    while an older row may only contain:

        {"source_markers": {..., "contract_fingerprint": "old-contract"}, ...}

    In the second case, this helper reconstructs the source-only fingerprint
    from the remaining source-state markers.
    """

    stored_source_fingerprint = record.get("source_fingerprint")
    if isinstance(stored_source_fingerprint, str) and stored_source_fingerprint.strip():
        return stored_source_fingerprint

    raw_source_markers = record.get("source_markers")
    if not isinstance(raw_source_markers, dict):
        return None

    return hash_payload(_source_markers_without_contract(raw_source_markers))


def find_skip_manifest_record(
    *,
    manifest_records: list[dict[str, Any]],
    candidate_fingerprint: str,
    source_fingerprint: str,
) -> dict[str, Any] | None:
    """
    Return the most recent manifest row that justifies skipping one candidate.

    Parameters
    ----------
    manifest_records : list[dict[str, Any]]
        Previously loaded manifest rows.

    candidate_fingerprint : str
        Contract-aware candidate processing fingerprint built for the current
        run.

    source_fingerprint : str
        Source-only fingerprint built for the current run.

    Returns
    -------
    dict[str, Any] | None
        Matching manifest row that is safe to skip, or `None` when the
        candidate should be processed again.

    Notes
    -----
    The skip policy now has two categories, each keyed differently:

    - identical prior success, matched on the full processing fingerprint
    - identical prior stable no-resume failure, matched on the source-only
      fingerprint

    It still does **not** skip:

    - parse failures
    - LLM/provider failures
    - prompt/schema failures
    - document-format failures

    because those are all cases where a later code change may make rerunning
    worthwhile.

    Example
    -------
    If the manifest contains an unchanged failure row for:

        - `stage == "resume_selection"`
        - `message == "No likely JobAdder resume attachment was found for this candidate."`

    this helper returns that row and the batch runner will skip the candidate.
    """

    # Iterate newest-first because the manifest is append-only and later rows
    # represent the most accurate known state for that candidate. That matters
    # especially when a candidate moved from:
    #
    # - failure -> success
    # - older fingerprint -> newer fingerprint
    #
    # A forward scan would risk treating stale history as the current truth.
    for record in reversed(manifest_records):
        record_outcome = record.get("processing_outcome")

        if (
            record_outcome == "success"
            and record.get("candidate_fingerprint") == candidate_fingerprint
        ):
            return record

        if (
            is_stable_source_failure_manifest_record(record)
            and get_manifest_record_source_fingerprint(record) == source_fingerprint
        ):
            return record

    return None


def build_batch_manifest_record(
    *,
    candidate_id: int,
    source_fingerprint: str,
    candidate_fingerprint: str,
    source_markers: dict[str, Any],
    output_json: str | None,
    processing_outcome: str,
    result: dict[str, Any] | None = None,
    failure_record: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Build one manifest row for a processed candidate.

    Parameters
    ----------
    candidate_id : int
        Candidate identifier for the processed batch item.

    source_fingerprint : str
        Source-only fingerprint used for stable source-failure skip decisions.

    candidate_fingerprint : str
        Exact processing fingerprint used for skip decisions.

    source_markers : dict[str, Any]
        Smaller source-marker payload used to build the fingerprint.

    output_json : str | None
        Per-candidate JSON output path when a successful extraction result was
        written.

    processing_outcome : str
        Processing outcome label. V1 uses:

        - `success`
        - `failure`

    result : dict[str, Any] | None
        Successful extraction result when available.

    failure_record : dict[str, Any] | None
        Structured failure record when the candidate run failed.

    Returns
    -------
    dict[str, Any]
        JSON-serialisable manifest record.

    Example
    -------
    A successful row captures:

    - the fingerprint
    - the source markers that produced it
    - the final model name
    - the final quality score
    - the per-candidate JSON artifact path
    """

    quality_assessment = result.get("quality_assessment", {}) if result else {}
    cv_source_assessment = result.get("cv_source_assessment", {}) if result else {}
    quality_gate = result.get("quality_gate", {}) if result else {}
    model_profile = result.get("model_profile", {}) if result else {}

    # Keep routing quality and source richness side by side in the manifest.
    #
    # That distinction matters later when reviewing a batch:
    # - a candidate may have a good extraction but a sparse CV
    # - a candidate may have a richer CV but a weak extraction
    #
    # Storing both values now makes later threshold tuning and recruiter-facing
    # reporting much easier than trying to reconstruct them from only one score.
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "candidate_id": candidate_id,
        "source_fingerprint": source_fingerprint,
        "candidate_fingerprint": candidate_fingerprint,
        "source_markers": source_markers,
        "processing_outcome": processing_outcome,
        "output_json": output_json,
        "provider": model_profile.get("provider"),
        "model_name": model_profile.get("model_name"),
        "final_model_name": quality_gate.get("final_model_name")
        if quality_gate
        else model_profile.get("model_name"),
        "quality_score": quality_assessment.get("quality_score"),
        "quality_status": quality_assessment.get("status"),
        "cv_richness_score": cv_source_assessment.get("richness_score"),
        "cv_richness_band": cv_source_assessment.get("richness_band"),
        "fallback_invoked": quality_gate.get("fallback_invoked", False),
        "failure_stage": failure_record.get("stage") if failure_record else None,
        "failure_message": failure_record.get("message") if failure_record else None,
    }


def build_failure_record(
    *,
    candidate_id: int,
    exc: Exception,
) -> dict[str, Any]:
    """
    Build one structured failure record for the batch summary.

    Parameters
    ----------
    candidate_id : int
        Candidate ID for the failed batch item.

    exc : Exception
        Captured exception raised during that candidate's extraction run.

    Returns
    -------
    dict[str, Any]
        JSON-serialisable failure record suitable for:

        - the batch summary
        - a JSONL failure log
        - later debugging/replay work

    Example
    -------
    A typical result contains:

        {
            "candidate_id": 16496678,
            "error_type": "ResumeExtractionError",
            "stage": "llm_invoke",
            "message": "The resume extraction model call failed.",
        }
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
    skipped: list[dict[str, Any]],
    output_dir: Path,
    quality_log_jsonl: Path | None,
    manifest_jsonl: Path | None,
) -> dict[str, Any]:
    """
    Build one structured batch summary payload.

    Parameters
    ----------
    candidate_ids : list[int]
        Full requested candidate-ID list for this batch.

    successes : list[dict[str, Any]]
        Per-candidate success records built during the batch loop.

    failures : list[dict[str, Any]]
        Per-candidate failure records built during the batch loop.

    skipped : list[dict[str, Any]]
        Candidate records skipped because an identical safe-to-skip fingerprint
        already existed in the manifest.

    output_dir : Path
        Timestamped output directory for this batch run.

    quality_log_jsonl : Path | None
        Path to the quality-gate JSONL log when quality gating is enabled.

    manifest_jsonl : Path | None
        Batch manifest JSONL path used for skip/reprocess tracking.

    Returns
    -------
    dict[str, Any]
        Summary payload describing what the batch attempted and how it ended.

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
        "skipped_count": len(skipped),
        "fallback_count": fallback_count,
        "quality_status_counts": quality_status_counts,
        "output_dir": str(output_dir),
        "quality_log_jsonl": str(quality_log_jsonl) if quality_log_jsonl is not None else None,
        "manifest_jsonl": str(manifest_jsonl) if manifest_jsonl is not None else None,
        "successes": successes,
        "failures": failures,
        "skipped": skipped,
    }


def print_batch_summary(summary: dict[str, Any]) -> None:
    """
    Print a concise human-readable batch summary.

    Parameters
    ----------
    summary : dict[str, Any]
        Structured batch summary payload returned by `build_batch_summary(...)`.

    Notes
    -----
    The batch runner writes detailed JSON artifacts to disk. This helper is
    intentionally smaller: it answers the operator's first question quickly:

    - how many succeeded?
    - how many failed?
    - did the quality gate trigger fallback reruns?
    """

    lines = [
        "Batch resume extraction completed.",
        "",
        f"Requested candidates: {summary['requested_count']}",
        f"Successful candidates: {summary['success_count']}",
        f"Failed candidates: {summary['failure_count']}",
        f"Skipped candidates: {summary['skipped_count']}",
        f"Fallback reruns: {summary['fallback_count']}",
        f"Output directory: {summary['output_dir']}",
    ]
    if summary.get("manifest_jsonl"):
        lines.append(f"Manifest JSONL: {summary['manifest_jsonl']}")

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

    Parameters
    ----------
    argv : list[str] | None
        Optional argument list. When omitted, `argparse` reads from
        `sys.argv`.

    Returns
    -------
    int
        Process exit code.

        - `0` when every requested candidate completed successfully
        - `1` when one or more candidates failed
        - `2` for unexpected top-level failures

    Notes
    -----
    The batch runner is intentionally tolerant by default:

    - one failed candidate does not abort the whole run
    - failures are captured into the batch summary
    - `--stop-on-error` exists for stricter debugging sessions

    Example
    -------
    Running the module directly executes:

        raise SystemExit(main())

    which gives the script a normal process exit code for shell use.
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

        manifest_records = load_batch_manifest_records(
            manifest_path=args.manifest_jsonl,
        )
        contract_fingerprint = build_extraction_contract_fingerprint(args=args)

        successes: list[dict[str, Any]] = []
        failures: list[dict[str, Any]] = []
        skipped: list[dict[str, Any]] = []

        for index, candidate_id in enumerate(candidate_ids, start=1):
            print(f"[{index}/{len(candidate_ids)}] Candidate {candidate_id}")

            # Clone the parsed batch arguments into one candidate-scoped
            # namespace rather than mutating the shared object in place.
            #
            # That makes the control flow easier to reason about because each
            # candidate run receives:
            # - the same batch-wide settings
            # - exactly one different candidate ID
            #
            # It also avoids subtle bugs where later logging or error handling
            # accidentally sees the "wrong current candidate" because one
            # mutable namespace object was reused across the whole loop.
            candidate_args = argparse.Namespace(**deepcopy(vars(args)))
            candidate_args.candidate_id = candidate_id
            source_fingerprint: str | None = None
            candidate_fingerprint: str | None = None
            source_markers: dict[str, Any] | None = None

            try:
                # Preflight one source-side ingest shell before we spend any
                # LLM tokens.
                #
                # This preflight has two jobs:
                # - gather the source markers needed for the manifest fingerprint
                # - fail early if the candidate cannot even be read cleanly from
                #   JobAdder
                #
                # That means the skip layer avoids duplicate LLM work, even
                # though it still performs the cheaper source-system reads
                # required to determine whether anything has changed upstream.
                ingest_payload = build_jobadder_candidate_ingest_shell(
                    jobadder_account=args.jobadder_account,
                    candidate_id=candidate_id,
                )
                source_fingerprint, candidate_fingerprint, source_markers = (
                    build_candidate_processing_fingerprint(
                        ingest_payload=ingest_payload,
                        contract_fingerprint=contract_fingerprint,
                    )
                )

                if not args.force_reprocess:
                    existing_skip_record = find_skip_manifest_record(
                        manifest_records=manifest_records,
                        candidate_fingerprint=candidate_fingerprint,
                        source_fingerprint=source_fingerprint,
                    )
                    if existing_skip_record is not None:
                        # Skip on an identical manifest row only when the prior
                        # outcome is known to be safe to replay as a skip.
                        #
                        # There are now two safe categories:
                        # - a prior identical success
                        # - a prior identical no-resume source failure
                        #
                        # The second category is intentionally narrow. A missing
                        # resume attachment is an upstream source-data absence,
                        # so repeating the same unchanged run does not buy us
                        # anything. By contrast, parser/model failures stay
                        # replayable because later code changes may fix them.
                        previous_outcome = existing_skip_record.get(
                            "processing_outcome"
                        )
                        skip_reason = (
                            "unchanged_success"
                            if previous_outcome == "success"
                            else "unchanged_terminal_source_failure"
                        )
                        skipped_record = {
                            "candidate_id": candidate_id,
                            "source_fingerprint": source_fingerprint,
                            "candidate_fingerprint": candidate_fingerprint,
                            "skip_reason": skip_reason,
                            "previous_output_json": existing_skip_record.get("output_json"),
                            "previous_timestamp": existing_skip_record.get("timestamp"),
                            "previous_failure_stage": existing_skip_record.get(
                                "failure_stage"
                            ),
                            "previous_failure_message": existing_skip_record.get(
                                "failure_message"
                            ),
                        }
                        skipped.append(skipped_record)
                        if previous_outcome == "success":
                            print(
                                "  Skipped: identical successful fingerprint already exists."
                            )
                        else:
                            print(
                                "  Skipped: identical no-resume source failure already exists."
                            )
                        continue

                result = run_live_resume_extraction_with_optional_quality_gate(
                    candidate_args
                )
                if args.persist_accepted_output:
                    # Persist only after the quality-gated result exists.
                    #
                    # This keeps the DB write path downstream of the same
                    # accepted-output policy that the single-run script uses,
                    # rather than letting the batch runner invent a second
                    # parallel notion of "good enough to persist".
                    result = dict(result)
                    result["persistence_result"] = (
                        persist_accepted_resume_extraction_result(result)
                    )
                json_payload = build_json_ready_result(
                    result=result,
                    include_prompts=args.include_prompts,
                )
                output_path = build_candidate_output_path(
                    output_dir=batch_output_dir,
                    candidate_id=candidate_id,
                )

                # Keep one JSON result per candidate rather than one giant
                # monolithic batch file.
                #
                # That tradeoff is deliberate:
                # - it keeps manual inspection simple
                # - it makes partial reruns easier later
                # - it avoids rewriting a huge batch artifact when only one
                #   candidate needs to be revisited
                write_json_output(payload=json_payload, output_path=output_path)

                quality_assessment = result.get("quality_assessment", {})
                cv_source_assessment = result.get("cv_source_assessment", {})
                quality_gate = result.get("quality_gate", {})
                successes.append(
                    {
                        "candidate_id": candidate_id,
                        "output_json": str(output_path),
                        "model_name": result.get("model_profile", {}).get("model_name"),
                        "quality_score": quality_assessment.get("quality_score"),
                        "quality_status": quality_assessment.get("status"),
                        "cv_richness_score": cv_source_assessment.get("richness_score"),
                        "cv_richness_band": cv_source_assessment.get("richness_band"),
                        "fallback_invoked": quality_gate.get("fallback_invoked", False),
                        "final_model_name": quality_gate.get(
                            "final_model_name",
                            result.get("model_profile", {}).get("model_name"),
                        ),
                        "persistence_result": result.get("persistence_result"),
                    }
                )
                manifest_record = build_batch_manifest_record(
                    candidate_id=candidate_id,
                    source_fingerprint=source_fingerprint,
                    candidate_fingerprint=candidate_fingerprint,
                    source_markers=source_markers,
                    output_json=str(output_path),
                    processing_outcome="success",
                    result=result,
                )
                append_jsonl_log(
                    payload=manifest_record,
                    output_path=args.manifest_jsonl,
                )
                manifest_records.append(manifest_record)

            except (
                JobAdderIngestPreparationError,
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
                if (
                    source_fingerprint is not None
                    and candidate_fingerprint is not None
                    and source_markers is not None
                ):
                    # Record fingerprinted failures too.
                    #
                    # Even though V1 does not skip failed fingerprints yet,
                    # keeping them in the manifest now gives us the raw data we
                    # need to introduce smarter "stable source failure" rules
                    # later without redesigning the storage format first.
                    append_jsonl_log(
                        payload=build_batch_manifest_record(
                            candidate_id=candidate_id,
                            source_fingerprint=source_fingerprint,
                            candidate_fingerprint=candidate_fingerprint,
                            source_markers=source_markers,
                            output_json=None,
                            processing_outcome="failure",
                            failure_record=failure_record,
                        ),
                        output_path=args.manifest_jsonl,
                    )

                print(f"  Failed candidate {candidate_id}: {exc}")
                if args.stop_on_error:
                    break

        summary = build_batch_summary(
            candidate_ids=candidate_ids,
            successes=successes,
            failures=failures,
            skipped=skipped,
            output_dir=batch_output_dir,
            quality_log_jsonl=args.quality_log_jsonl,
            manifest_jsonl=args.manifest_jsonl,
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
