"""
Persist the first real JobAdder application/candidate pair into Supabase.

Why this script exists
----------------------
The project has already proved the surrounding source shape for `tw398`:

- the JobAdder job/opportunity exists
- JobAdder applications carry the vacancy context
- JobAdder candidate attachments are the structured CV source
- Dropbox `.eml` files preserve advert-response provenance
- Dropbox CV files can mirror JobAdder attachment bytes exactly

The next concrete question is narrower:

    "Can we persist one real JobAdder application and its candidate context
    into the canonical schema in a repeatable way?"

This script answers that question.

What this script does
---------------------
For one supplied JobAdder application ID, it:

1. calls the live backend application-detail route
2. reads the nested candidate ID from that application payload
3. calls the live backend candidate-detail route for that candidate
4. builds the narrow application persistence payload
5. persists the canonical person/candidate/application rows into Postgres
6. optionally writes a JSON report

What this script does not do
----------------------------
It does not:

- ingest attachments
- create document chunks or embeddings
- parse recruiter notes into first-class interactions
- decide the final long-term source-of-truth policy for every application field

Example
-------
Persist the real `tw398` sample application:

    uv run python scripts/persist_tw398_application.py ^
        --jobadder-account 2236 ^
        --application-id 12204918 ^
        --output-json temp\\tw398_application_persisted.json
"""
# ruff: noqa: E402

from __future__ import annotations

import argparse
from datetime import datetime
import json
from pathlib import Path
import sys
from typing import Any
from uuid import UUID

import httpx

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.services.application_persistence import (  # noqa: E402
    build_jobadder_application_persistence_payload,
    persist_jobadder_application_with_candidate,
)

DEFAULT_API_BASE_URL = "https://james-joseph-associates.vercel.app"
DEFAULT_JOBADDER_ACCOUNT = 2236
DEFAULT_APPLICATION_ID = 12204918


def build_argument_parser() -> argparse.ArgumentParser:
    """
    Build the CLI argument parser for the first application persistence proof.

    Example
    -------
    A typical operator invocation looks like:

        --jobadder-account 2236 --application-id 12204918 --output-json temp\\report.json
    """

    parser = argparse.ArgumentParser(
        description=(
            "Persist one real JobAdder application plus candidate snapshot "
            "into the canonical Supabase schema."
        )
    )
    parser.add_argument("--jobadder-account", type=int, default=DEFAULT_JOBADDER_ACCOUNT)
    parser.add_argument("--application-id", type=int, default=DEFAULT_APPLICATION_ID)
    parser.add_argument(
        "--api-base-url",
        default=DEFAULT_API_BASE_URL,
        help="Base URL for the live backend that exposes the JobAdder detail routes.",
    )
    parser.add_argument(
        "--output-json",
        type=Path,
        default=None,
        help="Optional JSON output path for the final persistence report.",
    )
    return parser


def validate_arguments(args: argparse.Namespace) -> None:
    """
    Validate the high-signal local arguments before any provider calls start.

    Example
    -------
    This helper rejects clearly invalid states such as:

    - non-positive JobAdder identifiers
    - blank backend base URLs
    """

    if args.jobadder_account < 1:
        raise RuntimeError("JOBADDER_ACCOUNT must be at least 1.")
    if args.application_id < 1:
        raise RuntimeError("APPLICATION_ID must be at least 1.")
    if not isinstance(args.api_base_url, str) or args.api_base_url.strip() == "":
        raise RuntimeError("API_BASE_URL must be a non-empty string.")


def fetch_live_jobadder_application_detail(
    *,
    api_base_url: str,
    jobadder_account: int,
    application_id: int,
) -> dict[str, Any]:
    """
    Fetch one JobAdder application-detail wrapper from the live backend.

    Example
    -------
    A successful payload looks like:

        {
            "jobadder_account": 2236,
            "application_id": 12204918,
            "application": {...}
        }
    """

    route_path = (
        f"/api/v1/integrations/jobadder/accounts/{jobadder_account}/"
        f"applications/{application_id}"
    )
    return _fetch_live_backend_json(
        request_url=api_base_url.rstrip("/") + route_path,
        failure_label="JobAdder application-detail route",
    )


def fetch_live_jobadder_candidate_detail(
    *,
    api_base_url: str,
    jobadder_account: int,
    candidate_id: int,
) -> dict[str, Any]:
    """
    Fetch one JobAdder candidate-detail wrapper from the live backend.

    Example
    -------
    A successful payload looks like:

        {
            "jobadder_account": 2236,
            "candidate_id": 17071060,
            "candidate": {...}
        }
    """

    route_path = (
        f"/api/v1/integrations/jobadder/accounts/{jobadder_account}/"
        f"candidates/{candidate_id}"
    )
    return _fetch_live_backend_json(
        request_url=api_base_url.rstrip("/") + route_path,
        failure_label="JobAdder candidate-detail route",
    )


