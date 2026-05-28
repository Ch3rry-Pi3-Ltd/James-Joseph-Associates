"""
Service helpers for persisting narrow Outlook advert-response resume snapshots.

This module sits above the raw SQL helper in
`backend.db.outlook_resume_persistence` and below the operator-facing scripts.

It gives the rest of the repository a stable way to talk about:

- validating that one Outlook message snapshot is usable for persistence
- validating that one Outlook file attachment plus extracted text is usable
- normalizing those source payloads into one persistence snapshot
- hashing provenance payloads before they are written to `source_records`
- keeping business-level persistence rules out of CLI scripts

Why this module exists
----------------------
The Outlook integration has already proved the hard prerequisites:

- OAuth works
- the advert-response folder path is readable
- real file attachments can be downloaded
- the existing text extraction path works against those attachment bytes

That changes the next question:

    "Can we turn one real Outlook advert-response message and one real CV
    attachment into a repeatable canonical write without making the script own
    the write rules?"

This module is the answer to that narrow question.

Current policy
--------------
The first Outlook persistence path is intentionally conservative:

- one message plus one attachment per call
- canonical candidate/person reconciliation is deferred
- the file becomes a canonical `resume` document
- the message and attachment remain provenance-bearing source records
- a job link is only attempted when the `tw...` vacancy code is clear enough
- non-pass CVs are still persisted, but their quality status and score stay
  attached to the provenance so downstream flows can filter them out
"""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import re
from typing import Any

from backend.db.outlook_resume_persistence import persist_outlook_resume_snapshot


