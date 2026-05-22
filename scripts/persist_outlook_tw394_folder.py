"""
Persist the first narrow Outlook advert-response folder slice into Supabase.

Why this script exists
----------------------
The Outlook integration has already proved all of the prerequisite transport
steps:

- Tom's Outlook OAuth connection is stored correctly
- the advert-response folder path can be resolved through Graph
- real `tw394` messages exist and carry vacancy context in the subject line
- real file attachments can be downloaded and parsed locally

The next concrete question is narrower:

    "Can we move from one-off proof reads into a bounded repeatable mailbox
    ingestion slice for `# ADV-CVR > ### DOMINIQUE FOLDER > tw394`?"

This script answers that question.

What this script does
---------------------
For one supplied Outlook folder path, it:

1. loads the stored Outlook OAuth connection
2. refreshes the access token if needed
3. resolves the folder path level by level through Graph
4. fetches a bounded message page from that folder
5. fetches attachment metadata for messages that expose attachments
6. downloads supported file attachments transiently into memory
7. extracts resume text locally
8. persists one canonical `resume` document plus Outlook provenance records
9. optionally writes a JSON report

What this script does not do
----------------------------
It does not:

- reconcile the email directly to a canonical candidate yet
- persist `.eml` bodies as first-class documents yet
- create embeddings or document chunks
- infer skills or candidate fit

Examples
--------
Run the first narrow `tw394` mailbox-ingestion slice:

    uv run python scripts/persist_outlook_tw394_folder.py ^
        --microsoft-user-id "b4dd6a5f-8e27-4745-9369-e117121382ed" ^
        --output-json temp\\outlook_tw394_ingest.json

Target a delegated mailbox explicitly:

    uv run python scripts/persist_outlook_tw394_folder.py ^
        --microsoft-user-id "b4dd6a5f-8e27-4745-9369-e117121382ed" ^
        --mailbox "recruitment@example.com"
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

from backend.db.outlook_oauth import get_outlook_oauth_connection, save_outlook_oauth_connection
from backend.services.outlook_api import (
    OutlookApiError,
    download_outlook_message_file_attachment,
    fetch_outlook_child_mail_folders,
    fetch_outlook_mail_folders,
    fetch_outlook_message_attachments,
    fetch_outlook_messages,
)
from backend.services.outlook_oauth import (
    OutlookTokenSet,
    is_outlook_access_token_expired,
    refresh_outlook_access_token,
)
from backend.services.outlook_resume_persistence import (
    build_outlook_resume_persistence_payload,
    persist_outlook_message_attachment_resume,
)
from backend.services.resume_text import (
    ResumeTextExtractionError,
    extract_text_from_resume_bytes,
)
from backend.services.text_cleaning import clean_resume_text
DEFAULT_MICROSOFT_USER_ID = "b4dd6a5f-8e27-4745-9369-e117121382ed"
DEFAULT_FOLDER_PATH = ["Inbox", "# ADV-CVR", "### DOMINIQUE FOLDER", "tw394"]
DEFAULT_MESSAGE_LIMIT = 10
DEFAULT_ATTACHMENT_LIMIT = 10


def build_argument_parser() -> argparse.ArgumentParser:
    """
    Build the CLI argument parser for the first Outlook folder-ingest slice.

    Example
    -------
    A typical operator invocation looks like:

        --microsoft-user-id aaaa-bbbb --output-json temp\\report.json
    """

    parser = argparse.ArgumentParser(
        description=(
            "Persist a bounded Outlook advert-response folder slice into the "
            "canonical Supabase schema."
        )
    )
    parser.add_argument(
        "--microsoft-user-id",
        default=DEFAULT_MICROSOFT_USER_ID,
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
        "--folder-segment",
        action="append",
        default=None,
        help=(
            "One human-readable folder path segment. Pass this once per level. "
            "If omitted, the script uses the default tw394 path."
        ),
    )
    parser.add_argument(
        "--message-limit",
        type=int,
        default=DEFAULT_MESSAGE_LIMIT,
        help="Maximum number of messages to read from the target folder.",
    )
    parser.add_argument(
        "--attachment-limit",
        type=int,
        default=DEFAULT_ATTACHMENT_LIMIT,
        help="Maximum number of successful attachment ingests to persist in one run.",
    )
    parser.add_argument(
        "--output-json",
        type=Path,
        default=None,
        help="Optional JSON output path for the final ingestion report.",
    )
    return parser


def validate_arguments(args: argparse.Namespace) -> list[str]:
    """
    Validate the high-signal local arguments before any Graph read starts.

    Returns
    -------
    list[str]
        Final normalized folder path to resolve.

    Example
    -------
    This helper rejects clearly invalid states such as:

    - a blank Microsoft user ID
    - a zero message limit
    - an empty folder path
    """

    if (
        not isinstance(args.microsoft_user_id, str)
        or args.microsoft_user_id.strip() == ""
    ):
        raise RuntimeError("MICROSOFT_USER_ID must be a non-empty string.")

    if args.message_limit < 1:
        raise RuntimeError("MESSAGE_LIMIT must be at least 1.")

    if args.attachment_limit < 1:
        raise RuntimeError("ATTACHMENT_LIMIT must be at least 1.")

    raw_folder_segments = (
        args.folder_segment
        if isinstance(args.folder_segment, list) and args.folder_segment
        else DEFAULT_FOLDER_PATH
    )
    folder_segments = [
        segment.strip()
        for segment in raw_folder_segments
        if isinstance(segment, str) and segment.strip() != ""
    ]
    if not folder_segments:
        raise RuntimeError("At least one non-empty folder segment is required.")

    return folder_segments


def load_ready_outlook_connection(*, microsoft_user_id: str) -> dict[str, Any]:
    """
    Load the stored Outlook connection and refresh it if it is already expired.

    Example
    -------
    Calling:

        load_ready_outlook_connection(
            microsoft_user_id="aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
        )

    returns a connection row that is safe to use for the immediate mailbox
    reads.
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

    if is_outlook_access_token_expired(
        obtained_at=raw_obtained_at,
        expires_in_seconds=raw_expires_in_seconds,
    ):
        if not isinstance(raw_refresh_token, str) or raw_refresh_token.strip() == "":
            raise RuntimeError(
                "The stored Outlook connection is missing a refresh token."
            )

        try:
            refreshed_token_set = refresh_outlook_access_token(
                refresh_token=raw_refresh_token,
            )
        except (RuntimeError, ValueError) as exc:
            raise RuntimeError(
                "Outlook token refresh could not run because the required local "
                "Microsoft OAuth settings are missing."
            ) from exc

        # Microsoft refresh responses are not guaranteed to repeat the stable
        # identity fields already captured during the original callback.
        # Preserve those fields here so the refreshed connection remains
        # writable and usable for later mailbox reads.
        merged_raw_payload = dict(refreshed_token_set.raw_payload)
        merged_raw_payload.setdefault("refresh_token", raw_refresh_token)
        merged_raw_payload.setdefault("oid", stored_connection.get("microsoft_user_id"))
        merged_raw_payload.setdefault("tid", stored_connection.get("tenant_id"))
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
            tenant_id=refreshed_token_set.tenant_id or stored_connection.get("tenant_id"),
            user_principal_name=(
                refreshed_token_set.user_principal_name
                or stored_connection.get("user_principal_name")
            ),
            raw_payload=merged_raw_payload,
        )

        stored_connection = save_outlook_oauth_connection(refreshed_token_set)

    return stored_connection


