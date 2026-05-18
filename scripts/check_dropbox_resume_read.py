"""
Download one or more Dropbox CV files transiently and run local text extraction.

Why this script exists
----------------------
We have already proved:

- Tom's Dropbox OAuth connection is stored correctly
- the backend can read Dropbox account metadata
- the backend can list Dropbox folders through the local helper path

The next proof point is different:

    "Can a real Dropbox CV file be downloaded and passed through the same
    local text-extraction layer that already works for JobAdder resumes?"

This script answers that question.

What this script does
---------------------
For each requested Dropbox file path, it:

1. loads the stored Dropbox OAuth connection
2. downloads the file transiently into memory
3. runs the existing resume text-extraction helper
4. prints a small success/failure summary
5. optionally writes a JSON report

What this script does not do
----------------------------
It does not:

- persist the file locally
- write extracted data to Supabase
- call any LLM
- classify candidate matches
- support legacy `.doc` extraction

Examples
--------
Check one PDF and one DOCX from the `tw394 = to CVR` folder:

    uv run python scripts/check_dropbox_resume_read.py ^
        --dropbox-account-id "dbid:AAD6tG3lvKRz-MJoBoYeedYkauD7t5D4IB0" ^
        --path "/tw394 = to CVR/Jay Thakrar (351046050 - totaljobs).pdf" ^
        --path "/tw394 = to CVR/Aman-Raja_cv-library.docx"

Write the proof report to JSON:

    uv run python scripts/check_dropbox_resume_read.py ^
        --dropbox-account-id "dbid:AAD6tG3lvKRz-MJoBoYeedYkauD7t5D4IB0" ^
        --path "/tw394 = to CVR/Jay Thakrar (351046050 - totaljobs).pdf" ^
        --output-json temp\\dropbox_resume_read_check.json
"""
# ruff: noqa: E402

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.db.dropbox_oauth import get_dropbox_oauth_connection
from backend.services.dropbox_api import DropboxApiError, download_dropbox_file
from backend.services.dropbox_oauth import (
    is_dropbox_access_token_expired,
    refresh_dropbox_access_token,
)
from backend.services.resume_text import (
    ResumeTextExtractionError,
    extract_text_from_resume_bytes,
)
from backend.settings import get_settings


def build_argument_parser() -> argparse.ArgumentParser:
    """
    Build the CLI argument parser for Dropbox resume-read checks.

    Returns
    -------
    argparse.ArgumentParser
        Configured parser for transient Dropbox resume-read verification.

    Example
    -------
    A typical operator invocation looks like:

        --dropbox-account-id dbid:AAExample --path "/tw394 = to CVR/example.pdf"
    """

    parser = argparse.ArgumentParser(
        description=(
            "Download one or more Dropbox CV files transiently and run local "
            "resume text extraction against them."
        )
    )
    parser.add_argument(
        "--dropbox-account-id",
        required=True,
        help="Dropbox account identifier used to load the stored OAuth connection.",
    )
    parser.add_argument(
        "--path",
        action="append",
        required=True,
        help=(
            "Full Dropbox file path to test. Pass this flag more than once to "
            "check multiple files in one run."
        ),
    )
    parser.add_argument(
        "--output-json",
        type=Path,
        default=None,
        help="Optional JSON output path for the final check report.",
    )
    return parser


def validate_arguments(args: argparse.Namespace) -> None:
    """
    Validate the high-signal local arguments before any Dropbox read starts.

    Parameters
    ----------
    args : argparse.Namespace
        Parsed CLI arguments for the current run.

    Example
    -------
    This helper rejects clearly invalid states such as:

    - a blank Dropbox account ID
    - zero requested file paths
    - missing local Dropbox OAuth settings
    """

    if not isinstance(args.dropbox_account_id, str) or args.dropbox_account_id.strip() == "":
        raise RuntimeError("DROPBOX_ACCOUNT_ID must be a non-empty string.")

    if not isinstance(args.path, list) or len(args.path) == 0:
        raise RuntimeError("At least one --path value is required.")

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

    Raises
    ------
    RuntimeError
        If the stored connection is missing or incomplete.

    Example
    -------
    Calling:

        load_ready_dropbox_connection(dropbox_account_id="dbid:AAExample")

    returns a connection row that is safe to use for the immediate file-read
    attempt.
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

    # Refresh proactively when the stored token is already expired. That keeps
    # the file-read proof focused on the document path itself rather than being
    # derailed by an avoidable expired-token failure.
    if is_dropbox_access_token_expired(
        obtained_at=raw_obtained_at,
        expires_in_seconds=raw_expires_in_seconds,
    ):
        if not isinstance(raw_refresh_token, str) or raw_refresh_token.strip() == "":
            raise RuntimeError(
                "The stored Dropbox connection is missing a refresh token."
            )

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


