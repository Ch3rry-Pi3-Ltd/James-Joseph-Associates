"""
Persist the first real JobAdder job plus Dropbox job-spec pair into Supabase.

Why this script exists
----------------------
The project has now moved past source-shape inspection.

For `tw398`, we have already proved all of the following:

- the JobAdder job record exists
- the JobAdder applications carry the same vacancy context
- the Dropbox job-spec PDF exists and can be parsed
- the Dropbox `.eml` files preserve advert-response provenance
- some Dropbox CV files are exact mirrors of JobAdder candidate attachments

The next concrete question is narrower:

    "Can we persist one real job/opportunity plus one real Dropbox job-spec
    document into the canonical Supabase schema in a repeatable way?"

This script answers that question.

What this script does
---------------------
For one supplied JobAdder job and one Dropbox job-spec file, it:

1. calls the live backend JobAdder job-detail route
2. downloads the Dropbox job-spec file transiently through the local helper
3. extracts text from the file locally
4. builds the narrow job/job-spec persistence payload
5. persists the canonical job/document rows into Postgres
6. optionally writes a JSON report

What this script does not do
----------------------------
It does not:

- create document chunks or embeddings
- infer or persist required skills
- ingest applications or candidates
- decide the final long-term multi-source source-of-truth policy for jobs

Example
-------
Persist the real `tw398` job and Dropbox job-spec pair:

    uv run python scripts/persist_tw398_job_spec.py ^
        --jobadder-account 2236 ^
        --job-id 936462 ^
        --dropbox-account-id "dbid:AAD6tG3lvKRz-MJoBoYeedYkauD7t5D4IB0" ^
        --dropbox-path "/new dropbox/# DLV/LIVE JOBS - [Job Specs]/tw398 - B2C2 - KDB Developer x2/B2C2 - Snr. KDB Developer - London - 2026.pdf" ^
        --output-json temp\\tw398_job_spec_persisted.json
"""
# ruff: noqa: E402

from __future__ import annotations

import argparse
from datetime import datetime
from decimal import Decimal
import json
from pathlib import Path
import sys
from typing import Any
from uuid import UUID

import httpx

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.db.dropbox_oauth import get_dropbox_oauth_connection
from backend.services.dropbox_api import DropboxApiError, download_dropbox_file
from backend.services.dropbox_oauth import (
    is_dropbox_access_token_expired,
    refresh_dropbox_access_token,
)
from backend.services.job_spec_persistence import (
    build_jobadder_job_spec_persistence_payload,
    persist_jobadder_job_with_dropbox_job_spec,
)
from backend.services.resume_text import (
    ResumeTextExtractionError,
    extract_text_from_resume_bytes,
)
from backend.settings import get_settings

DEFAULT_API_BASE_URL = "https://james-joseph-associates.vercel.app"
DEFAULT_JOBADDER_ACCOUNT = 2236
DEFAULT_JOB_ID = 936462
DEFAULT_DROPBOX_ACCOUNT_ID = "dbid:AAD6tG3lvKRz-MJoBoYeedYkauD7t5D4IB0"
DEFAULT_DROPBOX_JOB_SPEC_PATH = (
    "/new dropbox/# DLV/LIVE JOBS - [Job Specs]/tw398 - B2C2 - KDB Developer x2/"
    "B2C2 - Snr. KDB Developer - London - 2026.pdf"
)


