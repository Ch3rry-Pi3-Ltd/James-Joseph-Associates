"""
Download one or more Dropbox `.eml` files transiently and parse their email
structure.

Why this script exists
----------------------
We have already proved:

- Tom's Dropbox OAuth connection is valid
- Dropbox CV files can be downloaded transiently
- PDF and DOCX files can be parsed through the existing extraction layer
- `tw...` vacancy codes appear across JobAdder and Dropbox

The next proof point is different:

    "What does one real advert-response email actually contain?"

This script answers that question for saved `.eml` files by pulling out the
parts we care about for provenance and reconciliation:

- sender
- subject
- date
- vacancy-code mentions
- attachment names
- a short plain-text body preview where available

What this script does
---------------------
For each requested Dropbox `.eml` path, it:

1. loads the stored Dropbox OAuth connection
2. refreshes the token locally if it is already expired
3. downloads the `.eml` file transiently into memory
4. parses the email structure with Python's standard email library
5. optionally extracts the embedded attachments to a local output directory
6. prints a concise summary
7. optionally writes a JSON report

What this script does not do
----------------------------
It does not:

- persist the email locally
- persist parsed data to Supabase
- ingest attachments into the CV pipeline
- parse Outlook/Exchange mailboxes directly

Examples
--------
Inspect one `tw398` advert-response email:

    uv run python scripts/check_dropbox_eml_parse.py ^
        --dropbox-account-id "dbid:AAD6tG3lvKRz-MJoBoYeedYkauD7t5D4IB0" ^
        --path "/### BIG BAD CV ARCHIVE inc. RFL/##############ACHTUNG! in RFL!/shan.lingeswaran@hotmail.co.uk - Totaljobs - Suitable application for KDB Developer tw398.eml"

Write the parsed result to JSON:

    uv run python scripts/check_dropbox_eml_parse.py ^
        --dropbox-account-id "dbid:AAD6tG3lvKRz-MJoBoYeedYkauD7t5D4IB0" ^
        --path "/.../example tw398.eml" ^
        --output-json temp\\dropbox_eml_parse_check_tw398.json

Extract the embedded attachment to a local folder for inspection:

    uv run python scripts/check_dropbox_eml_parse.py ^
        --dropbox-account-id "dbid:AAD6tG3lvKRz-MJoBoYeedYkauD7t5D4IB0" ^
        --path "/.../example tw398.eml" ^
        --extract-attachments-dir temp\\dropbox_eml_attachments
"""
# ruff: noqa: E402

from __future__ import annotations

import argparse
import hashlib
import json
from email import policy
from email.message import EmailMessage
from email.parser import BytesParser
from email.utils import getaddresses
from pathlib import Path
import re
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
from backend.settings import get_settings

TW_CODE_PATTERN = re.compile(r"\btw\d+\b", re.IGNORECASE)


