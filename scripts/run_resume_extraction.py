"""
Run one live JobAdder resume-extraction flow from the command line.

This script is the first real integration entrypoint for the backend's
candidate-enrichment pipeline.

Why this script exists
----------------------
By this point in the project, the backend already has the main building blocks
for structured candidate extraction:

- JobAdder ingest
- latest-resume selection
- resume download
- PDF text extraction
- text cleaning
- LLM provider construction
- structured resume extraction
- validation and test coverage around the main boundaries

The next question is different:

    "Can we run the full extraction flow against a real candidate and inspect
    the result end to end?"

That is what this script is for.

Why this matters
----------------
Until a real candidate goes through the pipeline, there are still important
unknowns:

- whether the prompt shape is good enough
- whether the schema is practical
- whether the selected model extracts useful fields consistently
- whether note text and resume text are being combined well
- whether the ambiguity/evidence output is genuinely helpful

This script gives the project a controlled way to answer those questions
without needing to build a route handler or UI first.

What this script does
---------------------
It performs the following steps:

1. load runtime settings
2. validate the minimum local configuration needed for a live extraction run
3. build a model profile for the extraction task
4. construct the LangChain chat model through `backend.llm.providers`
5. call `extract_jobadder_candidate_resume_profile(...)`
6. print a concise human-readable summary
7. optionally write the full result to disk as JSON

What this script does not do
----------------------------
It does not:

- write the structured extraction into the database
- update canonical candidate records
- run matching
- draft outreach
- expose an HTTP endpoint
- build a UI

That boundary is deliberate.

This script is for proving the extraction pipeline against live data, not for
solving the whole product workflow at once.

Examples
--------
Run a basic extraction and print a concise summary:

    uv run python scripts/run_resume_extraction.py ^
        --jobadder-account 2236 ^
        --candidate-id 16496678

Run an extraction and save the full JSON payload to disk:

    uv run python scripts/run_resume_extraction.py ^
        --jobadder-account 2236 ^
        --candidate-id 16496678 ^
        --output-json temp\\resume_extraction_result.json

Run with an explicit model override:

    uv run python scripts/run_resume_extraction.py ^
        --jobadder-account 2236 ^
        --candidate-id 16496678 ^
        --model-name gpt-5.4-mini ^
        --max-output-tokens 1600

Run against OpenRouter with a Nemotron-style extraction model:

    uv run python scripts/run_resume_extraction.py ^
        --jobadder-account 2236 ^
        --candidate-id 16496678 ^
        --provider openrouter ^
        --model-name nvidia/nemotron-3-nano-30b-a3b:nitro

Print the full result to stdout as JSON, including prompt material:

    uv run python scripts/run_resume_extraction.py ^
        --jobadder-account 2236 ^
        --candidate-id 16496678 ^
        --print-full-json ^
        --include-prompts

In plain language:

- point the script at one JobAdder account and one candidate
- let the backend fetch, clean, and extract the candidate data
- inspect the result
- optionally save the full payload for later analysis
"""
# ruff: noqa: E402

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from typing import Any

# When Python runs a file directly from `scripts/`, it places the `scripts/`
# directory on `sys.path`, not the repository root.
#
# This project's import graph starts from the repo root, for example:
# - `backend.llm.providers`
# - `backend.services.resume_extraction`
#
# So a direct invocation such as:
#
#     uv run python scripts/run_resume_extraction.py ...
#
# needs one small bootstrap step to ensure the repository root is importable.
# Doing it here keeps the script self-contained and matches the way an operator
# will naturally try to run it from the project root.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.llm.models import ModelProfile, ModelProvider, ModelPurpose
from backend.llm.providers import (
    LLMProviderConfigurationError,
    build_langchain_chat_model,
)
from backend.services.extraction_quality import (
    ExtractionQualityAssessment,
    score_resume_extraction,
)
from backend.services.resume_extraction import (
    DEFAULT_RESUME_EXTRACTION_MODEL_PROFILE,
    ResumeExtractionError,
    extract_jobadder_candidate_resume_profile,
)
from backend.settings import get_settings


