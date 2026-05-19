"""
Unit tests for job/job-spec database persistence helpers.

This module tests the narrow transactional write helper in
`backend.db.job_spec_persistence`.

It gives the rest of the repository a stable way to check:

- the helper can run end to end without a real database
- the transaction commits on success
- the returned summary keeps the key canonical IDs and provenance IDs

These tests are intentionally narrow. They do not try to re-prove every SQL
statement. Their job is to pin the important orchestration contract of the
write helper while keeping the mocked cursor flow readable.
"""

from decimal import Decimal
from unittest.mock import MagicMock, patch
from uuid import uuid4

from backend.db.job_spec_persistence import persist_jobadder_job_spec_snapshot


def test_persist_jobadder_job_spec_snapshot_commits_and_returns_summary() -> None:
    """
    Verify that the persistence helper commits and returns the key summary data.

    Notes
    -----
    This test uses a deliberately small but realistic payload:

    - one JobAdder job source record
    - one Dropbox job-spec source record
    - one company
    - one canonical job
    - one canonical document

    That keeps the mocked cursor flow small enough to follow while still
    exercising the important transaction path:

    - source-record upserts
    - company upsert
    - job upsert
    - document upsert
    - source/document link creation
    - commit
    """

    persistence_payload = {
        "source_job_id": 936462,
        "tw_code": "tw398",
        "company_name": "B2C2",
        "job_title": "tw398 - KDB Developer",
        "job_description": "<p>KDB role</p>",
        "job_location": "London",
        "workplace_type": "Hybrid",
        "employment_type": "Permanent",
        "work_type": "Permanent",
        "source": "jobadder",
        "owner_name": "Tom Owens",
        "salary_min": Decimal("125000"),
        "salary_max": Decimal("125000"),
        "currency": "GBP",
        "status": "Open",
        "opened_at": "2026-05-01T09:00:00Z",
        "closed_at": None,
        "updated_from_source_at": "2026-05-18T14:00:00Z",
        "job_source_payload": {"job_detail_response": {"job": {"jobId": 936462}}},
        "job_source_payload_hash": "job-source-hash",
        "job_spec_title": "B2C2 - Snr. KDB Developer - London - 2026.pdf",
        "job_spec_source_uri": (
            "/new dropbox/# DLV/LIVE JOBS - [Job Specs]/tw398 - B2C2 - "
            "KDB Developer x2/B2C2 - Snr. KDB Developer - London - 2026.pdf"
        ),
        "job_spec_mime_type": "application/octet-stream",
        "job_spec_content_hash": "job-spec-text-hash",
        "job_spec_extracted_text": "Senior KDB Developer role text",
        "job_spec_source_payload": {
            "path": "/new dropbox/example.pdf",
            "file_name": "example.pdf",
        },
        "job_spec_source_payload_hash": "job-spec-source-hash",
        "import_run_id": "jobadder_job_spec:936462:2026-05-19T19:00:00+00:00",
    }

    mock_cursor = MagicMock()
    job_source_record_uuid = uuid4()
    job_spec_source_record_uuid = uuid4()
    company_uuid = uuid4()
    job_uuid = uuid4()
    document_uuid = uuid4()

    mock_cursor.fetchone.side_effect = [
        {"id": job_source_record_uuid},
        {"id": job_spec_source_record_uuid},
        None,
        {"id": company_uuid},
        None,
        None,
        {"id": job_uuid},
        None,
        None,
        {"id": document_uuid},
        None,
        None,
        None,
        None,
        None,
    ]

    mock_connection = MagicMock()
    mock_connection.cursor.return_value.__enter__.return_value = mock_cursor

    with patch("backend.db.job_spec_persistence.postgres_connection") as mock_conn:
        mock_conn.return_value.__enter__.return_value = mock_connection
        summary = persist_jobadder_job_spec_snapshot(persistence_payload)

    assert summary["tw_code"] == "tw398"
    assert summary["company_id"] == str(company_uuid)
    assert summary["job_id"] == str(job_uuid)
    assert summary["document_id"] == str(document_uuid)
    assert summary["job_source_record_id"] == str(job_source_record_uuid)
    assert summary["job_spec_source_record_id"] == str(job_spec_source_record_uuid)
    mock_connection.commit.assert_called_once()
