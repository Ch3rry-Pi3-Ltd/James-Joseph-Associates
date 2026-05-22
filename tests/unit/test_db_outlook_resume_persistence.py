"""
Unit tests for Outlook resume database persistence helpers.

This module tests the narrow transactional write helper in
`backend.db.outlook_resume_persistence`.

It gives the rest of the repository a stable way to check:

- the helper can run end to end without a real database
- the transaction commits on success
- the returned summary keeps the key canonical IDs and provenance IDs
"""

from unittest.mock import MagicMock, patch
from uuid import uuid4

from backend.db.outlook_resume_persistence import persist_outlook_resume_snapshot


def test_persist_outlook_resume_snapshot_commits_and_returns_summary() -> None:
    """
    Verify that the persistence helper commits and returns the key summary data.

    Notes
    -----
    This test uses a deliberately small but realistic payload:

    - one Outlook message source record
    - one Outlook attachment source record
    - one canonical resume document
    - no resolved job link for the current slice

    That keeps the mocked cursor flow small enough to follow while still
    exercising the important transaction path:

    - source-record upserts
    - optional job lookup
    - document upsert
    - source/document link creation
    - commit
    """

    persistence_payload = {
        "tw_code": "tw394",
        "message_source_record_id": "user:me:message-1",
        "attachment_source_record_id": "user:me:message-1:attachment-1",
        "resume_title": "Candidate CV.pdf",
        "resume_mime_type": "application/pdf",
        "resume_source_uri": (
            "outlook://users/user/mailboxes/me/messages/message-1/"
            "attachments/attachment-1"
        ),
        "resume_content_hash": "resume-content-hash",
        "cleaned_resume_text": "Cleaned extracted CV text",
        "message_source_payload": {"subject": "Suitable application for tw394"},
        "message_source_payload_hash": "message-source-hash",
        "attachment_source_payload": {"file_name": "Candidate CV.pdf"},
        "attachment_source_payload_hash": "attachment-source-hash",
        "import_run_id": (
            "outlook_resume:user:# ADV-CVR > ### DOMINIQUE FOLDER > tw394:"
            "2026-05-21T18:00:00+00:00"
        ),
    }

    mock_cursor = MagicMock()
    message_source_record_uuid = uuid4()
    attachment_source_record_uuid = uuid4()
    document_uuid = uuid4()

    mock_cursor.fetchone.side_effect = [
        {"id": message_source_record_uuid},
        {"id": attachment_source_record_uuid},
        None,  # no resolved job row for tw394 yet
        None,  # no document already linked to attachment source record
        None,  # no document found by content hash
        {"id": document_uuid},
        None,
        None,
    ]

    mock_connection = MagicMock()
    mock_connection.cursor.return_value.__enter__.return_value = mock_cursor

    with patch("backend.db.outlook_resume_persistence.postgres_connection") as mock_conn:
        mock_conn.return_value.__enter__.return_value = mock_connection
        summary = persist_outlook_resume_snapshot(persistence_payload)

    assert summary["tw_code"] == "tw394"
    assert summary["resolved_job_id"] is None
    assert summary["document_id"] == str(document_uuid)
    assert summary["message_source_record_id"] == str(message_source_record_uuid)
    assert summary["attachment_source_record_id"] == str(
        attachment_source_record_uuid
    )
    mock_connection.commit.assert_called_once()