DEFAULT_OPENROUTER_RESUME_EXTRACTION_MODEL_NAME = (
    "nvidia/nemotron-3-nano-30b-a3b:nitro"
)
DEFAULT_QUALITY_GATE_FIRST_PASS_MODEL_NAME = "gpt-4.1-mini"
DEFAULT_QUALITY_GATE_FALLBACK_MODEL_NAME = "gpt-5.4-mini"
DEFAULT_QUALITY_LOG_JSONL_PATH = Path("temp/resume_extraction_quality_log.jsonl")
SUPPORTED_EXTRACTION_PROVIDERS = (
    ModelProvider.OPENAI,
    ModelProvider.OPENROUTER,
)


def build_argument_parser() -> argparse.ArgumentParser:
    """
    Build the CLI argument parser for the live extraction script.

    Returns
    -------
    argparse.ArgumentParser
        Configured argument parser.

    Notes
    -----
    - The arguments are intentionally explicit.
    - This is an integration script, not a reusable library call.
    - The goal is to make each runtime choice easy to see from the command
      line, especially when debugging extraction quality.

    Example
    -------
    A caller can request one live extraction with:

        --jobadder-account 2236
        --candidate-id 16496678

    and optionally add output controls such as:

        --output-json temp\\result.json
        --print-full-json
        --include-prompts

    In plain language:

    - define the inputs for one extraction run
    - keep them obvious and inspectable from the terminal
    """

    parser = argparse.ArgumentParser(
        description=(
            "Run one live JobAdder resume-extraction flow and inspect the "
            "structured result."
        )
    )

    parser.add_argument(
        "--jobadder-account",
        type=int,
        required=True,
        help=(
            "JobAdder account identifier used to resolve the stored OAuth "
            "connection."
        ),
    )
    parser.add_argument(
        "--candidate-id",
        type=int,
        required=True,
        help="JobAdder candidate identifier to extract from.",
    )

    parser.add_argument(
        "--provider",
        choices=[provider.value for provider in SUPPORTED_EXTRACTION_PROVIDERS],
        default=DEFAULT_RESUME_EXTRACTION_MODEL_PROFILE.provider.value,
        help=(
            "Model provider to use for extraction. Defaults to the current "
            "module extraction-provider baseline."
        ),
    )

    # Keep model controls overridable from the CLI because real extraction work
    # often needs quick empirical comparison:
    # - stronger vs cheaper model
    # - tighter token ceiling
    # - deterministic vs slightly looser temperature
    #
    # This avoids hard-coding every experiment back into the service module.
    parser.add_argument(
        "--model-name",
        default=None,
        help=(
            "Model name to use for extraction. If omitted, the script chooses "
            "a provider-specific default."
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

    # Output control matters because the full extraction payload can contain:
    # - cleaned CV text
    # - cleaned notes
    # - full prompts
    #
    # That is useful for debugging, but it is also noisy. The default behaviour
    # therefore prints a concise summary and only emits the full JSON when the
    # caller asks for it explicitly.
    parser.add_argument(
        "--output-json",
        type=Path,
        default=None,
        help="Optional path to write the full extraction result as JSON.",
    )
    parser.add_argument(
        "--print-full-json",
        action="store_true",
        help="Print the full extraction result as JSON to stdout.",
    )
    parser.add_argument(
        "--include-prompts",
        action="store_true",
        help=(
            "Include `prompt_bundle` in JSON output. This is useful for prompt "
            "debugging, but it can be verbose and may contain sensitive source "
            "material."
        ),
    )
    parser.add_argument(
        "--enable-quality-gate",
        action="store_true",
        help=(
            "Run a deterministic quality assessment after extraction and "
            "rerun weak first-pass outputs through a stronger fallback model."
        ),
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
        help=(
            "Fallback OpenAI model name to use when the deterministic quality "
            "score requests a rerun."
        ),
    )
    parser.add_argument(
        "--quality-log-jsonl",
        type=Path,
        default=DEFAULT_QUALITY_LOG_JSONL_PATH,
        help=(
            "Path to append quality-gate review/rerun records as JSONL when "
            "quality gating is enabled."
        ),
    )

    return parser


def build_runtime_model_profile(args: argparse.Namespace) -> ModelProfile:
    """
    Build the extraction `ModelProfile` from parsed CLI arguments.

    Parameters
    ----------
    args : argparse.Namespace
        Parsed CLI arguments.

    Returns
    -------
    ModelProfile
        Model profile to use for this script run.

    Notes
    -----
    - The project already has a default extraction profile.
    - This helper exists so the script can make a fresh profile for each run
      without mutating any module-level constant.
    - That is important for experimentation. A one-off CLI override should
      affect only this process.

    Example
    -------
    If the caller runs:

        --provider openai
        --model-name gpt-5.4-mini
        --temperature 0.0
        --max-output-tokens 1600

    this helper returns:

        ModelProfile(
            provider=ModelProvider.OPENAI,
            model_name="gpt-5.4-mini",
            purpose=ModelPurpose.EXTRACTION,
            temperature=0.0,
            max_output_tokens=1600,
        )

    In plain language:

    - take the command-line model choices
    - turn them into the same typed profile the backend already understands
    """

    provider = ModelProvider(args.provider)
    model_name = _resolve_default_model_name(
        provider,
        args.model_name,
        quality_gate_enabled=args.enable_quality_gate,
    )

    return ModelProfile(
        provider=provider,
        model_name=model_name,
        purpose=ModelPurpose.EXTRACTION,
        temperature=args.temperature,
        max_output_tokens=args.max_output_tokens,
    )


def _resolve_default_model_name(
    provider: ModelProvider,
    explicit_model_name: str | None,
    *,
    quality_gate_enabled: bool,
) -> str:
    """
    Resolve the model name for one CLI run.

    Parameters
    ----------
    provider : ModelProvider
        Provider selected for this script run.

    explicit_model_name : str | None
        Optional explicit model name supplied by the caller.

    Returns
    -------
    str
        Model name to place on the runtime profile.

    Notes
    -----
    - An explicit caller-provided model name always wins.
    - Otherwise the script chooses one stable provider-specific default so
      model-comparison runs remain convenient from the CLI.
    """

    if explicit_model_name is not None and explicit_model_name.strip() != "":
        return explicit_model_name

    if provider == ModelProvider.OPENAI:
        if quality_gate_enabled:
            return DEFAULT_QUALITY_GATE_FIRST_PASS_MODEL_NAME
        return DEFAULT_RESUME_EXTRACTION_MODEL_PROFILE.model_name

    if provider == ModelProvider.OPENROUTER:
        return DEFAULT_OPENROUTER_RESUME_EXTRACTION_MODEL_NAME

    return DEFAULT_RESUME_EXTRACTION_MODEL_PROFILE.model_name


def validate_live_run_preconditions(*, provider: ModelProvider) -> None:
    """
    Validate the minimum local configuration needed for a live extraction run.

    Raises
    ------
    RuntimeError
        If obviously required local configuration is missing.

    Notes
    -----
    This helper intentionally checks only the local prerequisites that are cheap
    and unambiguous to validate before any real provider or JobAdder work
    begins.

    At the moment that means:
    - the selected provider has a usable API key available through settings
    - the minimum JobAdder OAuth application settings needed by the wider
      integration layer

    This helper does not:
    - verify the provider key is valid
    - verify the JobAdder token store contains a usable connection
    - test network connectivity

    Those are real runtime/integration concerns and should fail in their own
    natural place.

    Example
    -------
    If `.env.local` has no provider key for the chosen provider, this helper
    raises early with a clear message rather than letting the provider
    constructor fail later with a less contextual stack trace.

    In plain language:

    - check the basics first
    - fail early when the local environment is obviously incomplete
    """

    settings = get_settings()

    # The provider layer can fall back to settings now, so this script should
    # check the provider-specific settings path up front and fail with a
    # message that is specific to this workflow.
    if provider == ModelProvider.OPENAI and settings.openai_api_key.strip() == "":
        raise RuntimeError(
            "OPENAI_API_KEY is not configured. Set it in `.env.local` or the "
            "shell environment before running a live extraction."
        )

    if (
        provider == ModelProvider.OPENROUTER
        and settings.openrouter_api_key.strip() == ""
    ):
        raise RuntimeError(
            "OPENROUTER_API_KEY is not configured. Set it in `.env.local` or "
            "the shell environment before running a live extraction."
        )

    # The JobAdder integration needs the OAuth app settings to exist locally.
    # This does not guarantee that a stored candidate connection exists for the
    # requested account, but it does catch the obvious "the integration is not
    # configured at all" state before we do any deeper work.
    missing_jobadder_settings: list[str] = []

    if settings.jobadder_client_id.strip() == "":
        missing_jobadder_settings.append("JOBADDER_CLIENT_ID")
    if settings.jobadder_client_secret.strip() == "":
        missing_jobadder_settings.append("JOBADDER_CLIENT_SECRET")
    if settings.jobadder_redirect_uri.strip() == "":
        missing_jobadder_settings.append("JOBADDER_REDIRECT_URI")

    if missing_jobadder_settings:
        raise RuntimeError(
            "The local JobAdder OAuth configuration is incomplete. Missing: "
            + ", ".join(missing_jobadder_settings)
        )


def build_console_summary(result: dict[str, Any]) -> str:
    """
    Build a concise human-readable summary of the extraction result.

    Parameters
    ----------
    result : dict[str, Any]
        Full extraction result returned by the service layer.

    Returns
    -------
    str
        Multi-line summary string suitable for terminal output.

    Notes
    -----
    - The full extraction result is useful for debugging, but it is too noisy
      to be the default terminal output.
    - A short summary makes it easier to answer the practical first question:
      "Did the extraction produce something sensible?"
    - The summary intentionally focuses on the most decision-relevant fields
      first.

    Example
    -------
    For a successful extraction, the summary may include lines such as:

        Current title: Senior Data Scientist
        Current employer: Pirum
        Skills: Python, NLP, SQL
        Emails: the_rfc@hotmail.co.uk

    In plain language:

    - pull out the fields a human most likely wants to sanity-check first
    - present them without dumping the whole JSON blob
    """

    structured = result.get("structured_extraction", {})
    extraction_input = result.get("extraction_input", {})
    candidate_context = extraction_input.get("candidate_context", {})
    latest_resume = extraction_input.get("latest_resume", {})

    skills = structured.get("skills", [])
    tools_and_platforms = structured.get("tools_and_platforms", [])
    certifications = structured.get("certifications", [])
    emails = structured.get("emails", [])
    phones = structured.get("phones", [])
    evidence_notes = structured.get("evidence_notes", [])
    ambiguity_notes = structured.get("ambiguity_notes", [])
    employment_history = structured.get("employment_history", [])
    education = structured.get("education", [])
    projects = structured.get("projects", [])
    quality_assessment = result.get("quality_assessment", {})
    quality_gate = result.get("quality_gate", {})

    lines = [
        "Live resume extraction completed.",
        "",
        f"Source system: {result.get('source_system')}",
        f"Source candidate ID: {result.get('source_candidate_id')}",
        f"JobAdder account: {result.get('jobadder_account')}",
        f"Candidate: {candidate_context.get('first_name')} {candidate_context.get('last_name')}",
        f"Resume file: {latest_resume.get('file_name')}",
        f"Provider: {result.get('model_profile', {}).get('provider')}",
        f"Model: {result.get('model_profile', {}).get('model_name')}",
        "",
        f"Current title: {structured.get('current_title')}",
        f"Current employer: {structured.get('current_employer')}",
        f"Location: {structured.get('location')}",
        f"Emails: {', '.join(emails) if emails else '(none)'}",
        f"Phones: {', '.join(phones) if phones else '(none)'}",
        f"Skills: {', '.join(skills) if skills else '(none)'}",
        f"Tools/platforms: {', '.join(tools_and_platforms) if tools_and_platforms else '(none)'}",
        f"Certifications: {', '.join(certifications) if certifications else '(none)'}",
        f"Employment entries: {len(employment_history)}",
        f"Projects: {len(projects)}",
        f"Education entries: {len(education)}",
        f"Evidence notes: {len(evidence_notes)}",
        f"Ambiguity notes: {len(ambiguity_notes)}",
    ]

    if quality_assessment:
        lines.extend(
            [
                "",
                f"Quality score: {quality_assessment.get('quality_score')}",
                f"Quality status: {quality_assessment.get('status')}",
            ]
        )
        reasons = quality_assessment.get("reasons", [])
        if reasons:
            lines.append(f"Quality reasons: {', '.join(reasons)}")

    if quality_gate:
        lines.append(
            f"Fallback invoked: {'yes' if quality_gate.get('fallback_invoked') else 'no'}"
        )
        final_model_name = quality_gate.get("final_model_name")
        if final_model_name:
            lines.append(f"Final model: {final_model_name}")

    # Include the first ambiguity/evidence note because those are often the
    # fastest signal of whether the model actually reasoned about uncertainty
    # and source support in a useful way.
    if evidence_notes:
        lines.extend(
            [
                "",
                f"First evidence note: {evidence_notes[0]}",
            ]
        )

    if ambiguity_notes:
        lines.extend(
            [
                f"First ambiguity note: {ambiguity_notes[0]}",
            ]
        )

    return "\n".join(lines)


def build_json_ready_result(
    *,
    result: dict[str, Any],
    include_prompts: bool,
) -> dict[str, Any]:
    """
    Build the JSON payload to print or save.

    Parameters
    ----------
    result : dict[str, Any]
        Full extraction result.

    include_prompts : bool
        Whether to keep `prompt_bundle` in the returned payload.

    Returns
    -------
    dict[str, Any]
        JSON-ready result payload.

    Notes
    -----
    - The extraction result already consists of plain serializable structures.
    - This helper still exists because prompt inclusion is a deliberate choice.
    - Prompt bundles can be very useful during extraction tuning, but they also
      contain the cleaned source material and can become noisy quickly.

    Example
    -------
    When `include_prompts=False`, the JSON output excludes:

        result["prompt_bundle"]

    but retains:

        result["structured_extraction"]
        result["extraction_input"]
        result["model_profile"]

    In plain language:

    - take the full result
    - optionally strip the prompt payload
    - return something safe to serialize
    """

    if include_prompts:
        return result

    json_ready = dict(result)
    json_ready.pop("prompt_bundle", None)
    return json_ready


def write_json_output(*, payload: dict[str, Any], output_path: Path) -> None:
    """
    Write the extraction result JSON to disk.

    Parameters
    ----------
    payload : dict[str, Any]
        JSON-ready extraction result.

    output_path : Path
        Output file path.

    Notes
    -----
    - Parent directories are created automatically so the caller does not have
      to prepare them manually.
    - UTF-8 and indentation are used because this output is intended for
      inspection and debugging, not compact transport.

    Example
    -------
    A caller may pass:

        output_path=Path("temp/resume_extraction_result.json")

    and this helper will create `temp/` if needed before writing the file.

    In plain language:

    - make sure the destination folder exists
    - write readable JSON to disk
    """

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def append_jsonl_log(*, payload: dict[str, Any], output_path: Path) -> None:
    """
    Append one JSON payload to a JSONL log file.

    Parameters
    ----------
    payload : dict[str, Any]
        One log record to append.

    output_path : Path
        Destination JSONL file.

    Notes
    -----
    This helper is used by the quality-gate flow so weak first-pass and
    fallback decisions can be inspected later without needing a database table
    first.

    Example
    -------
    A caller may append:

        append_jsonl_log(
            payload={"candidate_id": 16496678, "quality_score": 61},
            output_path=Path("temp/resume_extraction_quality_log.jsonl"),
        )
    """

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False) + "\n")


