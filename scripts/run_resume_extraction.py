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

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

from backend.llm.models import ModelProfile, ModelProvider, ModelPurpose
from backend.llm.providers import (
    LLMProviderConfigurationError,
    build_langchain_chat_model,
)
from backend.services.resume_extraction import (
    DEFAULT_RESUME_EXTRACTION_MODEL_PROFILE,
    ResumeExtractionError,
    extract_jobadder_candidate_resume_profile,
)
from backend.settings import get_settings


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

    # Keep model controls overridable from the CLI because real extraction work
    # often needs quick empirical comparison:
    # - stronger vs cheaper model
    # - tighter token ceiling
    # - deterministic vs slightly looser temperature
    #
    # This avoids hard-coding every experiment back into the service module.
    parser.add_argument(
        "--model-name",
        default=DEFAULT_RESUME_EXTRACTION_MODEL_PROFILE.model_name,
        help=(
            "Model name to use for extraction. Defaults to the module's "
            "configured extraction model."
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

    return ModelProfile(
        provider=ModelProvider.OPENAI,
        model_name=args.model_name,
        purpose=ModelPurpose.EXTRACTION,
        temperature=args.temperature,
        max_output_tokens=args.max_output_tokens,
    )


def validate_live_run_preconditions() -> None:
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
    - an OpenAI API key available through settings
    - the minimum JobAdder OAuth application settings needed by the wider
      integration layer

    This helper does not:
    - verify the OpenAI key is valid
    - verify the JobAdder token store contains a usable connection
    - test network connectivity

    Those are real runtime/integration concerns and should fail in their own
    natural place.

    Example
    -------
    If `.env.local` has no `OPENAI_API_KEY`, this helper raises early with a
    clear message rather than letting the provider constructor fail later with a
    less contextual stack trace.

    In plain language:

    - check the basics first
    - fail early when the local environment is obviously incomplete
    """

    settings = get_settings()

    # The provider layer can fall back to settings now, so this script should
    # check the settings-backed path up front and fail with a message that is
    # specific to this workflow.
    if settings.openai_api_key.strip() == "":
        raise RuntimeError(
            "OPENAI_API_KEY is not configured. Set it in `.env.local` or the "
            "shell environment before running a live extraction."
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
    emails = structured.get("emails", [])
    phones = structured.get("phones", [])
    evidence_notes = structured.get("evidence_notes", [])
    ambiguity_notes = structured.get("ambiguity_notes", [])
    employment_history = structured.get("employment_history", [])
    education = structured.get("education", [])

    lines = [
        "Live resume extraction completed.",
        "",
        f"Source system: {result.get('source_system')}",
        f"Source candidate ID: {result.get('source_candidate_id')}",
        f"JobAdder account: {result.get('jobadder_account')}",
        f"Candidate: {candidate_context.get('first_name')} {candidate_context.get('last_name')}",
        f"Resume file: {latest_resume.get('file_name')}",
        f"Model: {result.get('model_profile', {}).get('model_name')}",
        "",
        f"Current title: {structured.get('current_title')}",
        f"Current employer: {structured.get('current_employer')}",
        f"Location: {structured.get('location')}",
        f"Emails: {', '.join(emails) if emails else '(none)'}",
        f"Phones: {', '.join(phones) if phones else '(none)'}",
        f"Skills: {', '.join(skills) if skills else '(none)'}",
        f"Employment entries: {len(employment_history)}",
        f"Education entries: {len(education)}",
        f"Evidence notes: {len(evidence_notes)}",
        f"Ambiguity notes: {len(ambiguity_notes)}",
    ]

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

    validate_live_run_preconditions()

    model_profile = build_runtime_model_profile(args)

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
        result = run_live_resume_extraction(args)

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
            print(json.dumps(json_payload, indent=2, ensure_ascii=False))

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