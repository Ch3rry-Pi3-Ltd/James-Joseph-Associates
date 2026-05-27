"""
Unit tests for Recruiterflow import service helpers.

This module tests the business-side persistence rules in
`backend.services.recruiterflow_import`.

It gives the rest of the repository a stable way to check:

- the job persistence payload keeps the important provenance material
- the candidate persistence payload keeps the important provenance material
- nested candidate-job links are normalized for later application writes
- the service delegates the final write to the lower-level DB helper
"""

from decimal import Decimal
from unittest.mock import patch

from backend.services.recruiterflow_import import (
    build_recruiterflow_candidate_persistence_payload,
    build_recruiterflow_job_file_reference_payload,
    build_recruiterflow_job_persistence_payload,
    persist_recruiterflow_candidate,
    persist_recruiterflow_job_file_reference,
    persist_recruiterflow_job,
)


def _build_sample_job_payload() -> dict[str, object]:
    """
    Return a small Recruiterflow job payload suitable for persistence tests.
    """

    return {
        "id": 102,
        "name": "tw337 - Client Services Senior Associate",
        "title": "Client Services Senior Associate",
        "about_position": "Client Services Senior Associate role text",
        "remote_status": {"name": "Hybrid"},
        "employment_type": {"name": "Permanent"},
        "job_status": {"name": "Open"},
        "salary_range_start": 75000,
        "salary_range_end": 90000,
        "salary_range_currency": "GBP",
        "locations": [{"city": "London", "country": "United Kingdom"}],
        "hiring_team": [{"name": "Tom Owens"}],
        "last_opened": "2026-03-11T20:27:51+0000",
    }


def _build_sample_candidate_payload() -> dict[str, object]:
    """
    Return a small Recruiterflow candidate payload suitable for persistence tests.
    """

    return {
        "id": 4847,
        "first_name": "Bernardita",
        "last_name": "Gutierrez",
        "name": "Bernardita Gutierrez",
        "email": ["bngutierrezvg@gmail.com"],
        "phone_number": ["7775092914"],
        "linkedin_profile": "https://linkedin.com/in/bernardita",
        "candidate_summary": "Chief Legal Officer profile",
        "current_designation": "Chief Legal Officer",
        "current_organization": "Sociedad Concesionaria del Norte S.A.",
        "status": {"name": "Active"},
        "location": {"city": "Santiago", "country": "Chile"},
        "source_name": "Google Jobs",
        "latest_activity_time": "2026-03-11T20:27:51+0000",
        "files": [
            {
                "id": 5679,
                "filename": "Bernardita Gutierrez CV EN 03-2026.pdf",
                "upload_time": "2026-03-11T20:27:51+00:00",
                "is_primary": True,
            }
        ],
        "jobs": [
            {
                "job_id": 102,
                "title": "tw337 - Client Services Senior Associate",
                "stage_name": "Applied",
                "added_time": "2026-03-11T20:27:51+0000",
            }
        ],
    }


def test_build_recruiterflow_job_persistence_payload_keeps_key_provenance() -> None:
    """
    Verify that the Recruiterflow job payload keeps the important provenance slices.
    """

    payload = build_recruiterflow_job_persistence_payload(
        export_source_uri="/exports/Recruiterflow.zip",
        member_name="job/1.134.json",
        job_payload=_build_sample_job_payload(),
    )

    assert payload["source_system"] == "recruiterflow_job"
    assert payload["source_job_id"] == 102
    assert payload["tw_code"] == "tw337"
    assert payload["job_title"] == "tw337 - Client Services Senior Associate"
    assert payload["job_description"] == "Client Services Senior Associate role text"
    assert payload["job_location"] == "London, United Kingdom"
    assert payload["workplace_type"] == "Hybrid"
    assert payload["employment_type"] == "Permanent"
    assert payload["status"] == "Open"
    assert payload["owner_name"] == "Tom Owens"
    assert payload["salary_min"] == Decimal("75000")
    assert payload["salary_max"] == Decimal("90000")
    assert payload["currency"] == "GBP"
    assert payload["job_source_payload"]["member_name"] == "job/1.134.json"
    assert payload["job_source_payload_hash"]