def build_quality_assessment(
    *,
    result: dict[str, Any],
    pass_threshold: int,
    rerun_threshold: int,
) -> ExtractionQualityAssessment:
    """
    Score one extraction result using the deterministic quality gate.

    Parameters
    ----------
    result : dict[str, Any]
        Full extraction result payload returned by the live extraction flow.

    pass_threshold : int
        Score at or above this threshold is a pass.

    rerun_threshold : int
        Score below this threshold triggers a rerun recommendation.

    Returns
    -------
    ExtractionQualityAssessment
        Deterministic quality assessment for the extraction result.

    Example
    -------
    A caller can take the result from the live extraction runner and score it:

        assessment = build_quality_assessment(
            result=result,
            pass_threshold=80,
            rerun_threshold=65,
        )
    """

    extraction_input = result.get("extraction_input", {})
    structured_extraction = result.get("structured_extraction", {})

    return score_resume_extraction(
        extraction=structured_extraction,
        cleaned_resume_text=extraction_input.get("cleaned_resume_text", ""),
        pass_threshold=pass_threshold,
        rerun_threshold=rerun_threshold,
    )


def build_quality_log_record(
    *,
    result: dict[str, Any],
    assessment: ExtractionQualityAssessment,
    stage: str,
    fallback_invoked: bool,
    final_status: str | None = None,
) -> dict[str, Any]:
    """
    Build one structured quality-log record.

    Parameters
    ----------
    result : dict[str, Any]
        Extraction result being logged.

    assessment : ExtractionQualityAssessment
        Deterministic quality assessment for that result.

    stage : str
        Pipeline stage label, such as `first_pass` or `fallback`.

    fallback_invoked : bool
        Whether the quality gate triggered the fallback path for this
        candidate.

    final_status : str | None
        Final routing status after any fallback decision is made.

    Returns
    -------
    dict[str, Any]
        JSON-serialisable log record.

    Example
    -------
    A record may look like:

        {
            "candidate_id": 16496678,
            "model_name": "gpt-4.1-mini",
            "quality_score": 61,
            "quality_status": "rerun",
            "stage": "first_pass",
        }
    """

    extraction_input = result.get("extraction_input", {})
    latest_resume = extraction_input.get("latest_resume", {})
    model_profile = result.get("model_profile", {})

    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "stage": stage,
        "source_system": result.get("source_system"),
        "candidate_id": result.get("source_candidate_id"),
        "jobadder_account": result.get("jobadder_account"),
        "resume_file_name": latest_resume.get("file_name"),
        "provider": model_profile.get("provider"),
        "model_name": model_profile.get("model_name"),
        "quality_score": assessment.quality_score,
        "quality_status": assessment.status,
        "reasons": assessment.reasons,
        "fallback_invoked": fallback_invoked,
        "final_status": final_status,
    }


