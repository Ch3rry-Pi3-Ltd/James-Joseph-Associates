"""
Unit tests for Outlook resume persistence service helpers.

This module tests the business-side persistence rules in
`backend.services.outlook_resume_persistence`.

It gives the rest of the repository a stable way to check:

- the persistence payload keeps the important Outlook provenance material
- the `tw...` vacancy code is preserved from mailbox context
- the service delegates the final write to the lower-level DB helper
"""

from unittest.mock import patch

from backend.services.outlook_resume_persistence import (
    build_outlook_resume_persistence_payload,
    persist_outlook_message_attachment_resume,
)


def _build_sample_message() -> dict[str, object]:
    """
    Return a small Outlook message shape suitable for persistence tests.

    Example
    -------
    The default call returns a minimal advert-response wrapper with:

    - a real-looking message ID
    - `tw...` vacancy code in the subject
    - sender, conversation, and received-time fields
    """

    return {
        "id": "AAMkAGI2-message",
        "subject": (
            "sulaimanalikhan710@gmail.com - Totaljobs - Suitable application "
            "for Junior Desktop Engineer - Hedge Fund tw394"
        ),
        "receivedDateTime": "2026-05-21T08:00:00Z",
        "internetMessageId": "<internet-message-id@example.com>",
        "conversationId": "conversation-123",
        "hasAttachments": True,
        "from": {
            "emailAddress": {
                "name": "Totaljobs.com",
                "address": "totaljobs@totaljobsmail.com",
            }
        },
    }


def _build_sample_attachment_download() -> dict[str, object]:
    """
    Return a small Outlook attachment-download payload for persistence tests.

    Example
    -------
    The returned payload mirrors the narrow service-side shape:

    - message ID
    - attachment ID
    - file name
    - MIME type
    - raw bytes
    """

    return {
        "mailbox": None,
        "message_id": "AAMkAGI2-message",
        "attachment_id": "AAMkAGI2-attachment",
        "file_name": (
            "SULAIMAN MOHAMMED (412c3f29-e0be-4888-981a-4ae29d524ae2 - "
            "Totaljobs).pdf"
        ),
        "content_type": "application/pdf",
        "content_bytes": b"fake-pdf-bytes",
        "attachment_metadata": {"size": 54656},
        "endpoint_url": "https://graph.microsoft.com/v1.0/me/messages/...",
    }


def _build_sample_extracted_resume_text() -> dict[str, object]:
    """
    Return a small extracted-text bundle for persistence tests.

    Example
    -------
    The returned payload mirrors the extraction helper output with the added
    cleaned-text field used by persistence.
    """

    return {
        "text": "Raw extracted CV text",
        "cleaned_text": "Cleaned extracted CV text",
        "page_count": 2,
        "extractor": "pypdf",
        "file_name": "Candidate CV.pdf",
        "character_count": 6185,
    }


def test_build_outlook_resume_persistence_payload_keeps_key_provenance() -> None:
    """
    Verify that the persistence payload keeps the important provenance slices.

    Notes
    -----
    The first Outlook persistence path is intentionally narrow, but it still
    needs to preserve the source-side evidence that explains where the
    canonical document came from:

    - folder context
    - mailbox message metadata
    - attachment metadata
    - extracted text metrics
    - inferred `tw...` vacancy code
    """

    payload = build_outlook_resume_persistence_payload(
        microsoft_user_id="b4dd6a5f-8e27-4745-9369-e117121382ed",
        mailbox=None,
        folder_path=["# ADV-CVR", "### DOMINIQUE FOLDER", "tw394"],
        folder_id="folder-tw394",
        message=_build_sample_message(),
        attachment_download=_build_sample_attachment_download(),
        extracted_resume_text=_build_sample_extracted_resume_text(),
        quality_assessment={
            "status": "review",
            "quality_score": 70,
            "reasons": ["thin_cv"],
        },
    )

    assert payload["source_system"] == "outlook_resume"
    assert payload["tw_code"] == "tw394"
    assert payload["message_source_record_id"] == (
        "b4dd6a5f-8e27-4745-9369-e117121382ed:me:AAMkAGI2-message"
    )
    assert payload["attachment_source_record_id"] == (
        "b4dd6a5f-8e27-4745-9369-e117121382ed:me:AAMkAGI2-message:"
        "AAMkAGI2-attachment"
    )
    assert payload["resume_title"].endswith(".pdf")
    assert payload["quality_status"] == "review"
    assert payload["quality_score"] == 70
    assert payload["resume_source_uri"] == (
        "outlook://users/b4dd6a5f-8e27-4745-9369-e117121382ed/mailboxes/me/"
        "messages/AAMkAGI2-message/attachments/AAMkAGI2-attachment"
    )
    assert payload["cleaned_resume_text"] == "Cleaned extracted CV text"
    assert payload["message_source_payload"]["folder_path_text"] == (
        "# ADV-CVR > ### DOMINIQUE FOLDER > tw394"
    )
    assert payload["attachment_source_payload"]["extractor"] == "pypdf"
    assert payload["message_source_payload_hash"]
    assert payload["attachment_source_payload_hash"]


def test_persist_outlook_message_attachment_resume_delegates_to_db_helper() -> None:
    """
    Verify that the service delegates the prepared payload to the DB helper.

    Notes
    -----
    This test stops at the service boundary. The SQL write logic is covered
    separately. Here we only want to prove that:

    - the source pair is accepted
    - the prepared payload is handed to the lower layer
    - the DB helper summary is passed back unchanged
    """

    with patch(
        "backend.services.outlook_resume_persistence.persist_outlook_resume_snapshot"
    ) as mock_persist:
        mock_persist.return_value = {
            "document_id": "document-uuid",
            "resolved_job_id": None,
        }

        summary = persist_outlook_message_attachment_resume(
            microsoft_user_id="b4dd6a5f-8e27-4745-9369-e117121382ed",
            mailbox=None,
            folder_path=["# ADV-CVR", "### DOMINIQUE FOLDER", "tw394"],
            folder_id="folder-tw394",
            message=_build_sample_message(),
            attachment_download=_build_sample_attachment_download(),
            extracted_resume_text=_build_sample_extracted_resume_text(),
            quality_assessment={"status": "review", "quality_score": 70},
        )

    assert summary == {
        "document_id": "document-uuid",
        "resolved_job_id": None,
    }
    mock_persist.assert_called_once()