def _fetch_live_backend_json(*, request_url: str, failure_label: str) -> dict[str, Any]:
    """
    Fetch one JSON object from the live backend and fail clearly when it breaks.

    Example
    -------
    This helper is used for both:

    - the application-detail route
    - the candidate-detail route

    so the script keeps one consistent error/reporting rule for live reads.
    """

    try:
        response = httpx.get(request_url, timeout=60.0)
    except httpx.HTTPError as exc:
        raise RuntimeError(f"Could not reach the live backend {failure_label}.") from exc

    try:
        payload = response.json()
    except ValueError as exc:
        raise RuntimeError(
            f"The live backend {failure_label} did not return JSON."
        ) from exc

    if response.status_code >= 400:
        raise RuntimeError(
            f"{failure_label} failed: status={response.status_code}, payload={payload}"
        )

    if not isinstance(payload, dict):
        raise RuntimeError(f"The live backend {failure_label} did not return an object.")

    return payload


def _extract_candidate_id_from_application_detail(
    application_detail_response: dict[str, Any],
) -> int:
    """
    Extract the nested candidate ID from one application-detail wrapper.

    Example
    -------
    A payload such as:

        {"application": {"candidate": {"candidateId": 17071060}}}

    yields:

        17071060
    """

    application_payload = application_detail_response.get("application")
    if not isinstance(application_payload, dict):
        raise RuntimeError("Application detail response is missing `application`.")

    candidate_payload = application_payload.get("candidate")
    if not isinstance(candidate_payload, dict):
        raise RuntimeError("Application detail response is missing `application.candidate`.")

    candidate_id = candidate_payload.get("candidateId")
    try:
        resolved_candidate_id = int(candidate_id)
    except (TypeError, ValueError) as exc:
        raise RuntimeError(
            "Application detail response is missing a valid candidate ID."
        ) from exc

    if resolved_candidate_id < 1:
        raise RuntimeError(
            "Application detail response candidate ID must be at least 1."
        )

    return resolved_candidate_id


def _make_json_safe_value(value: Any) -> Any:
    """
    Convert mixed operator report values into JSON-safe plain Python types.

    Example
    -------
    Values such as:

        UUID("...")
        datetime(...)

    are converted into strings before the report is written to disk.
    """

    if isinstance(value, UUID):
        return str(value)

    if isinstance(value, datetime):
        return value.isoformat()

    if isinstance(value, dict):
        return {
            key: _make_json_safe_value(nested_value)
            for key, nested_value in value.items()
        }

    if isinstance(value, list):
        return [_make_json_safe_value(item) for item in value]

    if isinstance(value, tuple):
        return [_make_json_safe_value(item) for item in value]

    return value


def main() -> int:
    """
    Run the first real application persistence proof.

    Example
    -------
    Running:

        uv run python scripts/persist_tw398_application.py ^
            --output-json temp\\tw398_application_persisted.json

    fetches the live JobAdder application detail and candidate detail,
    persists the canonical rows, and writes a JSON summary report.
    """

    parser = build_argument_parser()
    args = parser.parse_args()

    validate_arguments(args)

    application_detail_response = fetch_live_jobadder_application_detail(
        api_base_url=args.api_base_url,
        jobadder_account=args.jobadder_account,
        application_id=args.application_id,
    )
    candidate_id = _extract_candidate_id_from_application_detail(
        application_detail_response
    )
    candidate_detail_response = fetch_live_jobadder_candidate_detail(
        api_base_url=args.api_base_url,
        jobadder_account=args.jobadder_account,
        candidate_id=candidate_id,
    )

    # Build the payload explicitly first so the report shows both:
    # - the live source material we used
    # - the exact flattened persistence decisions we made
    #
    # That makes the script a useful operator checkpoint when the first live
    # canonical writes need careful inspection.
    persistence_payload = build_jobadder_application_persistence_payload(
        jobadder_account=args.jobadder_account,
        application_detail_response=application_detail_response,
        candidate_detail_response=candidate_detail_response,
    )
    persistence_summary = persist_jobadder_application_with_candidate(
        jobadder_account=args.jobadder_account,
        application_detail_response=application_detail_response,
        candidate_detail_response=candidate_detail_response,
    )

    report = {
        "application_detail_response": application_detail_response,
        "candidate_detail_response": candidate_detail_response,
        "persistence_payload": persistence_payload,
        "persistence_summary": persistence_summary,
    }

    if args.output_json is not None:
        args.output_json.parent.mkdir(parents=True, exist_ok=True)
        args.output_json.write_text(
            json.dumps(_make_json_safe_value(report), indent=2),
            encoding="utf-8",
        )

    print("Application persistence completed.\n")
    print(f"JobAdder account: {args.jobadder_account}")
    print(f"Application ID: {args.application_id}")
    print(f"Candidate ID: {candidate_id}")
    print(f"tw_code: {persistence_summary.get('tw_code')}")
    print(f"person_id: {persistence_summary.get('person_id')}")
    print(f"candidate_id: {persistence_summary.get('candidate_id')}")
    print(f"job_id: {persistence_summary.get('job_id')}")
    print(f"application_id: {persistence_summary.get('application_id')}")
    print(
        "candidate_source_record_id: "
        f"{persistence_summary.get('candidate_source_record_id')}"
    )
    print(
        "application_source_record_id: "
        f"{persistence_summary.get('application_source_record_id')}"
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