def resolve_outlook_folder_path(
    *,
    access_token: str,
    mailbox: str | None,
    folder_segments: list[str],
) -> dict[str, Any]:
    """
    Resolve one human-readable Outlook folder path through Graph.

    Returns
    -------
    dict[str, Any]
        Resolved folder metadata for the final path segment.

    Example
    -------
    Resolving:

        ["Inbox", "# ADV-CVR", "### DOMINIQUE FOLDER", "tw394"]

    walks the mailbox level by level and returns the final `tw394` folder
    object plus the resolved path.
    """

    current_level = fetch_outlook_mail_folders(
        access_token=access_token,
        mailbox=mailbox,
        limit=200,
    )
    resolved_folders: list[dict[str, Any]] = []

    for segment_index, segment in enumerate(folder_segments):
        matched_folder = _match_folder_by_display_name(
            folders=current_level.get("folders", []),
            target_name=segment,
        )
        if matched_folder is None:
            raise RuntimeError(
                "Could not resolve Outlook folder segment "
                f"{segment!r} at position {segment_index + 1}."
            )

        resolved_folders.append(matched_folder)

        if segment_index == len(folder_segments) - 1:
            break

        parent_folder_id = matched_folder.get("id")
        if not isinstance(parent_folder_id, str) or parent_folder_id.strip() == "":
            raise RuntimeError(
                f"Resolved folder {segment!r} did not include a usable folder ID."
            )

        current_level = fetch_outlook_child_mail_folders(
            access_token=access_token,
            parent_folder_id=parent_folder_id,
            mailbox=mailbox,
            limit=200,
        )

    final_folder = resolved_folders[-1]
    return {
        "folder_id": final_folder["id"],
        "folder": final_folder,
        "resolved_path": folder_segments,
        "resolved_folders": resolved_folders,
    }