def build_argument_parser() -> argparse.ArgumentParser:
    """
    Build the CLI argument parser for Dropbox `.eml` inspection.

    Returns
    -------
    argparse.ArgumentParser
        Configured parser for transient Dropbox email parsing checks.

    Example
    -------
    A typical operator invocation looks like:

        --dropbox-account-id dbid:AAExample --path "/archive/example tw398.eml"
    """

    parser = argparse.ArgumentParser(
        description=(
            "Download one or more Dropbox .eml files transiently and parse "
            "their headers, body preview, and attachment names."
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
            "Full Dropbox .eml file path to inspect. Pass this flag more than "
            "once to inspect multiple emails in one run."
        ),
    )
    parser.add_argument(
        "--output-json",
        type=Path,
        default=None,
        help="Optional JSON output path for the final parsed-email report.",
    )
    parser.add_argument(
        "--extract-attachments-dir",
        type=Path,
        default=None,
        help=(
            "Optional local directory where embedded email attachments should "
            "be written for manual inspection."
        ),
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
    - zero requested paths
    - non-`.eml` target paths
    - missing local Dropbox OAuth settings
    """

    if not isinstance(args.dropbox_account_id, str) or args.dropbox_account_id.strip() == "":
        raise RuntimeError("DROPBOX_ACCOUNT_ID must be a non-empty string.")

    if not isinstance(args.path, list) or len(args.path) == 0:
        raise RuntimeError("At least one --path value is required.")

    for path in args.path:
        if not isinstance(path, str) or path.strip() == "":
            raise RuntimeError("Each --path value must be a non-empty string.")
        if not path.lower().endswith(".eml"):
            raise RuntimeError("This script only accepts .eml paths.")

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

    returns a connection row that is safe to use for the immediate email-read
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
    # the `.eml` inspection focused on the email contents instead of being
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


def inspect_dropbox_eml_path(
    *,
    access_token: str,
    path: str,
    extract_attachments_dir: Path | None = None,
) -> dict[str, Any]:
    """
    Download one Dropbox `.eml` file and parse its useful email structure.

    Parameters
    ----------
    access_token : str
        Ready-to-use Dropbox access token.

    path : str
        Full Dropbox `.eml` file path to inspect.

    extract_attachments_dir : Path | None
        Optional local directory where embedded email attachments should be
        written.

    Returns
    -------
    dict[str, Any]
        Small structured result describing whether the file could be downloaded
        and parsed successfully, plus the parsed email summary when successful.

    Example
    -------
    A successful result looks like:

        {
            "status": "ok",
            "path": "/archive/example tw398.eml",
            "file_name": "example tw398.eml",
            "subject": "Totaljobs - Suitable application for KDB Developer tw398",
            "attachment_names": ["candidate_cv.pdf"],
            "tw_codes_found": ["tw398"],
            "plain_text_preview": "Please find attached...",
        }
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
        email_message = BytesParser(policy=policy.default).parsebytes(
            downloaded_file["content_bytes"]
        )
    except Exception as exc:  # pragma: no cover - defensive parsing guard
        return {
            "status": "parse_failed",
            "path": path,
            "file_name": downloaded_file.get("file_name"),
            "content_type": downloaded_file.get("content_type"),
            "byte_count": len(downloaded_file["content_bytes"]),
            "reason": f"Failed to parse .eml content: {exc}",
        }

    parsed_email = extract_email_summary(
        email_message=email_message,
        path=path,
        extract_attachments_dir=extract_attachments_dir,
    )

    # Keep the final result deliberately flat.
    #
    # The script is mainly an operator proof tool, so the useful shape is:
    # - transport/download metadata
    # - one parsed email summary
    # - no extra nested wrapper that callers then have to unwrap again
    return {
        "status": "ok",
        "path": path,
        "file_name": downloaded_file.get("file_name"),
        "content_type": downloaded_file.get("content_type"),
        "byte_count": len(downloaded_file["content_bytes"]),
        **parsed_email,
    }


def extract_email_summary(
    *,
    email_message: EmailMessage,
    path: str,
    extract_attachments_dir: Path | None = None,
) -> dict[str, Any]:
    """
    Extract the small set of email fields that matter for advert-response work.

    Parameters
    ----------
    email_message : EmailMessage
        Parsed email object built from the `.eml` bytes.

    path : str
        Source Dropbox path. This is included because folder/file names often
        contain vacancy codes even when the body does not.

    extract_attachments_dir : Path | None
        Optional local directory where embedded attachments should be written.

    Returns
    -------
    dict[str, Any]
        Parsed summary covering headers, body previews, attachment list, and
        detected `tw...` vacancy codes.

    Example
    -------
    The returned structure includes fields such as:

        {
            "subject": "...",
            "from_addresses": [{"name": "Totaljobs.com", "email": "totaljobs@..."}],
            "attachment_names": ["candidate_cv.pdf"],
            "tw_codes_found": ["tw398"],
        }
    """

    subject = email_message.get("Subject")
    raw_date = email_message.get("Date")
    raw_from = email_message.get_all("From", [])
    raw_to = email_message.get_all("To", [])
    raw_cc = email_message.get_all("Cc", [])

    from_addresses = format_address_list(raw_from)
    to_addresses = format_address_list(raw_to)
    cc_addresses = format_address_list(raw_cc)

    plain_text_body, html_body = extract_email_bodies(email_message=email_message)
    attachment_summaries = extract_attachment_summaries(
        email_message=email_message,
        extract_attachments_dir=extract_attachments_dir,
    )

    # Vacancy codes can appear in multiple layers:
    # - the Dropbox file path itself
    # - the email subject
    # - the human-written email body
    #
    # Folding them together here gives one simple answer to the real operator
    # question: "which tw-code, if any, does this email appear to belong to?"
    tw_code_sources: list[str] = [path]
    if isinstance(subject, str):
        tw_code_sources.append(subject)
    if plain_text_body is not None:
        tw_code_sources.append(plain_text_body)

    tw_codes_found = sorted(
        {
            match.group(0).lower()
            for source_text in tw_code_sources
            for match in TW_CODE_PATTERN.finditer(source_text)
        }
    )

    plain_text_preview = (
        normalize_preview_text(plain_text_body)
        if plain_text_body is not None
        else None
    )

    return {
        "subject": subject,
        "date": raw_date,
        "from_addresses": from_addresses,
        "to_addresses": to_addresses,
        "cc_addresses": cc_addresses,
        "attachment_count": len(attachment_summaries),
        "attachment_names": [
            summary["file_name"]
            for summary in attachment_summaries
            if isinstance(summary.get("file_name"), str)
        ],
        "attachments": attachment_summaries,
        "plain_text_character_count": (
            len(plain_text_body) if plain_text_body is not None else None
        ),
        "html_character_count": len(html_body) if html_body is not None else None,
        "plain_text_preview": plain_text_preview,
        "tw_codes_found": tw_codes_found,
    }


def extract_email_bodies(*, email_message: EmailMessage) -> tuple[str | None, str | None]:
    """
    Extract the best plain-text and HTML bodies from a parsed email.

    Parameters
    ----------
    email_message : EmailMessage
        Parsed email object built from the `.eml` bytes.

    Returns
    -------
    tuple[str | None, str | None]
        Best-effort `(plain_text_body, html_body)` pair.

    Example
    -------
    Multipart advert-response emails commonly return:

    - a short plain-text body
    - a longer HTML body

    If only one body type exists, the other tuple slot is returned as `None`.
    """

    plain_text_body: str | None = None
    html_body: str | None = None

    # Walk every MIME part and keep the first useful body for each type.
    #
    # We skip attachments here because advert-response emails often contain
    # CVs or inline files with their own MIME types, and we only want the
    # message body itself in this helper.
    for part in email_message.walk():
        if part.is_multipart():
            continue
        if part.get_content_disposition() == "attachment":
            continue

        content_type = part.get_content_type()

        try:
            payload_text = part.get_content()
        except Exception:  # pragma: no cover - defensive decode guard
            continue

        if not isinstance(payload_text, str):
            continue

        if content_type == "text/plain" and plain_text_body is None:
            plain_text_body = payload_text
        elif content_type == "text/html" and html_body is None:
            html_body = payload_text

    return plain_text_body, html_body


def extract_attachment_summaries(
    *,
    email_message: EmailMessage,
    extract_attachments_dir: Path | None = None,
) -> list[dict[str, Any]]:
    """
    Build a compact attachment summary list from a parsed email.

    Parameters
    ----------
    email_message : EmailMessage
        Parsed email object built from the `.eml` bytes.

    extract_attachments_dir : Path | None
        Optional local directory where extracted attachments should be written.

    Returns
    -------
    list[dict[str, Any]]
        One dictionary per attachment, including name, content type, and size.

    Example
    -------
    A CV attachment entry looks like:

        {
            "file_name": "candidate_cv.docx",
            "content_type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "byte_count": 123456
        }

    Notes
    -----
    - The default mode is metadata-only.
    - Attachment extraction is opt-in because most inspection runs only need
      names, types, and hashes, not local file copies.
    """

    summaries: list[dict[str, Any]] = []

    if extract_attachments_dir is not None:
        extract_attachments_dir.mkdir(parents=True, exist_ok=True)

    for attachment_part in email_message.iter_attachments():
        file_name = attachment_part.get_filename()
        content_type = attachment_part.get_content_type()

        try:
            payload_bytes = attachment_part.get_payload(decode=True)
        except Exception:  # pragma: no cover - defensive decode guard
            payload_bytes = None

        byte_count = len(payload_bytes) if isinstance(payload_bytes, bytes) else None
        sha256 = (
            hashlib.sha256(payload_bytes).hexdigest()
            if isinstance(payload_bytes, bytes)
            else None
        )

        extracted_file_path: str | None = None

        # Keep extraction opt-in and explicit.
        #
        # The normal provenance pass only needs metadata, but when we want to
        # inspect or compare the embedded file itself, writing it to a chosen
        # temp folder is the simplest repeatable path.
        if (
            extract_attachments_dir is not None
            and isinstance(payload_bytes, bytes)
            and isinstance(file_name, str)
            and file_name.strip() != ""
        ):
            target_path = extract_attachments_dir / file_name
            target_path.write_bytes(payload_bytes)
            extracted_file_path = str(target_path)

        summaries.append(
            {
                "file_name": file_name,
                "content_type": content_type,
                "byte_count": byte_count,
                "sha256": sha256,
                "content_disposition": attachment_part.get_content_disposition(),
                "extracted_file_path": extracted_file_path,
            }
        )

    return summaries


def format_address_list(raw_headers: list[str]) -> list[dict[str, str | None]]:
    """
    Normalize email header address lists into dictionaries.

    Parameters
    ----------
    raw_headers : list[str]
        Raw header values such as `From`, `To`, or `Cc`.

    Returns
    -------
    list[dict[str, str | None]]
        Parsed address dictionaries with `name` and `email`.

    Example
    -------
    A parsed address entry looks like:

        {"name": "Tom Owens", "email": "tom@example.com"}
    """

    formatted_addresses: list[dict[str, str | None]] = []

    for display_name, email_address in getaddresses(raw_headers):
        formatted_addresses.append(
            {
                "name": display_name or None,
                "email": email_address or None,
            }
        )

    return formatted_addresses


def normalize_preview_text(text: str) -> str:
    """
    Collapse body text into a short readable preview.

    Parameters
    ----------
    text : str
        Raw plain-text email body.

    Returns
    -------
    str
        Single-line preview trimmed to a manageable length.

    Notes
    -----
    This intentionally trades fidelity for readability:

    - collapse whitespace so console output stays compact
    - cap the preview length so one large email body does not swamp the report
    """

    normalized = " ".join(text.split())
    return normalized[:500]


def main() -> int:
    """
    Run the Dropbox `.eml` inspection proof script.

    Returns
    -------
    int
        Process exit code.

    Example
    -------
    Running:

        uv run python scripts/check_dropbox_eml_parse.py ^
            --dropbox-account-id dbid:AAExample ^
            --path "/archive/example tw398.eml"

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
        inspect_dropbox_eml_path(
            access_token=access_token,
            path=path,
            extract_attachments_dir=args.extract_attachments_dir,
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

    print("Dropbox .eml inspection completed.\n")
    print(f"Dropbox account ID: {args.dropbox_account_id}")
    print(f"Checked files: {len(results)}")

    for result in results:
        print("")
        print(f"Path: {result['path']}")
        print(f"Status: {result['status']}")

        if result["status"] == "ok":
            print(f"Subject: {result['subject']}")
            print(f"Date: {result['date']}")
            print(f"From: {result['from_addresses']}")
            print(f"Attachment count: {result['attachment_count']}")
            print(f"Attachment names: {result['attachment_names']}")
            print(f"TW codes found: {result['tw_codes_found']}")
            print(f"Preview: {result['plain_text_preview']}")
        else:
            print(f"Reason: {result['reason']}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