def enrich_result_with_quality_metadata(
    *,
    result: dict[str, Any],
    assessment: ExtractionQualityAssessment,
    quality_gate: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Attach quality-gate metadata to one extraction result payload.

    Notes
    -----
    This keeps the final JSON output self-contained. A saved extraction file
    can then explain both:

    - what the extraction output was
    - how the quality gate judged it

    Example
    -------
    After enrichment, the payload contains fields such as:

        result["quality_assessment"]
        result["quality_gate"]
    """

    enriched_result = dict(result)
    enriched_result["quality_assessment"] = assessment.model_dump()
    if quality_gate is not None:
        enriched_result["quality_gate"] = quality_gate
    return enriched_result


def _print_json_safely(payload: dict[str, Any]) -> None:
    """
    Print JSON to stdout while tolerating narrow Windows console encodings.

    Parameters
    ----------
    payload : dict[str, Any]
        JSON-ready payload to print.

    Notes
    -----
    - The saved JSON file should preserve Unicode faithfully.
    - The console, however, may be using a narrower code page that cannot
      render every character found in live recruiter notes or candidate text.
    - This helper therefore falls back to a replacement-safe encoding when
      direct `print(...)` would fail.
    """

    rendered_json = json.dumps(payload, indent=2, ensure_ascii=False)

    try:
        print(rendered_json)
    except UnicodeEncodeError:
        safe_stdout = getattr(sys.stdout, "buffer", None)
        if safe_stdout is None:
            print(rendered_json.encode("ascii", errors="replace").decode("ascii"))
            return

        safe_stdout.write(
            rendered_json.encode(
                getattr(sys.stdout, "encoding", "utf-8") or "utf-8",
                errors="replace",
            )
        )
        safe_stdout.write(b"\n")


def run_live_resume_extraction(args: argparse.Namespace) -> dict[str, Any]:
    """
    Run one live JobAdder resume extraction from parsed CLI arguments.

    Parameters
    ----------
    args : argparse.Namespace
        Parsed CLI arguments.

    Returns
    -------
    dict[str, Any]
        Full extraction result returned by the service layer.

    Raises
    ------
    RuntimeError
        If obvious local preconditions are missing.

    ResumeExtractionError
        If the extraction layer fails during prompt build, model invocation, or
        schema validation.

    LLMProviderConfigurationError
        If the provider layer cannot build a usable model client.

    Notes
    -----
    - This is the main integration step in the script.
    - It is intentionally short because the business logic should remain inside
      the real backend modules rather than being recreated here.
    - The script's job is orchestration and observability, not duplication.

    Example
    -------
    A typical flow is:

        1. validate local settings
        2. build `ModelProfile`
        3. build LangChain chat model
        4. run `extract_jobadder_candidate_resume_profile(...)`

    In plain language:

    - check that this machine is configured
    - construct the model
    - send one real candidate through the full extraction flow
    """

    model_profile = build_runtime_model_profile(args)
    return run_live_resume_extraction_with_model_profile(
        args=args,
        model_profile=model_profile,
    )


def run_live_resume_extraction_with_model_profile(
    *,
    args: argparse.Namespace,
    model_profile: ModelProfile,
) -> dict[str, Any]:
    """
    Run one live extraction using an already-resolved model profile.

    Parameters
    ----------
    args : argparse.Namespace
        Parsed CLI arguments for the current invocation.

    model_profile : ModelProfile
        Explicit model profile to use for this extraction run.

    Returns
    -------
    dict[str, Any]
        Full extraction result returned by the backend extraction layer.

    Notes
    -----
    This helper exists so the quality-gate flow can:

    - run a first-pass model
    - then rerun the same candidate with a stronger fallback model

    without re-implementing the lower-level orchestration.

    Example
    -------
    The quality gate can call this once with:

        model_profile=ModelProfile(model_name="gpt-4.1-mini", ...)

    and again with:

        model_profile=ModelProfile(model_name="gpt-5.4-mini", ...)
    """

    validate_live_run_preconditions(provider=model_profile.provider)

    # Build the real provider-backed model through the shared provider factory.
    # This matters because the project now has a deliberate architecture:
    # - settings own runtime configuration
    # - `backend.llm.providers` owns provider construction
    # - `backend.services.resume_extraction` owns extraction orchestration
    #
    # This script should respect that separation rather than bypassing it.
    chat_model = build_langchain_chat_model(profile=model_profile)

    return extract_jobadder_candidate_resume_profile(
        jobadder_account=args.jobadder_account,
        candidate_id=args.candidate_id,
        chat_model=chat_model,
        model_profile=model_profile,
    )


def main(argv: list[str] | None = None) -> int:
    """
    Run the CLI entrypoint.

    Parameters
    ----------
    argv : list[str] | None
        Optional argument list. When omitted, `argparse` reads from
        `sys.argv`.

    Returns
    -------
    int
        Process exit code.

        - `0` for success
        - `1` for known runtime/configuration failures
        - `2` for unexpected failures

    Notes
    -----
    - Keeping `main(...)` return an integer makes the script easy to use from:
        - the terminal
        - shell scripts
        - future CI/debug helpers
    - Known failures are caught and rendered as concise terminal messages.
    - Unexpected failures still print a short message and return a separate
      exit code.

    Example
    -------
    Running the module directly executes:

        raise SystemExit(main())

    which gives the script a normal process exit code.

    In plain language:

    - parse the CLI arguments
    - run the extraction
    - print useful output
    - exit cleanly with a meaningful code
    """

    parser = build_argument_parser()
    args = parser.parse_args(argv)

    try:
        if args.enable_quality_gate and args.provider != ModelProvider.OPENAI.value:
            raise RuntimeError(
                "The quality-gate fallback flow currently supports only the "
                "OpenAI provider."
            )

        if args.quality_rerun_threshold > args.quality_pass_threshold:
            raise RuntimeError(
                "QUALITY_RERUN_THRESHOLD cannot be greater than "
                "QUALITY_PASS_THRESHOLD."
            )

        result = run_live_resume_extraction(args)
        quality_gate_metadata: dict[str, Any] | None = None

        if args.enable_quality_gate:
            first_pass_assessment = build_quality_assessment(
                result=result,
                pass_threshold=args.quality_pass_threshold,
                rerun_threshold=args.quality_rerun_threshold,
            )
            first_pass_model_name = result.get("model_profile", {}).get("model_name")
            fallback_invoked = False
            final_assessment = first_pass_assessment
            final_result = result

            if first_pass_assessment.status == "rerun":
                fallback_invoked = True
                fallback_profile = ModelProfile(
                    provider=ModelProvider.OPENAI,
                    model_name=args.fallback_model_name,
                    purpose=ModelPurpose.EXTRACTION,
                    temperature=args.temperature,
                    max_output_tokens=args.max_output_tokens,
                )
                fallback_result = run_live_resume_extraction_with_model_profile(
                    args=args,
                    model_profile=fallback_profile,
                )
                fallback_assessment = build_quality_assessment(
                    result=fallback_result,
                    pass_threshold=args.quality_pass_threshold,
                    rerun_threshold=args.quality_rerun_threshold,
                )

                if fallback_assessment.quality_score >= first_pass_assessment.quality_score:
                    final_result = fallback_result
                    final_assessment = fallback_assessment

                append_jsonl_log(
                    payload=build_quality_log_record(
                        result=result,
                        assessment=first_pass_assessment,
                        stage="first_pass",
                        fallback_invoked=True,
                        final_status=final_assessment.status,
                    ),
                    output_path=args.quality_log_jsonl,
                )
                append_jsonl_log(
                    payload=build_quality_log_record(
                        result=fallback_result,
                        assessment=fallback_assessment,
                        stage="fallback",
                        fallback_invoked=True,
                        final_status=final_assessment.status,
                    ),
                    output_path=args.quality_log_jsonl,
                )
            elif first_pass_assessment.status == "review":
                append_jsonl_log(
                    payload=build_quality_log_record(
                        result=result,
                        assessment=first_pass_assessment,
                        stage="first_pass",
                        fallback_invoked=False,
                        final_status=first_pass_assessment.status,
                    ),
                    output_path=args.quality_log_jsonl,
                )

            quality_gate_metadata = {
                "enabled": True,
                "first_pass_model_name": first_pass_model_name,
                "fallback_model_name": args.fallback_model_name,
                "fallback_invoked": fallback_invoked,
                "final_model_name": final_result.get("model_profile", {}).get("model_name"),
                "first_pass_quality_assessment": first_pass_assessment.model_dump(),
                "final_quality_assessment": final_assessment.model_dump(),
            }
            result = enrich_result_with_quality_metadata(
                result=final_result,
                assessment=final_assessment,
                quality_gate=quality_gate_metadata,
            )
        else:
            result = enrich_result_with_quality_metadata(
                result=result,
                assessment=build_quality_assessment(
                    result=result,
                    pass_threshold=args.quality_pass_threshold,
                    rerun_threshold=args.quality_rerun_threshold,
                ),
            )

        # Default to a concise summary because the full payload can be large and
        # includes prompt/input material. The operator usually wants the "did it
        # work and does it look sane?" answer first.
        print(build_console_summary(result))

        json_payload = build_json_ready_result(
            result=result,
            include_prompts=args.include_prompts,
        )

        if args.output_json is not None:
            write_json_output(
                payload=json_payload,
                output_path=args.output_json,
            )
            print("")
            print(f"Wrote full JSON result to: {args.output_json}")

        if args.print_full_json:
            print("")
            _print_json_safely(json_payload)

        return 0

    except (
        ResumeExtractionError,
        LLMProviderConfigurationError,
        RuntimeError,
    ) as exc:
        # These are the failures we expect to be able to reason about:
        # - local config missing
        # - provider build problem
        # - extraction pipeline failure
        #
        # Print them cleanly without a huge traceback first, because in normal
        # operator use the message and the stage are what matter most.
        print("Live resume extraction failed.", file=sys.stderr)
        print(str(exc), file=sys.stderr)

        stage = getattr(exc, "stage", None)
        details = getattr(exc, "details", None)

        if stage:
            print(f"Stage: {stage}", file=sys.stderr)
        if details:
            print("Details:", file=sys.stderr)
            print(json.dumps(details, indent=2, ensure_ascii=False), file=sys.stderr)

        return 1

    except Exception as exc:
        # Keep an explicit final guard. For a live integration script, an
        # unexpected failure should still give a short, visible message and a
        # non-zero exit code, even if it is not one of our known exception
        # families.
        print("Live resume extraction failed unexpectedly.", file=sys.stderr)
        print(str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