def run_outlook_folder_ingest(
    *,
    access_token: str,
    microsoft_user_id: str,
    mailbox: str | None,
    folder_path: list[str],
    folder_id: str,
    message_limit: int,
    attachment_limit: int,
) -> dict[str, Any]:
    """
    Run the bounded Outlook folder-ingest slice for one resolved folder.

    Returns
    -------
    dict[str, Any]
        Operator-facing report containing ingested items, skips, and failures.

    Example
    -------
    A bounded run with:

        message_limit=10
        attachment_limit=1

    reads at most ten messages from the resolved Outlook folder and stops
    after the first successfully persisted supported attachment.
    """

    messages_result = fetch_outlook_messages(
        access_token=access_token,
        folder_id=folder_id,
        mailbox=mailbox,
        limit=message_limit,
    )
    messages = messages_result.get("messages", [])

    ingested_items: list[dict[str, Any]] = []
    skipped_items: list[dict[str, Any]] = []
    failed_items: list[dict[str, Any]] = []

    # Walk messages one by one so every persisted document can be traced back
    # to one concrete mailbox item and one concrete attachment.
    for message in messages:
        if len(ingested_items) >= attachment_limit:
            break

        message_id = message.get("id")
        if not isinstance(message_id, str) or message_id.strip() == "":
            skipped_items.append(
                {
                    "reason": "missing_message_id",
                    "message_subject": message.get("subject"),
                }
            )
            continue

        if not message.get("hasAttachments"):
            skipped_items.append(
                {
                    "reason": "message_has_no_attachments",
                    "message_id": message_id,
                    "message_subject": message.get("subject"),
                }
            )
            continue

        try:
            attachment_list_result = fetch_outlook_message_attachments(
                access_token=access_token,
                message_id=message_id,
                mailbox=mailbox,
                limit=50,
            )
        except OutlookApiError as exc:
            failed_items.append(
                {
                    "stage": "attachment_list_read",
                    "message_id": message_id,
                    "message_subject": message.get("subject"),
                    "error_type": exc.__class__.__name__,
                    "message": str(exc),
                }
            )
            continue

        # Work attachment by attachment inside the message so the report can
        # say exactly which file was skipped, failed, or became the canonical
        # resume document.
        for attachment in attachment_list_result.get("attachments", []):
            if len(ingested_items) >= attachment_limit:
                break

            attachment_id = attachment.get("id")
            file_name = attachment.get("name")
            content_type = attachment.get("contentType")
            odata_type = attachment.get("@odata.type")

            if (
                not isinstance(attachment_id, str)
                or attachment_id.strip() == ""
            ):
                skipped_items.append(
                    {
                        "reason": "missing_attachment_id",
                        "message_id": message_id,
                        "message_subject": message.get("subject"),
                        "file_name": file_name,
                    }
                )
                continue

            if odata_type != "#microsoft.graph.fileAttachment":
                skipped_items.append(
                    {
                        "reason": "unsupported_attachment_type",
                        "message_id": message_id,
                        "attachment_id": attachment_id,
                        "message_subject": message.get("subject"),
                        "file_name": file_name,
                        "odata_type": odata_type,
                    }
                )
                continue

            try:
                attachment_download = download_outlook_message_file_attachment(
                    access_token=access_token,
                    message_id=message_id,
                    attachment_id=attachment_id,
                    mailbox=mailbox,
                )
                extracted_resume_text = extract_text_from_resume_bytes(
                    content_bytes=attachment_download["content_bytes"],
                    file_name=attachment_download.get("file_name"),
                    content_type=attachment_download.get("content_type"),
                )
                extracted_resume_text["cleaned_text"] = clean_resume_text(
                    extracted_resume_text["text"]
                )
                # Build the payload once here so the operator report can expose
                # the inferred `tw...` code even though the lower-level
                # persistence helper only returns canonical IDs.
                persistence_payload = build_outlook_resume_persistence_payload(
                    microsoft_user_id=microsoft_user_id,
                    mailbox=mailbox,
                    folder_path=folder_path,
                    folder_id=folder_id,
                    message=message,
                    attachment_download=attachment_download,
                    extracted_resume_text=extracted_resume_text,
                )
                persistence_summary = persist_outlook_message_attachment_resume(
                    microsoft_user_id=microsoft_user_id,
                    mailbox=mailbox,
                    folder_path=folder_path,
                    folder_id=folder_id,
                    message=message,
                    attachment_download=attachment_download,
                    extracted_resume_text=extracted_resume_text,
                )
            except ResumeTextExtractionError as exc:
                skipped_items.append(
                    {
                        "reason": "resume_text_extraction_failed",
                        "message_id": message_id,
                        "attachment_id": attachment_id,
                        "message_subject": message.get("subject"),
                        "file_name": file_name,
                        "content_type": content_type,
                        "error_type": exc.__class__.__name__,
                        "message": str(exc),
                    }
                )
                continue
            except (OutlookApiError, RuntimeError) as exc:
                failed_items.append(
                    {
                        "stage": "attachment_ingest",
                        "message_id": message_id,
                        "attachment_id": attachment_id,
                        "message_subject": message.get("subject"),
                        "file_name": file_name,
                        "error_type": exc.__class__.__name__,
                        "message": str(exc),
                    }
                )
                continue

            ingested_items.append(
                {
                    "message_id": message_id,
                    "attachment_id": attachment_id,
                    "message_subject": message.get("subject"),
                    "file_name": attachment_download.get("file_name"),
                    "content_type": attachment_download.get("content_type"),
                    "byte_count": len(attachment_download["content_bytes"]),
                    "extractor": extracted_resume_text.get("extractor"),
                    "character_count": extracted_resume_text.get("character_count"),
                    "tw_code": persistence_payload.get("tw_code"),
                    "document_id": persistence_summary.get("document_id"),
                    "resolved_job_id": persistence_summary.get("resolved_job_id"),
                    "message_source_record_id": persistence_summary.get(
                        "message_source_record_id"
                    ),
                    "attachment_source_record_id": persistence_summary.get(
                        "attachment_source_record_id"
                    ),
                }
            )

    return {
        "microsoft_user_id": microsoft_user_id,
        "mailbox": mailbox,
        "folder_id": folder_id,
        "folder_path": folder_path,
        "message_limit": message_limit,
        "attachment_limit": attachment_limit,
        "message_count_scanned": len(messages),
        "ingested_count": len(ingested_items),
        "skipped_count": len(skipped_items),
        "failed_count": len(failed_items),
        "ingested_items": ingested_items,
        "skipped_items": skipped_items,
        "failed_items": failed_items,
    }


