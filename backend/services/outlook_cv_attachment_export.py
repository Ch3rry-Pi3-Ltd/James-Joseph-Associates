"""
Heuristic Outlook attachment scanning and CV export helpers.

This module supports one narrow operational question:

    "Can we scan a bounded Outlook mailbox slice, decide locally whether an
    attachment looks like a CV, and export only those CVs to Dropbox?"

The important constraint is that this stage should not depend on an LLM.
Instead it uses:

- existing local document parsers
- text cleaning
- conservative filename/content-type checks
- a heuristic CV-likeness scorer over the extracted text
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any

from backend.services.dropbox_api import upload_dropbox_file
from backend.services.outlook_api import (
    OutlookApiError,
    download_outlook_message_file_attachment,
    fetch_outlook_message_attachments,
    fetch_outlook_messages,
)
from backend.services.resume_text import (
    ResumeTextExtractionError,
    extract_text_from_resume_bytes,
)
from backend.services.text_cleaning import clean_resume_text
from scripts.persist_outlook_tw394_folder import _build_outlook_dropbox_export_path

SUPPORTED_RESUME_SUFFIXES = (".pdf", ".doc", ".docx")
SUPPORTED_RESUME_CONTENT_TYPES = {
    "application/pdf",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}
POSITIVE_SECTION_TERMS = (
    "experience",
    "employment",
    "education",
    "skills",
    "certifications",
    "projects",
    "professional summary",
    "profile",
)
NEGATIVE_DOCUMENT_TERMS = (
    "agreement",
    "services agreement",
    "recruitment services agreement",
    "agency terms",
    "countersigned",
    "invoice",
    "receipt",
    "statement",
    "energy statement",
    "billing statement",
    "account statement",
    "bank statement",
    "quote",
    "proposal",
    "purchase order",
    "timesheet",
    "account number",
    "balance",
    "payment due",
    "payment date",
    "meter reading",
    "meter number",
    "tariff",
    "direct debit",
    "opening balance",
    "closing balance",
    "unit rate",
    "standing charge",
    "usage summary",
    "job description",
    "job spec",
    "brochure",
    "terms and conditions",
)

EMAIL_REGEX = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
PHONE_REGEX = re.compile(r"(?:\+?\d[\d\s().-]{7,}\d)")
YEAR_REGEX = re.compile(r"\b(?:19|20)\d{2}\b")
LINKEDIN_REGEX = re.compile(r"linkedin\.com/in/", re.IGNORECASE)


def run_outlook_cv_attachment_export(
    *,
    access_token: str,
    mailbox: str | None,
    folder_id: str,
    folder_path: list[str],
    message_limit: int,
    attachment_limit: int,
    dropbox_access_token: str | None,
    dropbox_export_folder: str | None,
    received_from: datetime | None = None,
    received_to: datetime | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """
    Scan one bounded Outlook folder slice and export only heuristic CV matches.
    """

    messages_result = fetch_outlook_messages(
        access_token=access_token,
        folder_id=folder_id,
        mailbox=mailbox,
        limit=message_limit,
        received_from=received_from,
        received_to=received_to,
    )
    messages = messages_result.get("messages", [])

    exported_items: list[dict[str, Any]] = []
    non_resume_items: list[dict[str, Any]] = []
    skipped_items: list[dict[str, Any]] = []
    failed_items: list[dict[str, Any]] = []

    messages_with_attachments = 0
    supported_attachment_count = 0
    extracted_attachment_count = 0
    detected_resume_count = 0

    for message in messages:
        if len(exported_items) >= attachment_limit:
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

        messages_with_attachments += 1

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

        for attachment in attachment_list_result.get("attachments", []):
            if len(exported_items) >= attachment_limit:
                break

            attachment_id = attachment.get("id")
            if not isinstance(attachment_id, str) or attachment_id.strip() == "":
                skipped_items.append(
                    {
                        "reason": "missing_attachment_id",
                        "message_id": message_id,
                        "message_subject": message.get("subject"),
                        "file_name": attachment.get("name"),
                    }
                )
                continue

            support_result = assess_outlook_attachment_support(attachment)
            if not support_result["is_supported"]:
                skipped_items.append(
                    {
                        "reason": support_result["reason"],
                        "message_id": message_id,
                        "attachment_id": attachment_id,
                        "message_subject": message.get("subject"),
                        "file_name": attachment.get("name"),
                        "content_type": attachment.get("contentType"),
                    }
                )
                continue

            supported_attachment_count += 1

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
                cleaned_text = clean_resume_text(extracted_resume_text["text"])
                extracted_attachment_count += 1
            except ResumeTextExtractionError as exc:
                skipped_items.append(
                    {
                        "reason": "resume_text_extraction_failed",
                        "message_id": message_id,
                        "attachment_id": attachment_id,
                        "message_subject": message.get("subject"),
                        "file_name": attachment.get("name"),
                        "content_type": attachment.get("contentType"),
                        "error_type": exc.__class__.__name__,
                        "message": str(exc),
                    }
                )
                continue
            except OutlookApiError as exc:
                failed_items.append(
                    {
                        "stage": "attachment_download",
                        "message_id": message_id,
                        "attachment_id": attachment_id,
                        "message_subject": message.get("subject"),
                        "file_name": attachment.get("name"),
                        "error_type": exc.__class__.__name__,
                        "message": str(exc),
                    }
                )
                continue

            detection_result = score_resume_likeness(
                file_name=attachment_download.get("file_name"),
                content_type=attachment_download.get("content_type"),
                cleaned_text=cleaned_text,
            )
            base_item = {
                "message_id": message_id,
                "attachment_id": attachment_id,
                "message_subject": message.get("subject"),
                "file_name": attachment_download.get("file_name"),
                "content_type": attachment_download.get("content_type"),
                "byte_count": len(attachment_download["content_bytes"]),
                "character_count": len(cleaned_text),
                "heuristic": detection_result,
            }

            if not detection_result["is_resume_like"]:
                non_resume_items.append(base_item)
                continue

            detected_resume_count += 1

            dropbox_export_path = None
            if (
                not dry_run
                and isinstance(dropbox_access_token, str)
                and dropbox_access_token.strip() != ""
                and isinstance(dropbox_export_folder, str)
                and dropbox_export_folder.strip() != ""
            ):
                dropbox_export_path = _build_outlook_dropbox_export_path(
                    base_folder=dropbox_export_folder,
                    received_at=message.get("receivedDateTime"),
                    file_name=attachment_download.get("file_name"),
                )
                upload_dropbox_file(
                    access_token=dropbox_access_token,
                    path=dropbox_export_path,
                    content_bytes=attachment_download["content_bytes"],
                    timeout_seconds=120.0,
                    autorename=True,
                )

            exported_items.append(
                {
                    **base_item,
                    "dropbox_export_path": dropbox_export_path,
                }
            )

    return {
        "mailbox": mailbox,
        "folder_id": folder_id,
        "folder_path": folder_path,
        "message_limit": message_limit,
        "attachment_limit": attachment_limit,
        "received_from": messages_result.get("received_from"),
        "received_to": messages_result.get("received_to"),
        "dry_run": dry_run,
        "message_count_scanned": len(messages),
        "messages_with_attachments": messages_with_attachments,
        "supported_attachment_count": supported_attachment_count,
        "extracted_attachment_count": extracted_attachment_count,
        "detected_resume_count": detected_resume_count,
        "exported_count": len(exported_items),
        "non_resume_count": len(non_resume_items),
        "skipped_count": len(skipped_items),
        "failed_count": len(failed_items),
        "exported_items": exported_items,
        "non_resume_items": non_resume_items[:20],
        "skipped_items": skipped_items,
        "failed_items": failed_items,
    }


def assess_outlook_attachment_support(attachment: dict[str, Any]) -> dict[str, Any]:
    """
    Return whether one Outlook attachment is locally processable as a CV candidate.
    """

    odata_type = attachment.get("@odata.type")
    if odata_type != "#microsoft.graph.fileAttachment":
        return {"is_supported": False, "reason": "unsupported_attachment_type"}

    file_name = attachment.get("name")
    lowered_name = file_name.strip().lower() if isinstance(file_name, str) else ""
    content_type = (
        attachment.get("contentType").strip().lower()
        if isinstance(attachment.get("contentType"), str)
        else ""
    )

    if lowered_name == "":
        return {"is_supported": False, "reason": "missing_file_name"}

    if lowered_name.endswith(".lnk"):
        return {"is_supported": False, "reason": "unsupported_file_suffix"}

    if lowered_name.endswith(SUPPORTED_RESUME_SUFFIXES):
        return {"is_supported": True, "reason": "supported_file_suffix"}

    if content_type in SUPPORTED_RESUME_CONTENT_TYPES:
        return {"is_supported": True, "reason": "supported_content_type"}

    return {"is_supported": False, "reason": "unsupported_file_suffix"}


def score_resume_likeness(
    *,
    file_name: str | None,
    content_type: str | None,
    cleaned_text: str,
) -> dict[str, Any]:
    """
    Score one extracted attachment text for CV-likeness using local heuristics.
    """

    normalized_name = file_name.strip().lower() if isinstance(file_name, str) else ""
    normalized_content_type = (
        content_type.strip().lower() if isinstance(content_type, str) else ""
    )
    normalized_text = cleaned_text.strip()
    lowered_text = normalized_text.lower()

    score = 0
    positive_signals: list[str] = []
    negative_signals: list[str] = []

    if normalized_name.endswith(SUPPORTED_RESUME_SUFFIXES):
        score += 2
        positive_signals.append("supported_file_type")

    if normalized_content_type in SUPPORTED_RESUME_CONTENT_TYPES:
        score += 1
        positive_signals.append("supported_content_type")

    if "cv" in normalized_name or "resume" in normalized_name or "curriculum vitae" in normalized_name:
        score += 3
        positive_signals.append("resume_like_filename")

    if len(normalized_text) >= 2500:
        score += 2
        positive_signals.append("substantial_text_length")
    elif len(normalized_text) >= 800:
        score += 1
        positive_signals.append("moderate_text_length")

    section_hits = [term for term in POSITIVE_SECTION_TERMS if term in lowered_text]
    if len(section_hits) >= 2:
        score += min(len(section_hits), 4)
        positive_signals.append(f"section_hits:{len(section_hits)}")

    email_count = len(EMAIL_REGEX.findall(normalized_text))
    if email_count >= 1:
        score += 2
        positive_signals.append("email_present")

    phone_count = len(PHONE_REGEX.findall(normalized_text))
    if phone_count >= 1:
        score += 2
        positive_signals.append("phone_present")

    linkedin_present = LINKEDIN_REGEX.search(normalized_text) is not None
    if linkedin_present:
        score += 1
        positive_signals.append("linkedin_present")

    year_count = len(YEAR_REGEX.findall(normalized_text))
    if year_count >= 4:
        score += 2
        positive_signals.append("employment_dates_present")
    elif year_count >= 2:
        score += 1
        positive_signals.append("some_dates_present")

    negative_hits = [term for term in NEGATIVE_DOCUMENT_TERMS if term in lowered_text]
    if negative_hits:
        score -= min(len(negative_hits) * 2, 6)
        negative_signals.extend(negative_hits)

    personal_identity_signal = (
        email_count >= 1
        or phone_count >= 1
        or linkedin_present
        or "resume_like_filename" in positive_signals
    )
    career_structure_signal = len(section_hits) >= 2 or year_count >= 2
    strong_negative_document_signal = (
        len(negative_hits) >= 3
        and not linkedin_present
        and "resume_like_filename" not in positive_signals
    )
    transactional_document_signal = (
        (
            len(negative_hits) >= 2
            and len(section_hits) == 0
            and "resume_like_filename" not in positive_signals
        )
        or strong_negative_document_signal
    )
    is_resume_like = (
        score >= 5
        and personal_identity_signal
        and career_structure_signal
        and not transactional_document_signal
    )

    return {
        "score": score,
        "is_resume_like": is_resume_like,
        "email_count": email_count,
        "phone_count": phone_count,
        "year_count": year_count,
        "section_hits": section_hits,
        "personal_identity_signal": personal_identity_signal,
        "career_structure_signal": career_structure_signal,
        "transactional_document_signal": transactional_document_signal,
        "positive_signals": positive_signals,
        "negative_signals": negative_signals,
    }


__all__ = [
    "SUPPORTED_RESUME_CONTENT_TYPES",
    "SUPPORTED_RESUME_SUFFIXES",
    "assess_outlook_attachment_support",
    "run_outlook_cv_attachment_export",
    "score_resume_likeness",
]