def test_build_recruiterflow_candidate_persistence_payload_keeps_job_links() -> None:
    """
    Verify that the Recruiterflow candidate payload keeps key provenance and job links.
    """

    payload = build_recruiterflow_candidate_persistence_payload(
        export_source_uri="/exports/Recruiterflow.zip",
        member_name="candidate/1.100.json",
        candidate_payload=_build_sample_candidate_payload(),
    )

    assert payload["source_system"] == "recruiterflow_candidate"
    assert payload["source_candidate_id"] == 4847
    assert payload["tw_code"] == "tw337"
    assert payload["full_name"] == "Bernardita Gutierrez"
    assert payload["primary_email"] == "bngutierrezvg@gmail.com"
    assert payload["primary_phone"] == "7775092914"
    assert payload["linkedin_url"] == "https://linkedin.com/in/bernardita"
    assert payload["current_title"] == "Chief Legal Officer"
    assert payload["current_employer"] == "Sociedad Concesionaria del Norte S.A."
    assert payload["candidate_source_payload"]["member_name"] == "candidate/1.100.json"
    assert payload["candidate_source_payload_hash"]
    assert len(payload["job_links"]) == 1
    assert payload["job_links"][0]["source_job_id"] == 102
    assert payload["job_links"][0]["application_status"] == "Applied"
    assert payload["job_links"][0]["source_payload_hash"]


def test_build_recruiterflow_job_file_reference_payload_keeps_metadata() -> None:
    """
    Verify that the job-file payload keeps the important reference metadata.
    """

    job_payload = {
        **_build_sample_job_payload(),
        "files": [
            {
                "file_id": 9001,
                "filename": "Job brief.pdf",
                "link": "https://example.com/job-brief.pdf",
            }
        ],
    }
    file_payload = job_payload["files"][0]
    assert isinstance(file_payload, dict)

    payload = build_recruiterflow_job_file_reference_payload(
        export_source_uri="/exports/Recruiterflow.zip",
        member_name="job/1.134.json",
        job_payload=job_payload,
        file_payload=file_payload,
    )

    assert payload["source_job_id"] == 102
    assert payload["source_file_record_id"] == "102:9001"
    assert payload["document_title"] == "Job brief.pdf"
    assert payload["source_uri"] == "https://example.com/job-brief.pdf"
    assert payload["mime_type"] == "application/pdf"
    assert payload["job_file_source_payload_hash"]


def test_persist_recruiterflow_job_delegates_to_db_helper() -> None:
    """
    Verify that the Recruiterflow job service delegates the prepared payload to the DB helper.
    """

    with patch(
        "backend.services.recruiterflow_import.persist_recruiterflow_job_snapshot"
    ) as mock_persist:
        mock_persist.return_value = {"job_id": "job-uuid"}
        summary = persist_recruiterflow_job(
            export_source_uri="/exports/Recruiterflow.zip",
            member_name="job/1.134.json",
            job_payload=_build_sample_job_payload(),
        )

    assert summary == {"job_id": "job-uuid"}
    mock_persist.assert_called_once()


def test_persist_recruiterflow_candidate_delegates_to_db_helper() -> None:
    """
    Verify that the Recruiterflow candidate service delegates the prepared payload to the DB helper.
    """

    with patch(
        "backend.services.recruiterflow_import.persist_recruiterflow_candidate_snapshot"
    ) as mock_persist:
        mock_persist.return_value = {"candidate_id": "candidate-uuid"}
        summary = persist_recruiterflow_candidate(
            export_source_uri="/exports/Recruiterflow.zip",
            member_name="candidate/1.100.json",
            candidate_payload=_build_sample_candidate_payload(),
        )

    assert summary == {"candidate_id": "candidate-uuid"}
    mock_persist.assert_called_once()


def test_persist_recruiterflow_job_file_reference_delegates_to_db_helper() -> None:
    """
    Verify that the job-file service delegates the prepared payload to the DB helper.
    """

    job_payload = {
        **_build_sample_job_payload(),
        "files": [
            {
                "file_id": 9001,
                "filename": "Job brief.pdf",
                "link": "https://example.com/job-brief.pdf",
            }
        ],
    }
    file_payload = job_payload["files"][0]
    assert isinstance(file_payload, dict)

    with patch(
        "backend.services.recruiterflow_import.persist_recruiterflow_job_file_reference_snapshot"
    ) as mock_persist:
        mock_persist.return_value = {"document_id": "document-uuid"}
        summary = persist_recruiterflow_job_file_reference(
            export_source_uri="/exports/Recruiterflow.zip",
            member_name="job/1.134.json",
            job_payload=job_payload,
            file_payload=file_payload,
        )

    assert summary == {"document_id": "document-uuid"}
    mock_persist.assert_called_once()