def _match_folder_by_display_name(
    *,
    folders: list[dict[str, Any]],
    target_name: str,
) -> dict[str, Any] | None:
    """
    Return the first folder whose display name matches one target segment.

    Example
    -------
    A target segment such as:

        "tw394"

    matches a folder whose Graph payload includes:

        {"displayName": "tw394", "id": "..."}
    """

    target_key = target_name.strip().casefold()
    for folder in folders:
        display_name = folder.get("displayName")
        if (
            isinstance(display_name, str)
            and display_name.strip().casefold() == target_key
        ):
            return folder
    return None


def _make_json_safe_value(value: Any) -> Any:
    """
    Convert the operator report into JSON-safe plain Python types.

    Example
    -------
    Nested report dictionaries and lists remain structurally the same while
    any non-JSON-native values are converted into strings where needed.
    """

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
    Run the first narrow Outlook folder-ingest slice.

    Example
    -------
    Running:

        uv run python scripts/persist_outlook_tw394_folder.py ^
            --output-json temp\\outlook_tw394_ingest.json

    resolves the `tw394` folder path, ingests a bounded set of supported
    attachments, and writes a JSON summary report.
    """

    parser = build_argument_parser()
    args = parser.parse_args()

    folder_segments = validate_arguments(args)
    stored_connection = load_ready_outlook_connection(
        microsoft_user_id=args.microsoft_user_id,
    )

    access_token = stored_connection["access_token"]
    assert isinstance(access_token, str)

    resolved_folder = resolve_outlook_folder_path(
        access_token=access_token,
        mailbox=args.mailbox,
        folder_segments=folder_segments,
    )

    ingest_report = run_outlook_folder_ingest(
        access_token=access_token,
        microsoft_user_id=args.microsoft_user_id,
        mailbox=args.mailbox,
        folder_path=folder_segments,
        folder_id=resolved_folder["folder_id"],
        message_limit=args.message_limit,
        attachment_limit=args.attachment_limit,
    )

    final_report = {
        "resolved_folder": resolved_folder,
        "ingest_report": ingest_report,
    }

    if args.output_json is not None:
        args.output_json.parent.mkdir(parents=True, exist_ok=True)
        args.output_json.write_text(
            json.dumps(_make_json_safe_value(final_report), indent=2),
            encoding="utf-8",
        )
        print(f"[info] Wrote JSON report to {args.output_json}")

    print("Outlook folder ingestion completed.\n")
    print(f"microsoft_user_id: {args.microsoft_user_id}")
    print(f"mailbox: {args.mailbox}")
    print(f"folder_path: {' > '.join(folder_segments)}")
    print(f"folder_id: {resolved_folder['folder_id']}")
    print(f"message_count_scanned: {ingest_report['message_count_scanned']}")
    print(f"ingested_count: {ingest_report['ingested_count']}")
    print(f"skipped_count: {ingest_report['skipped_count']}")
    print(f"failed_count: {ingest_report['failed_count']}")

    return 0 if ingest_report["failed_count"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