def persist_outlook_message_attachment_resume(
    *,
    microsoft_user_id: str,
    mailbox: str | None,
    folder_path: list[str],
    folder_id: str,
    message: dict[str, Any],
    attachment_download: dict[str, Any],
    extracted_resume_text: dict[str, Any],
    quality_assessment: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Persist one Outlook advert-response message attachment into the canonical schema.

    Parameters
    ----------
    microsoft_user_id : str
        Connected Microsoft user identifier used as part of the source keys.

    mailbox : str | None
        Optional delegated mailbox identifier used for the read.

    folder_path : list[str]
        Human-readable folder path used for provenance and operator review.

    folder_id : str
        Outlook folder identifier that contained the message.

    message : dict[str, Any]
        Outlook message object returned by the message-list helper.

    attachment_download : dict[str, Any]
        Normalized attachment download payload returned by the Outlook API
        helper.

    extracted_resume_text : dict[str, Any]
        Resume text bundle returned by `extract_text_from_resume_bytes(...)`.

    quality_assessment : dict[str, Any] | None, optional
        Structured quality decision returned by the canonical LLM-backed resume
        extraction path. When present, the persistence layer stores the
        quality status and score alongside the Outlook provenance instead of
        dropping non-pass CVs on the floor.

    Returns
    -------
    dict[str, Any]
        Persistence summary returned by the lower-level database helper.

    Example
    -------
    A caller can take one already-downloaded Outlook attachment plus its
    extracted text bundle and persist it directly:

        persisted = persist_outlook_message_attachment_resume(
            microsoft_user_id="aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
            mailbox=None,
            folder_path=["# ADV-CVR", "### DOMINIQUE FOLDER", "tw394"],
            folder_id="AAMkAGI2...",
            message=message,
            attachment_download=attachment_download,
            extracted_resume_text=extracted_resume_text,
        )
        print(persisted["document_id"])

    That keeps the caller logic simple: download attachment, extract text,
    then hand both snapshots to this helper for one canonical write.
    """

    persistence_payload = build_outlook_resume_persistence_payload(
        microsoft_user_id=microsoft_user_id,
        mailbox=mailbox,
        folder_path=folder_path,
        folder_id=folder_id,
        message=message,
        attachment_download=attachment_download,
        extracted_resume_text=extracted_resume_text,
        quality_assessment=quality_assessment,
    )
    return persist_outlook_resume_snapshot(persistence_payload)


def build_outlook_resume_persistence_payload(
    *,
    microsoft_user_id: str,
    mailbox: str | None,
    folder_path: list[str],
    folder_id: str,
    message: dict[str, Any],
    attachment_download: dict[str, Any],
    extracted_resume_text: dict[str, Any],
    quality_assessment: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Build the narrow persistence payload for one Outlook message attachment.

    Parameters
    ----------
    microsoft_user_id : str
        Connected Microsoft user identifier used as part of the source keys.

    mailbox : str | None
        Optional delegated mailbox identifier used for the read.

    folder_path : list[str]
        Human-readable folder path used for provenance and operator review.

    folder_id : str
        Outlook folder identifier that contained the message.

    message : dict[str, Any]
        Outlook message object returned by the message-list helper.

    attachment_download : dict[str, Any]
        Normalized attachment download payload returned by the Outlook API
        helper.

    extracted_resume_text : dict[str, Any]
        Resume text bundle returned by `extract_text_from_resume_bytes(...)`.

    quality_assessment : dict[str, Any] | None, optional
        Structured quality decision returned by the canonical LLM-backed resume
        extraction path.

    Returns
    -------
    dict[str, Any]
        Normalized payload ready for the direct SQL persistence helper.

    Notes
    -----
    The persistence payload intentionally preserves more provenance than the
    canonical tables can represent directly today.

    In particular, the source-record payloads keep:

    - the Outlook folder context
    - the mailbox message metadata
    - the attachment metadata and byte metrics
    - the extracted resume-text metrics
    - the inferred `tw...` vacancy code

    Example
    -------
    The returned payload contains provenance slices such as:

        payload["message_source_payload"]
        payload["attachment_source_payload"]

    and stable source identifiers such as:

        payload["message_source_record_id"]
        payload["attachment_source_record_id"]
    """

    _validate_outlook_resume_inputs(
        microsoft_user_id=microsoft_user_id,
        folder_path=folder_path,
        folder_id=folder_id,
        message=message,
        attachment_download=attachment_download,
        extracted_resume_text=extracted_resume_text,
    )

    message_id = _require_nonempty_string(message.get("id"), field_name="message.id")
    attachment_id = _require_nonempty_string(
        attachment_download.get("attachment_id"),
        field_name="attachment_download.attachment_id",
    )
    file_name = _require_nonempty_string(
        attachment_download.get("file_name"),
        field_name="attachment_download.file_name",
    )
    cleaned_resume_text = _require_nonempty_string(
        extracted_resume_text.get("cleaned_text") or extracted_resume_text.get("text"),
        field_name="extracted_resume_text.cleaned_text",
    )
    folder_segments = [
        _require_nonempty_string(item, field_name="folder_path item")
        for item in folder_path
    ]
    folder_path_text = " > ".join(folder_segments)
    message_subject = _clean_optional_string(message.get("subject"))
    sender_name, sender_email = _extract_sender_identity(message)
    received_at = _clean_optional_string(message.get("receivedDateTime"))
    internet_message_id = _clean_optional_string(message.get("internetMessageId"))
    conversation_id = _clean_optional_string(message.get("conversationId"))

    # Normalize the mailbox key once so the provenance identifiers stay stable
    # across reruns. A blank delegated-mailbox value and the signed-in-user
    # path should both collapse to the same explicit `me` marker.
    source_mailbox_key = (mailbox or "me").strip() if mailbox else "me"
    message_source_key = _build_outlook_message_source_key(
        microsoft_user_id=microsoft_user_id,
        mailbox=source_mailbox_key,
        message_id=message_id,
    )
    attachment_source_key = _build_outlook_attachment_source_key(
        message_source_key=message_source_key,
        attachment_id=attachment_id,
    )

    tw_code = _extract_tw_code(
        [
            folder_path_text,
            message_subject,
            file_name,
        ]
    )
    quality_status = _clean_optional_string(
        (quality_assessment or {}).get("status")
    ) or "unscored"
    quality_score = (quality_assessment or {}).get("quality_score")

    resume_source_uri = _build_outlook_attachment_source_uri(
        microsoft_user_id=microsoft_user_id,
        mailbox=source_mailbox_key,
        message_id=message_id,
        attachment_id=attachment_id,
    )
    resume_content_hash = _hash_text(cleaned_resume_text)

    message_source_payload = {
        "microsoft_user_id": microsoft_user_id,
        "mailbox": mailbox,
        "folder_id": folder_id,
        "folder_path": folder_segments,
        "folder_path_text": folder_path_text,
        "message": {
            "id": message_id,
            "subject": message_subject,
            "receivedDateTime": received_at,
            "internetMessageId": internet_message_id,
            "conversationId": conversation_id,
            "hasAttachments": message.get("hasAttachments"),
            "fromName": sender_name,
            "fromEmail": sender_email,
        },
        "tw_code": tw_code,
        "quality_assessment": quality_assessment,
    }
    attachment_source_payload = {
        "microsoft_user_id": microsoft_user_id,
        "mailbox": mailbox,
        "folder_id": folder_id,
        "message_id": message_id,
        "attachment_id": attachment_id,
        "file_name": file_name,
        "content_type": _clean_optional_string(
            attachment_download.get("content_type")
        ),
        "byte_count": len(attachment_download.get("content_bytes", b"")),
        "attachment_metadata": attachment_download.get("attachment_metadata"),
        "extractor": extracted_resume_text.get("extractor"),
        "character_count": extracted_resume_text.get("character_count"),
        "page_count": extracted_resume_text.get("page_count"),
        "resume_content_hash": resume_content_hash,
        "tw_code": tw_code,
        "quality_assessment": quality_assessment,
    }

    return {
        "source_system": "outlook_resume",
        "microsoft_user_id": microsoft_user_id,
        "mailbox": mailbox,
        "import_run_id": _build_import_run_id(
            microsoft_user_id=microsoft_user_id,
            folder_path_text=folder_path_text,
        ),
        "tw_code": tw_code,
        "quality_status": quality_status,
        "quality_score": quality_score,
        "message_source_record_id": message_source_key,
        "attachment_source_record_id": attachment_source_key,
        "resume_title": file_name,
        "resume_mime_type": _clean_optional_string(
            attachment_download.get("content_type")
        ),
        "resume_source_uri": resume_source_uri,
        "resume_content_hash": resume_content_hash,
        "cleaned_resume_text": cleaned_resume_text,
        "message_source_payload": message_source_payload,
        "message_source_payload_hash": _hash_json_ready_payload(
            message_source_payload
        ),
        "attachment_source_payload": attachment_source_payload,
        "attachment_source_payload_hash": _hash_json_ready_payload(
            attachment_source_payload
        ),
    }


def _validate_outlook_resume_inputs(
    *,
    microsoft_user_id: str,
    folder_path: list[str],
    folder_id: str,
    message: dict[str, Any],
    attachment_download: dict[str, Any],
    extracted_resume_text: dict[str, Any],
) -> None:
    """
    Validate that one Outlook message attachment snapshot is safe to persist.

    Example
    -------
    A payload missing `message.id`, `attachment_download.file_name`, or usable
    extracted text is rejected here before any database write is attempted.

    In other words, this helper is the guardrail that stops a half-formed
    Graph snapshot from reaching the SQL layer.
    """

    _require_nonempty_string(
        microsoft_user_id,
        field_name="microsoft_user_id",
    )
    _require_nonempty_string(folder_id, field_name="folder_id")

    if not isinstance(folder_path, list) or len(folder_path) == 0:
        raise RuntimeError("folder_path must contain at least one folder segment.")

    if not isinstance(message, dict):
        raise RuntimeError("message must be an object.")

    if not isinstance(attachment_download, dict):
        raise RuntimeError("attachment_download must be an object.")

    if not isinstance(extracted_resume_text, dict):
        raise RuntimeError("extracted_resume_text must be an object.")

    _require_nonempty_string(message.get("id"), field_name="message.id")
    _require_nonempty_string(
        attachment_download.get("attachment_id"),
        field_name="attachment_download.attachment_id",
    )
    _require_nonempty_string(
        attachment_download.get("file_name"),
        field_name="attachment_download.file_name",
    )
    _require_nonempty_string(
        extracted_resume_text.get("cleaned_text") or extracted_resume_text.get("text"),
        field_name="extracted_resume_text.cleaned_text",
    )


def _build_outlook_message_source_key(
    *,
    microsoft_user_id: str,
    mailbox: str,
    message_id: str,
) -> str:
    """
    Build a stable source-record key for one Outlook message snapshot.

    Example
    -------
    A call with:

        microsoft_user_id="aaaa"
        mailbox="me"
        message_id="AAMkAGI2..."

    returns a source key that is stable across reruns of the same mailbox
    ingestion slice.
    """

    return f"{microsoft_user_id}:{mailbox}:{message_id}"


def _build_outlook_attachment_source_key(
    *,
    message_source_key: str,
    attachment_id: str,
) -> str:
    """
    Build a stable source-record key for one Outlook attachment snapshot.

    Example
    -------
    A call with one message source key and one attachment ID returns a stable
    combined key such as:

        aaaa:me:AAMkAGI2...:AAMkAGI2...AAABEgAQ...
    """

    return f"{message_source_key}:{attachment_id}"


def _build_outlook_attachment_source_uri(
    *,
    microsoft_user_id: str,
    mailbox: str,
    message_id: str,
    attachment_id: str,
) -> str:
    """
    Build a stable backend-local URI for one Outlook attachment source.

    Example
    -------
    A call with:

        microsoft_user_id="aaaa"
        mailbox="me"
        message_id="AAMkAGI2..."
        attachment_id="AAMkAGI2...AAABEgAQ..."

    returns:

        outlook://users/aaaa/mailboxes/me/messages/AAMkAGI2.../attachments/AAMkAGI2...AAABEgAQ...
    """

    return (
        f"outlook://users/{microsoft_user_id}/mailboxes/{mailbox}/messages/"
        f"{message_id}/attachments/{attachment_id}"
    )


def _extract_sender_identity(message: dict[str, Any]) -> tuple[str | None, str | None]:
    """
    Return the sender display name and email from one Outlook message payload.

    Example
    -------
    A message with:

        {"from": {"emailAddress": {"name": "Totaljobs", "address": "x@y"}}}

    returns:

        ("Totaljobs", "x@y")
    """

    raw_from = message.get("from")
    if not isinstance(raw_from, dict):
        return None, None

    raw_email_address = raw_from.get("emailAddress")
    if not isinstance(raw_email_address, dict):
        return None, None

    return (
        _clean_optional_string(raw_email_address.get("name")),
        _clean_optional_string(raw_email_address.get("address")),
    )


def _extract_tw_code(text_values: list[str | None]) -> str | None:
    """
    Extract the first `tw...` vacancy code from a small set of candidate strings.

    Example
    -------
    Given values such as:

        ["# ADV-CVR > ### DOMINIQUE FOLDER > tw394", "Suitable application for ... tw394"]

    this helper returns:

        "tw394"
    """

    for value in text_values:
        cleaned_value = _clean_optional_string(value)
        if cleaned_value is None:
            continue

        match = re.search(r"\btw\d+\b", cleaned_value, flags=re.IGNORECASE)
        if match is not None:
            return match.group(0).lower()

    return None


def _build_import_run_id(
    *,
    microsoft_user_id: str,
    folder_path_text: str,
) -> str:
    """
    Build a stable import-run identifier for Outlook resume persistence.

    Example
    -------
    A `tw394` run might yield:

        outlook_resume:b4dd...:# ADV-CVR > ### DOMINIQUE FOLDER > tw394:2026-05-21T18:00:00+00:00
    """

    timestamp = datetime.now(timezone.utc).isoformat()
    return f"outlook_resume:{microsoft_user_id}:{folder_path_text}:{timestamp}"


def _require_nonempty_string(value: Any, *, field_name: str) -> str:
    """
    Return a stripped non-empty string or raise clearly.

    Example
    -------
    Passing:

        value=" tw394 "

    returns:

        "tw394"
    """

    cleaned_value = _clean_optional_string(value)
    if cleaned_value is None:
        raise RuntimeError(f"{field_name} must be a non-empty string.")
    return cleaned_value


def _clean_optional_string(value: Any) -> str | None:
    """
    Return a stripped string or `None` when the input is blank-like.

    Example
    -------
    Inputs such as:

        "  Totaljobs  "
        ""
        None

    become:

        "Totaljobs"
        None
        None
    """

    if not isinstance(value, str):
        return None

    cleaned_value = value.strip()
    if cleaned_value == "":
        return None
    return cleaned_value


def _hash_text(text: str) -> str:
    """
    Hash source text for document/provenance deduplication.

    Example
    -------
    Two identical cleaned resume-text strings produce the same SHA-256 hash,
    which lets the persistence layer spot obvious duplicate resume content.
    """

    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _hash_json_ready_payload(payload: dict[str, Any]) -> str:
    """
    Hash one provenance payload after a stable JSON-style normalization step.

    Example
    -------
    Two payloads with the same keys and values but different dictionary order
    still produce the same hash because the JSON serialization is sorted.
    """

    return hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()


__all__ = [
    "build_outlook_resume_persistence_payload",
    "persist_outlook_message_attachment_resume",
]