def check_dropbox_resume_path(
    *,
    access_token: str,
    path: str,
) -> dict[str, Any]:
    """
    Download one Dropbox file and run the local resume text-extraction layer.

    Parameters
    ----------
    access_token : str
        Ready-to-use Dropbox access token.

    path : str
        Full Dropbox file path to test.

    Returns
    -------
    dict[str, Any]
        Small structured result describing whether the file could be downloaded
        and parsed successfully.

    Example
    -------
    A successful result contains fields such as:

    - `status`
    - `path`
    - `file_name`
    - `content_type`
    - `extractor`
    - `character_count`
    """

    try:
        downloaded_file = download_dropbox_file(
            access_token=access_token,
            path=path,
        )
    except DropboxApiError as exc:
        return {
            "status": "download_failed",
            "path": path,
            "reason": str(exc),
            "provider_status_code": exc.status_code,
            "endpoint_url": exc.endpoint_url,
            "provider_response_body": exc.response_body,
        }

    try:
        extracted_resume = extract_text_from_resume_bytes(
            content_bytes=downloaded_file["content_bytes"],
            file_name=downloaded_file.get("file_name"),
            content_type=downloaded_file.get("content_type"),
        )
    except ResumeTextExtractionError as exc:
        return {
            "status": "extraction_failed",
            "path": path,
            "file_name": downloaded_file.get("file_name"),
            "content_type": downloaded_file.get("content_type"),
            "byte_count": len(downloaded_file["content_bytes"]),
            "reason": str(exc),
            "resume_text_stage": exc.stage,
            "details": exc.details,
        }

    extracted_text = extracted_resume.get("text")
    text_preview = (
        extracted_text[:300]
        if isinstance(extracted_text, str)
        else None
    )

    return {
        "status": "ok",
        "path": path,
        "file_name": downloaded_file.get("file_name"),
        "content_type": downloaded_file.get("content_type"),
        "byte_count": len(downloaded_file["content_bytes"]),
        "extractor": extracted_resume.get("extractor"),
        "character_count": extracted_resume.get("character_count"),
        "page_count": extracted_resume.get("page_count"),
        "text_preview": text_preview,
    }


def main() -> int:
    """
    Run the Dropbox resume-read proof script.

    Returns
    -------
    int
        Process exit code.

    Example
    -------
    Running:

        uv run python scripts/check_dropbox_resume_read.py ^
            --dropbox-account-id dbid:AAExample ^
            --path "/tw394 = to CVR/example.pdf"

    prints a concise summary and exits non-zero only if the overall run fails
    catastrophically before per-file checks can complete.
    """

    parser = build_argument_parser()
    args = parser.parse_args()

    validate_arguments(args)

    connection = load_ready_dropbox_connection(
        dropbox_account_id=args.dropbox_account_id,
    )
    access_token = connection["access_token"]
    assert isinstance(access_token, str)

    results = [
        check_dropbox_resume_path(
            access_token=access_token,
            path=path,
        )
        for path in args.path
    ]

    report = {
        "dropbox_account_id": args.dropbox_account_id,
        "checked_file_count": len(results),
        "results": results,
    }

    if args.output_json is not None:
        args.output_json.parent.mkdir(parents=True, exist_ok=True)
        args.output_json.write_text(
            json.dumps(report, indent=2),
            encoding="utf-8",
        )

    print("Dropbox resume-read check completed.\n")
    print(f"Dropbox account ID: {args.dropbox_account_id}")
    print(f"Checked files: {len(results)}")

    for result in results:
        print("")
        print(f"Path: {result['path']}")
        print(f"Status: {result['status']}")

        if result["status"] == "ok":
            print(f"File: {result['file_name']}")
            print(f"Content type: {result['content_type']}")
            print(f"Extractor: {result['extractor']}")
            print(f"Character count: {result['character_count']}")
            print(f"Page count: {result['page_count']}")
            print(f"Text preview: {result['text_preview']}")
        else:
            print(f"Reason: {result['reason']}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
