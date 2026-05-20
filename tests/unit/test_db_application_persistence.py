"""
Unit tests for application database persistence helpers.

This module tests the narrow transactional write helper in
`backend.db.application_persistence`.

It gives the rest of the repository a stable way to check:

- the helper can run end to end without a real database
- the transaction commits on success
- the returned summary keeps the key canonical IDs and provenance IDs

These tests are intentionally narrow. They do not try to re-prove every SQL
statement. Their job is to pin the important orchestration contract of the
write helper while keeping the mocked cursor flow readable.
"""

from unittest.mock import MagicMock, patch
from uuid import uuid4

from backend.db.application_persistence import persist_jobadder_application_snapshot


def test_persist_jobadder_application_snapshot_commits_and_returns_summary() -> None:
    """
    Verify that the persistence helper commits and returns the key summary data.

    Notes
    -----
    This test uses a deliberately small but realistic payload:

    - one JobAdder candidate source record
    - one JobAdder application source record
    - one current employer company
    - one canonical person
    - one canonical candidate
    - one canonical job already resolved from prior persistence work
    - one canonical application

    That keeps the mocked cursor flow small enough to follow while still
    exercising the important transaction path:

    - source-record upserts
    - company upsert
    - person/candidate upsert
    - canonical job resolution
    - application upsert
    - source-link creation
    - commit
    """

    persistence_payload = {
        "source_candidate_id": 17071060,
        "source_application_id": 12204918,
        "source_job_id": 936462,
        "tw_code": "tw398",
        "job_title": "tw398 - KDB Developer",
        "full_name": "Sanjeev Sarda",
        "first_name": "Sanjeev",
        "last_name": "Sarda",
        "primary_email": "sanjeev.sarda@gmail.com",
        "primary_phone": "+44(0)7912 071 369",
        "linkedin_url": "https://linkedin.com/in/sanjeev-sarda",
        "location": None,
        "headline": "Senior Engineer",
        "summary": None,
        "candidate_status": "Active",
        "availability_status": None,
        "current_title": "Senior Engineer",
        "current_position": "Senior Engineer",
        "current_employer": "Freelancing, UpWork",
        "last_contacted_at": "2026-05-18T14:00:00Z",
        "resume_updated_at": "2026-05-18T14:00:00Z",
        "application_status": '"INBOX"= New-CV\'s - [So CVR them!]',
        "source": "Database",
        "rating": None,
        "candidate_rating": None,
        "social_profiles": {"linkedin_url": "https://linkedin.com/in/sanjeev-sarda"},
        "applied_at": "2026-05-10T09:00:00Z",
        "candidate_source_payload": {"candidate_detail_response": {"candidate": {}}},
        "candidate_source_payload_hash": "candidate-source-hash",
        "application_source_payload": {
            "application_detail_response": {"application": {}}
        },
        "application_source_payload_hash": "application-source-hash",
        "import_run_id": "jobadder_application:12204918:2026-05-20T20:00:00+00:00",
    }

    mock_cursor = MagicMock()
    candidate_source_record_uuid = uuid4()
    application_source_record_uuid = uuid4()
    company_uuid = uuid4()
    person_uuid = uuid4()
    candidate_uuid = uuid4()
    job_uuid = uuid4()
    application_uuid = uuid4()

    mock_cursor.fetchone.side_effect = [
        {"id": candidate_source_record_uuid},
        {"id": application_source_record_uuid},
        None,
        {"id": company_uuid},
        None,
        None,
        None,
        {"id": person_uuid},
        None,
        None,
        {"id": candidate_uuid},
        {"job_id": job_uuid},
        None,
        None,
        {"id": application_uuid},
        None,
        None,
        None,
        None,
        None,
        None,
    ]

    mock_connection = MagicMock()
    mock_connection.cursor.return_value.__enter__.return_value = mock_cursor

    with patch("backend.db.application_persistence.postgres_connection") as mock_conn:
        mock_conn.return_value.__enter__.return_value = mock_connection
        summary = persist_jobadder_application_snapshot(persistence_payload)

    assert summary["tw_code"] == "tw398"
    assert summary["person_id"] == str(person_uuid)
    assert summary["candidate_id"] == str(candidate_uuid)
    assert summary["current_company_id"] == str(company_uuid)
    assert summary["job_id"] == str(job_uuid)
    assert summary["application_id"] == str(application_uuid)
    assert summary["candidate_source_record_id"] == str(candidate_source_record_uuid)
    assert summary["application_source_record_id"] == str(application_source_record_uuid)
    mock_connection.commit.assert_called_once()
