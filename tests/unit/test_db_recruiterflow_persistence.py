"""
Unit tests for Recruiterflow database persistence helpers.

This module tests the narrow transactional write helpers in
`backend.db.recruiterflow_persistence`.

It gives the rest of the repository a stable way to check:

- the job helper can run end to end without a real database
- the candidate helper can run end to end without a real database
- transactions commit on success
- the returned summaries keep the key canonical IDs and provenance IDs
"""

from decimal import Decimal
from unittest.mock import MagicMock, patch
from uuid import uuid4

from backend.db.recruiterflow_persistence import (
    persist_recruiterflow_candidate_file_content,
    persist_recruiterflow_candidate_file_reference,
    persist_recruiterflow_candidate_snapshot,
    persist_recruiterflow_job_file_reference,
    persist_recruiterflow_job_snapshot,
)


def test_persist_recruiterflow_job_snapshot_commits_and_returns_summary() -> None:
    """
    Verify that the Recruiterflow job persistence helper commits and returns key summary data.
    """

    persistence_payload = {
        "source_job_id": 102,
        "tw_code": "tw337",
        "company_name": None,
        "job_title": "tw337 - Client Services Senior Associate",
        "job_description": "Role text",
        "job_location": "London, United Kingdom",
        "workplace_type": "Hybrid",
        "employment_type": "Permanent",
        "work_type": None,
        "source": "recruiterflow",
        "owner_name": "Tom Owens",
        "salary_min": Decimal("75000"),
        "salary_max": Decimal("90000"),
        "currency": "GBP",
        "status": "Open",
        "opened_at": "2026-03-11T20:27:51+0000",
        "closed_at": None,
        "updated_from_source_at": "2026-03-11T20:27:51+0000",
        "job_source_payload": {"job_payload": {"id": 102}},
        "job_source_payload_hash": "job-source-hash",
        "import_run_id": "recruiterflow_job:102:job/1.134.json",
    }

    mock_cursor = MagicMock()
    job_source_record_uuid = uuid4()
    job_uuid = uuid4()

    mock_cursor.fetchone.side_effect = [
        {"id": job_source_record_uuid},
        None,
        {"id": job_uuid},
        None,
    ]

    mock_connection = MagicMock()
    mock_connection.cursor.return_value.__enter__.return_value = mock_cursor

    with patch("backend.db.recruiterflow_persistence.postgres_connection") as mock_conn:
        mock_conn.return_value.__enter__.return_value = mock_connection
        summary = persist_recruiterflow_job_snapshot(persistence_payload)

    assert summary["tw_code"] == "tw337"
    assert summary["company_id"] is None
    assert summary["job_id"] == str(job_uuid)
    assert summary["job_source_record_id"] == str(job_source_record_uuid)
    mock_connection.commit.assert_called_once()


