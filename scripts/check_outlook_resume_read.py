"""
Download one or more Outlook message attachments transiently and run local
text extraction.

Why this script exists
----------------------
We have already proved:

- Tom's Outlook OAuth connection is stored correctly
- the backend can read Outlook folders and advert-response messages
- the backend can list attachment metadata through Microsoft Graph

The next proof point is different:

    "Can a real Outlook advert-response attachment be downloaded and passed
    through the same local text-extraction layer that already works for
    JobAdder resumes and Dropbox CV files?"

This script answers that question.

What this script does
---------------------
For each requested Outlook message attachment, it:

1. loads the stored Outlook OAuth connection
2. refreshes the access token if it is already expired
3. downloads the attachment transiently into memory
4. runs the existing resume text-extraction helper
5. prints a small success/failure summary
6. optionally writes a JSON report

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
Check one real Outlook attachment:

    uv run python scripts/check_outlook_resume_read.py ^
        --microsoft-user-id "b4dd6a5f-8e27-4745-9369-e117121382ed" ^
        --message-id "AAMkAGI2..." ^
        --attachment-id "AAMkAGI2...AAABEgAQ..."

Write the proof report to JSON:

    uv run python scripts/check_outlook_resume_read.py ^
        --microsoft-user-id "b4dd6a5f-8e27-4745-9369-e117121382ed" ^
        --message-id "AAMkAGI2..." ^
        --attachment-id "AAMkAGI2...AAABEgAQ..." ^
        --output-json temp\\outlook_resume_read_check.json
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

from backend.db.outlook_oauth import (
    get_outlook_oauth_connection,
    save_outlook_oauth_connection,
)
from backend.services.outlook_api import (
    OutlookApiError,
    download_outlook_message_file_attachment,
)
from backend.services.outlook_oauth import (
    OutlookTokenSet,
    is_outlook_access_token_expired,
    refresh_outlook_access_token,
)
from backend.services.resume_text import (
    ResumeTextExtractionError,
    extract_text_from_resume_bytes,
)
from backend.settings import get_settings


def build_argument_parser() -> argparse.ArgumentParser:
    """
    Build the CLI argument parser for Outlook resume-read checks.

    Returns
    -------
    argparse.ArgumentParser
        Configured parser for transient Outlook attachment-read verification.

    Example
    -------
    A typical operator invocation looks like:

        --microsoft-user-id aaaa-bbbb --message-id AAMkAGI2... --attachment-id AAMkAGI2...AAABEgAQ...
    """

    parser = argparse.ArgumentParser(
        description=(
            "Download one or more Outlook message attachments transiently and "
            "run local resume text extraction against them."
        )
    )
    parser.add_argument(
        "--microsoft-user-id",
        required=True,
        help="Microsoft user identifier used to load the stored OAuth connection.",
    )
    parser.add_argument(
        "--mailbox",
        default=None,
        help=(
            "Optional delegated mailbox identifier such as a shared mailbox "
            "email address."
        ),
    )
    parser.add_argument(
        "--message-id",
        action="append",
        required=True,
        help=(
            "Outlook message identifier to test. Pass this flag once per "
            "attachment proof item."
        ),
    )
    parser.add_argument(
        "--attachment-id",
        action="append",
        required=True,
        help=(
            "Outlook attachment identifier to test. Pass this flag once per "
            "attachment proof item, in the same order as --message-id."
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
    Validate the high-signal local arguments before any Graph read starts.

    Parameters
    ----------
    args : argparse.Namespace
        Parsed CLI arguments for the current run.

    Example
    -------
    This helper rejects clearly invalid states such as:

    - a blank Microsoft user ID
    - mismatched message-id and attachment-id counts
    - missing local Microsoft OAuth settings
    """

    if (
        not isinstance(args.microsoft_user_id, str)
        or args.microsoft_user_id.strip() == ""
    ):
        raise RuntimeError("MICROSOFT_USER_ID must be a non-empty string.")

    if not isinstance(args.message_id, list) or len(args.message_id) == 0:
        raise RuntimeError("At least one --message-id value is required.")

    if not isinstance(args.attachment_id, list) or len(args.attachment_id) == 0:
        raise RuntimeError("At least one --attachment-id value is required.")

    if len(args.message_id) != len(args.attachment_id):
        raise RuntimeError(
            "--message-id and --attachment-id must be supplied the same number of times."
        )

    settings = get_settings()
    missing_settings: list[str] = []

    if settings.microsoft_client_id.strip() == "":
        missing_settings.append("MICROSOFT_CLIENT_ID")
    if settings.microsoft_client_secret.strip() == "":
        missing_settings.append("MICROSOFT_CLIENT_SECRET")
    if settings.microsoft_redirect_uri.strip() == "":
        missing_settings.append("MICROSOFT_REDIRECT_URI")

    if missing_settings:
        raise RuntimeError(
            "Missing Outlook OAuth settings: " + ", ".join(missing_settings)
        )


