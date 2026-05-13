"""
Unit tests for resume-extraction database persistence helpers.

This module tests the narrow transactional write helper in
`backend.db.resume_extraction_persistence`.

It gives the rest of the repository a stable way to check:

- the helper can run end to end without a real database
- the transaction commits on success
- the returned summary keeps the key canonical IDs and counts

These tests are intentionally narrow. They do not try to re-prove every SQL
statement. Their job is to pin the important orchestration contract of the
write helper while keeping the test setup readable.
"""

from unittest.mock import MagicMock, patch
from uuid import uuid4

from backend.db.resume_extraction_persistence import (
    persist_jobadder_resume_extraction_snapshot,
)


def test_persist_jobadder_resume_extraction_snapshot_commits_and_returns_summary() -> None:
    """
    Verify that the persistence helper commits and returns the key summary data.

    Notes
    -----
    This test uses a deliberately small payload:

    - no resume document
    - no company
    - no extracted skills

    That keeps the mocked cursor flow small enough to follow while still
    exercising the important transaction path:

    - source-record upserts
    - person upsert
    - candidate upsert
    - source-link creation
    - commit

    Example
    -------
    Even with a deliberately tiny payload, the helper should still return a
    JSON-safe summary containing the canonical person and candidate IDs as
    strings.
    """

    persistence_payload = {
        "source_candidate_id": 16496678,
        "latest_resume": {},
        "candidate_source_payload": {"candidate_context": {"first_name": "Roger"}},
        "candidate_source_payload_hash": "candidate-hash",
        "resume_source_payload": {},
        "resume_source_payload_hash": "resume-hash",
        "extraction_source_payload": {"structured_extraction": {}},
        "extraction_source_payload_hash": "extraction-hash",
        "import_run_id": "run-123",
        "current_employer": None,
        "full_name": "Roger Campbell",
        "first_name": "Roger",
        "last_name": "Campbell",
        "primary_email": "roger@example.com",
        "primary_phone": "+447700900111",
        "linkedin_url": None,
        "location": "London",
        "headline": "Software Engineer",
        "summary": "Builds backend systems.",
        "candidate_status": "Active",
        "availability_status": None,
        "current_title": "Software Engineer",
        "last_contacted_at": "2026-05-10T10:00:00Z",
        "resume_updated_at": None,
        "resume_source_uri": None,
        "resume_content_hash": "resume-content-hash",
        "cleaned_resume_text": "Resume body",
        "skills": [],
        "tools_and_platforms": [],
        "quality_status": "pass",
    }

    mock_cursor = MagicMock()
    person_uuid = uuid4()
    candidate_uuid = uuid4()
    source_record_uuid = uuid4()
    extraction_source_record_uuid = uuid4()
    mock_cursor.fetchone.side_effect = [
        {"id": source_record_uuid},
        {"id": extraction_source_record_uuid},
        None,
        None,
        {"id": person_uuid},
        None,
        None,
        {"id": candidate_uuid},
        None,
        None,
        None,
        None,
    ]

    mock_connection = MagicMock()
    mock_connection.cursor.return_value.__enter__.return_value = mock_cursor

    with patch(
        "backend.db.resume_extraction_persistence.postgres_connection"
    ) as mock_postgres_connection:
        mock_postgres_connection.return_value.__enter__.return_value = (
            mock_connection
        )

        summary = persist_jobadder_resume_extraction_snapshot(persistence_payload)

    assert summary["person_id"] == str(person_uuid)
    assert summary["candidate_id"] == str(candidate_uuid)
    assert summary["candidate_source_record_id"] == str(source_record_uuid)
    assert (
        summary["extraction_source_record_id"] == str(extraction_source_record_uuid)
    )
    assert summary["resume_source_record_id"] is None
    assert summary["document_id"] is None
    assert summary["candidate_skill_count"] == 0
    assert isinstance(summary["person_id"], str)
    assert isinstance(summary["candidate_id"], str)
    mock_connection.commit.assert_called_once()