def test_persist_recruiterflow_candidate_snapshot_commits_and_returns_summary() -> None:
    """
    Verify that the Recruiterflow candidate persistence helper commits and returns key summary data.
    """

    persistence_payload = {
        "source_candidate_id": 4847,
        "tw_code": "tw337",
        "full_name": "Bernardita Gutierrez",
        "first_name": "Bernardita",
        "last_name": "Gutierrez",
        "primary_email": "bngutierrezvg@gmail.com",
        "primary_phone": "7775092914",
        "linkedin_url": "https://linkedin.com/in/bernardita",
        "location": "Santiago, Chile",
        "headline": "Chief Legal Officer",
        "summary": "Chief Legal Officer profile",
        "candidate_status": "Active",
        "availability_status": None,
        "current_title": "Chief Legal Officer",
        "current_employer": "Sociedad Concesionaria del Norte S.A.",
        "last_contacted_at": "2026-03-11T20:27:51+0000",
        "resume_updated_at": "2026-03-11T20:27:51+00:00",
        "social_profiles": {"linkedin_url": "https://linkedin.com/in/bernardita"},
        "job_links": [
            {
                "source_job_id": 102,
                "source_record_id": "4847:102",
                "job_title": "tw337 - Client Services Senior Associate",
                "application_status": "Applied",
                "source": "Google Jobs",
                "applied_at": "2026-03-11T20:27:51+0000",
                "source_payload": {"job_link_payload": {"job_id": 102}},
                "source_payload_hash": "job-link-hash",
            }
        ],
        "candidate_source_payload": {"candidate_payload": {"id": 4847}},
        "candidate_source_payload_hash": "candidate-source-hash",
        "import_run_id": "recruiterflow_candidate:4847:candidate/1.100.json",
    }

    mock_cursor = MagicMock()
    candidate_source_record_uuid = uuid4()
    company_uuid = uuid4()
    person_uuid = uuid4()
    candidate_uuid = uuid4()
    application_source_record_uuid = uuid4()
    application_uuid = uuid4()
    job_uuid = uuid4()

    mock_cursor.fetchone.side_effect = [
        {"id": candidate_source_record_uuid},
        None,
        {"id": company_uuid},
        None,
        None,
        None,
        {"id": person_uuid},
        None,
        None,
        {"id": candidate_uuid},
        None,
        None,
        None,
        {"job_id": job_uuid},
        {"id": application_source_record_uuid},
        None,
        None,
        {"id": application_uuid},
        None,
        None,
        None,
    ]

    mock_connection = MagicMock()
    mock_connection.cursor.return_value.__enter__.return_value = mock_cursor

    with patch("backend.db.recruiterflow_persistence.postgres_connection") as mock_conn:
        mock_conn.return_value.__enter__.return_value = mock_connection
        summary = persist_recruiterflow_candidate_snapshot(persistence_payload)

    assert summary["tw_code"] == "tw337"
    assert summary["person_id"] == str(person_uuid)
    assert summary["candidate_id"] == str(candidate_uuid)
    assert summary["current_company_id"] == str(company_uuid)
    assert summary["candidate_source_record_id"] == str(candidate_source_record_uuid)
    assert summary["resolved_application_count"] == 1
    assert summary["unresolved_job_link_count"] == 0
    assert summary["resolved_application_ids"] == [str(application_uuid)]
    mock_connection.commit.assert_called_once()


def test_persist_recruiterflow_candidate_file_reference_commits_and_returns_summary() -> None:
    """
    Verify that the candidate-file persistence helper commits and returns key summary data.
    """

    persistence_payload = {
        "source_candidate_id": 4847,
        "source_file_record_id": "4847:5679",
        "document_title": "Bernardita Gutierrez CV EN 03-2026.pdf",
        "source_uri": "https://example.com/candidate-cv.pdf",
        "mime_type": "application/pdf",
        "content_hash": None,
        "candidate_file_source_payload": {"candidate_file_payload": {"id": 5679}},
        "candidate_file_source_payload_hash": "candidate-file-source-hash",
        "import_run_id": "recruiterflow_candidate_file_reference:4847:5679:candidate/1.100.json",
    }

    mock_cursor = MagicMock()
    candidate_uuid = uuid4()
    candidate_file_source_record_uuid = uuid4()
    document_uuid = uuid4()

    mock_cursor.fetchone.side_effect = [
        {"candidate_id": candidate_uuid},
        {"id": candidate_file_source_record_uuid},
        None,
        None,
        {"id": document_uuid},
        None,
        None,
        None,
    ]

    mock_connection = MagicMock()
    mock_connection.cursor.return_value.__enter__.return_value = mock_cursor

    with patch("backend.db.recruiterflow_persistence.postgres_connection") as mock_conn:
        mock_conn.return_value.__enter__.return_value = mock_connection
        summary = persist_recruiterflow_candidate_file_reference(persistence_payload)

    assert summary["candidate_id"] == str(candidate_uuid)
    assert summary["document_id"] == str(document_uuid)
    assert (
        summary["candidate_file_source_record_id"]
        == str(candidate_file_source_record_uuid)
    )
    mock_connection.commit.assert_called_once()