def build_argument_parser() -> argparse.ArgumentParser:
    """
    Build the CLI argument parser for the first job/job-spec persistence proof.

    Returns
    -------
    argparse.ArgumentParser
        Configured parser for one persistence run.

    Example
    -------
    A typical operator invocation looks like:

        --jobadder-account 2236 --job-id 936462 --output-json temp\\report.json
    """

    parser = argparse.ArgumentParser(
        description=(
            "Persist one real JobAdder job plus one Dropbox job-spec document "
            "into the canonical Supabase schema."
        )
    )
    parser.add_argument("--jobadder-account", type=int, default=DEFAULT_JOBADDER_ACCOUNT)
    parser.add_argument("--job-id", type=int, default=DEFAULT_JOB_ID)
    parser.add_argument("--dropbox-account-id", default=DEFAULT_DROPBOX_ACCOUNT_ID)
    parser.add_argument("--dropbox-path", default=DEFAULT_DROPBOX_JOB_SPEC_PATH)
    parser.add_argument(
        "--api-base-url",
        default=DEFAULT_API_BASE_URL,
        help="Base URL for the live backend that exposes the JobAdder job-detail route.",
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
    - blank Dropbox inputs
    - missing local Dropbox OAuth settings
    """

    if args.jobadder_account < 1:
        raise RuntimeError("JOBADDER_ACCOUNT must be at least 1.")
    if args.job_id < 1:
        raise RuntimeError("JOB_ID must be at least 1.")
    if not isinstance(args.dropbox_account_id, str) or args.dropbox_account_id.strip() == "":
        raise RuntimeError("DROPBOX_ACCOUNT_ID must be a non-empty string.")
    if not isinstance(args.dropbox_path, str) or args.dropbox_path.strip() == "":
        raise RuntimeError("DROPBOX_PATH must be a non-empty string.")
    if not isinstance(args.api_base_url, str) or args.api_base_url.strip() == "":
        raise RuntimeError("API_BASE_URL must be a non-empty string.")

    settings = get_settings()
    missing_settings: list[str] = []
    if settings.dropbox_client_id.strip() == "":
        missing_settings.append("DROPBOX_CLIENT_ID")
    if settings.dropbox_client_secret.strip() == "":
        missing_settings.append("DROPBOX_CLIENT_SECRET")
    if settings.dropbox_redirect_uri.strip() == "":
        missing_settings.append("DROPBOX_REDIRECT_URI")

    if missing_settings:
        raise RuntimeError(
            "Missing Dropbox OAuth settings: " + ", ".join(missing_settings)
        )


def fetch_live_jobadder_job_detail(
    *,
    api_base_url: str,
    jobadder_account: int,
    job_id: int,
) -> dict[str, Any]:
    """
    Fetch one JobAdder job-detail wrapper from the live backend.

    Parameters
    ----------
    api_base_url : str
        Base URL for the deployed backend.

    jobadder_account : int
        JobAdder account identifier used in the route path.

    job_id : int
        Job identifier used in the route path.

    Returns
    -------
    dict[str, Any]
        Decoded JSON wrapper returned by the backend.

    Example
    -------
    A successful payload looks like:

        {
            "jobadder_account": 2236,
            "job_id": 936462,
            "job": {
                "jobId": 936462,
                "jobTitle": "tw398 - KDB Developer",
            },
        }
    """

    route_path = f"/api/v1/integrations/jobadder/accounts/{jobadder_account}/jobs/{job_id}"
    request_url = api_base_url.rstrip("/") + route_path

    try:
        response = httpx.get(request_url, timeout=60.0)
    except httpx.HTTPError as exc:
        raise RuntimeError("Could not reach the live backend job-detail route.") from exc

    try:
        payload = response.json()
    except ValueError as exc:
        raise RuntimeError("The live backend job-detail route did not return JSON.") from exc

    if response.status_code >= 400:
        raise RuntimeError(
            f"JobAdder job-detail route failed: status={response.status_code}, payload={payload}"
        )

    if not isinstance(payload, dict):
        raise RuntimeError("The live backend job-detail route did not return an object.")

    return payload


def load_ready_dropbox_connection(*, dropbox_account_id: str) -> dict[str, Any]:
    """
    Load the stored Dropbox connection and refresh it if it is already expired.

    Parameters
    ----------
    dropbox_account_id : str
        Dropbox account identifier used to fetch the stored OAuth connection.

    Returns
    -------
    dict[str, Any]
        Stored Dropbox OAuth connection row containing a usable access token.
    """

    stored_connection = get_dropbox_oauth_connection(dropbox_account_id)

    if stored_connection is None:
        raise RuntimeError("Stored Dropbox connection was not found.")

    raw_access_token = stored_connection.get("access_token")
    raw_refresh_token = stored_connection.get("refresh_token")
    raw_scope = stored_connection.get("scope")
    raw_obtained_at = stored_connection.get("obtained_at")
    raw_expires_in_seconds = stored_connection.get("expires_in_seconds")

    if not isinstance(raw_access_token, str) or raw_access_token.strip() == "":
        raise RuntimeError("The stored Dropbox connection is missing an access token.")

    # Keep the Dropbox side resilient locally even though the JobAdder side is
    # coming through the live backend route. That keeps this script focused on
    # the persistence slice rather than being derailed by an avoidable expired
    # Dropbox access token.
    if is_dropbox_access_token_expired(
        obtained_at=raw_obtained_at,
        expires_in_seconds=raw_expires_in_seconds,
    ):
        if not isinstance(raw_refresh_token, str) or raw_refresh_token.strip() == "":
            raise RuntimeError("The stored Dropbox connection is missing a refresh token.")

        refreshed_token_set = refresh_dropbox_access_token(
            refresh_token=raw_refresh_token,
        )

        refreshed_access_token = refreshed_token_set.access_token
        merged_scope = (
            refreshed_token_set.scope
            if isinstance(refreshed_token_set.scope, str)
            and refreshed_token_set.scope.strip() != ""
            else (
                raw_scope
                if isinstance(raw_scope, str) and raw_scope.strip() != ""
                else None
            )
        )

        stored_connection = dict(stored_connection)
        stored_connection["access_token"] = refreshed_access_token
        stored_connection["scope"] = merged_scope

    return stored_connection


def build_dropbox_job_spec_file(
    *,
    access_token: str,
    path: str,
) -> dict[str, Any]:
    """
    Download one Dropbox job-spec file and build the persistence-side payload.

    Parameters
    ----------
    access_token : str
        Ready-to-use Dropbox access token.

    path : str
        Full Dropbox file path to the job-spec document.

    Returns
    -------
    dict[str, Any]
        File metadata plus extracted text ready for the persistence helper.

    Notes
    -----
    This first slice intentionally reuses the existing binary text-extraction
    helper, even though the function name mentions "resume". The important
    point here is not the label; it is the proven PDF/DOCX byte-to-text path.

    Example
    -------
    A successful result contains fields such as:

    - `path`
    - `file_name`
    - `content_type`
    - `byte_count`
    - `extractor`
    - `page_count`
    - `extracted_text`
    """

    try:
        downloaded_file = download_dropbox_file(
            access_token=access_token,
            path=path,
        )
    except DropboxApiError as exc:
        raise RuntimeError(
            f"Dropbox job-spec download failed: {exc}"
        ) from exc

    try:
        extracted_document = extract_text_from_resume_bytes(
            content_bytes=downloaded_file["content_bytes"],
            file_name=downloaded_file.get("file_name"),
            content_type=downloaded_file.get("content_type"),
        )
    except ResumeTextExtractionError as exc:
        raise RuntimeError(
            f"Dropbox job-spec text extraction failed: {exc}"
        ) from exc

    return {
        "path": path,
        "file_name": downloaded_file.get("file_name"),
        "content_type": downloaded_file.get("content_type"),
        "byte_count": len(downloaded_file["content_bytes"]),
        "file_metadata": downloaded_file.get("file_metadata"),
        "extractor": extracted_document.get("extractor"),
        "character_count": extracted_document.get("character_count"),
        "page_count": extracted_document.get("page_count"),
        "extracted_text": extracted_document.get("text"),
    }


def _make_json_safe_value(value: Any) -> Any:
    """
    Convert mixed operator report values into JSON-safe plain Python types.

    Example
    -------
    Values such as:

        Decimal("125000")
        UUID("...")
        datetime(...)

    are converted into strings before the report is written to disk.
    """

    if isinstance(value, Decimal):
        return str(value)

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
    Run the first real job/job-spec persistence proof.

    Returns
    -------
    int
        Process exit code.

    Example
    -------
    Running:

        uv run python scripts/persist_tw398_job_spec.py ^
            --output-json temp\\tw398_job_spec_persisted.json

    fetches the live JobAdder job detail, downloads the Dropbox PDF, persists
    the canonical rows, and writes a JSON summary report.
    """

    parser = build_argument_parser()
    args = parser.parse_args()

    validate_arguments(args)

    job_detail_response = fetch_live_jobadder_job_detail(
        api_base_url=args.api_base_url,
        jobadder_account=args.jobadder_account,
        job_id=args.job_id,
    )

    dropbox_connection = load_ready_dropbox_connection(
        dropbox_account_id=args.dropbox_account_id,
    )
    dropbox_access_token = dropbox_connection["access_token"]
    assert isinstance(dropbox_access_token, str)

    dropbox_job_spec_file = build_dropbox_job_spec_file(
        access_token=dropbox_access_token,
        path=args.dropbox_path,
    )

    # Build the payload explicitly first so the report can show exactly what we
    # decided to persist, not just the final database summary. That makes this
    # script a more useful operator checkpoint when the first live writes need
    # careful inspection.
    persistence_payload = build_jobadder_job_spec_persistence_payload(
        jobadder_account=args.jobadder_account,
        job_detail_response=job_detail_response,
        dropbox_account_id=args.dropbox_account_id,
        dropbox_job_spec_file=dropbox_job_spec_file,
    )
    persistence_summary = persist_jobadder_job_with_dropbox_job_spec(
        jobadder_account=args.jobadder_account,
        job_detail_response=job_detail_response,
        dropbox_account_id=args.dropbox_account_id,
        dropbox_job_spec_file=dropbox_job_spec_file,
    )

    report = {
        "job_detail_response": job_detail_response,
        "dropbox_job_spec_file": dropbox_job_spec_file,
        "persistence_payload": persistence_payload,
        "persistence_summary": persistence_summary,
    }

    if args.output_json is not None:
        args.output_json.parent.mkdir(parents=True, exist_ok=True)
        args.output_json.write_text(
            json.dumps(_make_json_safe_value(report), indent=2),
            encoding="utf-8",
        )

    print("Job/job-spec persistence completed.\n")
    print(f"JobAdder account: {args.jobadder_account}")
    print(f"Job ID: {args.job_id}")
    print(f"Dropbox path: {args.dropbox_path}")
    print(f"tw_code: {persistence_summary.get('tw_code')}")
    print(f"company_id: {persistence_summary.get('company_id')}")
    print(f"job_id: {persistence_summary.get('job_id')}")
    print(f"document_id: {persistence_summary.get('document_id')}")
    print(f"job_source_record_id: {persistence_summary.get('job_source_record_id')}")
    print(
        "job_spec_source_record_id: "
        f"{persistence_summary.get('job_spec_source_record_id')}"
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