def load_ready_outlook_connection(*, microsoft_user_id: str) -> dict[str, Any]:
    """
    Load the stored Outlook connection and refresh it if it is already expired.

    Parameters
    ----------
    microsoft_user_id : str
        Microsoft user identifier used to fetch the stored OAuth connection.

    Returns
    -------
    dict[str, Any]
        Stored Outlook OAuth connection row containing a usable access token.

    Raises
    ------
    RuntimeError
        If the stored connection is missing or incomplete.

    Example
    -------
    Calling:

        load_ready_outlook_connection(
            microsoft_user_id="aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
        )

    returns a connection row that is safe to use for the immediate attachment
    read attempt.
    """

    stored_connection = get_outlook_oauth_connection(microsoft_user_id)

    if stored_connection is None:
        raise RuntimeError("Stored Outlook connection was not found.")

    raw_access_token = stored_connection.get("access_token")
    raw_refresh_token = stored_connection.get("refresh_token")
    raw_obtained_at = stored_connection.get("obtained_at")
    raw_expires_in_seconds = stored_connection.get("expires_in_seconds")

    if not isinstance(raw_access_token, str) or raw_access_token.strip() == "":
        raise RuntimeError("The stored Outlook connection is missing an access token.")

    # Refresh proactively when the stored token is already expired. That keeps
    # the attachment-read proof focused on the document path itself rather than
    # being derailed by an avoidable expired-token failure.
    if is_outlook_access_token_expired(
        obtained_at=raw_obtained_at,
        expires_in_seconds=raw_expires_in_seconds,
    ):
        if not isinstance(raw_refresh_token, str) or raw_refresh_token.strip() == "":
            raise RuntimeError(
                "The stored Outlook connection is missing a refresh token."
            )

        refreshed_token_set = refresh_outlook_access_token(
            refresh_token=raw_refresh_token,
        )

        # Microsoft refresh responses are not guaranteed to repeat every
        # identity hint we already captured during the original OAuth callback.
        # Preserve the stable stored identity fields so the refreshed
        # connection remains writable and usable for later Graph reads.
        merged_raw_payload = dict(refreshed_token_set.raw_payload)
        merged_raw_payload.setdefault("refresh_token", raw_refresh_token)
        merged_raw_payload.setdefault(
            "oid",
            stored_connection.get("microsoft_user_id"),
        )
        merged_raw_payload.setdefault(
            "tid",
            stored_connection.get("tenant_id"),
        )
        merged_raw_payload.setdefault(
            "preferred_username",
            stored_connection.get("user_principal_name"),
        )

        refreshed_token_set = OutlookTokenSet(
            access_token=refreshed_token_set.access_token,
            token_type=refreshed_token_set.token_type,
            expires_in=refreshed_token_set.expires_in,
            refresh_token=refreshed_token_set.refresh_token or raw_refresh_token,
            scope=refreshed_token_set.scope or stored_connection.get("scope"),
            microsoft_user_id=(
                refreshed_token_set.microsoft_user_id
                or stored_connection.get("microsoft_user_id")
            ),
            tenant_id=(
                refreshed_token_set.tenant_id or stored_connection.get("tenant_id")
            ),
            user_principal_name=(
                refreshed_token_set.user_principal_name
                or stored_connection.get("user_principal_name")
            ),
            raw_payload=merged_raw_payload,
        )

        stored_connection = save_outlook_oauth_connection(refreshed_token_set)

    return stored_connection