def test_persist_recruiterflow_job_file_reference_commits_and_returns_summary() -> None:
    """
    Verify that the job-file persistence helper commits and returns key summary data.
    """

    persistence_payload = {
        "source_job_id": 102,
        "source_file_record_id": "102:9001",
        "job_title": "tw337 - Client Services Senior Associate",
        "document_title": "Job brief.pdf",
        "source_uri": "https://example.com/job-brief.pdf",
        "mime_type": "application/pdf",
        "content_hash": None,
        "job_file_source_payload": {"job_file_payload": {"id": 9001}},
        "job_file_source_payload_hash": "job-file-source-hash",
        "import_run_id": "recruiterflow_job_file_reference:102:9001:job/1.134.json",
    }

    mock_cursor = MagicMock()
    job_uuid = uuid4()
    job_file_source_record_uuid = uuid4()
    document_uuid = uuid4()

    mock_cursor.fetchone.side_effect = [
        {"job_id": job_uuid},
        {"id": job_file_source_record_uuid},
        None,
        None,
        {"id": document_uuid},
        None,
        None,
        None,
    ]

    mock_connection = MagicMock()
    mock_connection.cursor.return_value.__enter__.return_value = mock_cursor

    with patch("backend.db.recruiterflow_persistence.postgres_connection") as mock_conn:
        mock_conn.return_value.__enter__.return_value = mock_connection
        summary = persist_recruiterflow_job_file_reference(persistence_payload)

    assert summary["job_id"] == str(job_uuid)
    assert summary["document_id"] == str(document_uuid)
    assert summary["job_file_source_record_id"] == str(job_file_source_record_uuid)
    mock_connection.commit.assert_called_once()


def test_persist_recruiterflow_candidate_file_content_commits_and_returns_summary() -> None:
    """
    Verify that the candidate-file content persistence helper commits and returns key summary data.
    """

    persistence_payload = {
        "source_candidate_id": 4847,
        "source_file_record_id": "4847:5679",
        "document_title": "Bernardita Gutierrez CV EN 03-2026.pdf",
        "source_uri": "https://example.com/candidate-cv.pdf",
        "mime_type": "application/pdf",
        "content_hash": "hash-123",
        "extracted_text": "Bernardita Gutierrez CV",
        "character_count": 24,
        "sync_status": "extracted",
        "error_message": None,
        "candidate_file_content_source_payload": {
            "candidate_file_payload": {"id": 5679}
        },
        "candidate_file_content_source_payload_hash": "candidate-file-content-hash",
        "import_run_id": "recruiterflow_candidate_file_content:4847:5679:candidate/1.100.json",
    }

    mock_cursor = MagicMock()
    candidate_uuid = uuid4()
    reference_source_record_uuid = uuid4()
    content_source_record_uuid = uuid4()
    document_uuid = uuid4()

    mock_cursor.fetchone.side_effect = [
        {"candidate_id": candidate_uuid},
        {"id": reference_source_record_uuid},
        {"document_id": document_uuid},
        {"id": content_source_record_uuid},
        None,
        None,
    ]

    mock_connection = MagicMock()
    mock_connection.cursor.return_value.__enter__.return_value = mock_cursor

    with patch("backend.db.recruiterflow_persistence.postgres_connection") as mock_conn:
        mock_conn.return_value.__enter__.return_value = mock_connection
        summary = persist_recruiterflow_candidate_file_content(persistence_payload)

    assert summary["candidate_id"] == str(candidate_uuid)
    assert summary["document_id"] == str(document_uuid)
    assert summary["sync_status"] == "extracted"
    assert (
        summary["candidate_file_content_source_record_id"]
        == str(content_source_record_uuid)
    )
    mock_connection.commit.assert_called_once()