def check_outlook_resume_attachment(
    *,
    access_token: str,
    message_id: str,
    attachment_id: str,
    mailbox: str | None = None,
) -> dict[str, Any]:
    """
    Download one Outlook attachment and run the local resume text-extraction layer.

    Parameters
    ----------
    access_token : str
        Ready-to-use Microsoft Graph access token.

    message_id : str
        Outlook message identifier that owns the attachment.

    attachment_id : str
        Outlook attachment identifier to test.

    mailbox : str | None
        Optional delegated mailbox identifier.

    Returns
    -------
    dict[str, Any]
        Small structured success/failure report for this attachment.

    Example
    -------
    A successful report includes:

    - attachment metadata
    - extractor name
    - extracted character count
    """

    download_result = download_outlook_message_file_attachment(
        access_token=access_token,
        message_id=message_id,
        attachment_id=attachment_id,
        mailbox=mailbox,
    )

    extraction_result = extract_text_from_resume_bytes(
        content_bytes=download_result["content_bytes"],
        file_name=download_result.get("file_name"),
        content_type=download_result.get("content_type"),
    )

    return {
        "status": "ok",
        "message_id": message_id,
        "attachment_id": attachment_id,
        "mailbox": mailbox,
        "file_name": download_result.get("file_name"),
        "content_type": download_result.get("content_type"),
        "byte_count": len(download_result["content_bytes"]),
        "extractor": extraction_result.get("extractor"),
        "page_count": extraction_result.get("page_count"),
        "character_count": extraction_result.get("character_count"),
    }


def main() -> int:
    """
    Run the Outlook attachment-read proof from the command line.

    Returns
    -------
    int
        Process exit code. Zero means every requested attachment was read and
        parsed successfully.

    Example
    -------
    A successful run prints a short operator summary such as:

        [ok] Candidate CV.pdf | pypdf | 6185 chars

    and optionally writes a JSON report when `--output-json` is supplied.
    """

    parser = build_argument_parser()
    args = parser.parse_args()

    try:
        validate_arguments(args)
        stored_connection = load_ready_outlook_connection(
            microsoft_user_id=args.microsoft_user_id,
        )
    except RuntimeError as exc:
        print(f"[error] {exc}")
        return 1

    access_token = stored_connection["access_token"]
    results: list[dict[str, Any]] = []
    overall_success = True

    # Walk the message/attachment pairs in lockstep so each proof item is
    # traceable back to one concrete Outlook email and one concrete file.
    #
    # That matters when an operator is checking one `tw...` mailbox folder and
    # needs to know exactly which advert-response item failed.
    for message_id, attachment_id in zip(
        args.message_id,
        args.attachment_id,
        strict=True,
    ):
        try:
            result = check_outlook_resume_attachment(
                access_token=access_token,
                message_id=message_id,
                attachment_id=attachment_id,
                mailbox=args.mailbox,
            )
            results.append(result)
            print(
                "[ok] "
                f"{result['file_name']} | "
                f"{result['extractor']} | "
                f"{result['character_count']} chars"
            )
        except (OutlookApiError, ResumeTextExtractionError) as exc:
            overall_success = False
            failure_result = {
                "status": "error",
                "message_id": message_id,
                "attachment_id": attachment_id,
                "mailbox": args.mailbox,
                "error_type": exc.__class__.__name__,
                "message": str(exc),
            }
            results.append(failure_result)
            print(
                "[error] "
                f"message_id={message_id} attachment_id={attachment_id} | {exc}"
            )

    report = {
        "microsoft_user_id": args.microsoft_user_id,
        "mailbox": args.mailbox,
        "checked_item_count": len(results),
        "all_passed": overall_success,
        "results": results,
    }

    if args.output_json is not None:
        args.output_json.parent.mkdir(parents=True, exist_ok=True)
        args.output_json.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(f"[info] Wrote JSON report to {args.output_json}")

    return 0 if overall_success else 1


if __name__ == "__main__":
    raise SystemExit(main())
