"""
Unit tests for job/job-spec persistence service helpers.

This module tests the business-side persistence rules in
`backend.services.job_spec_persistence`.

It gives the rest of the repository a stable way to check:

- the persistence payload keeps the important provenance material
- the `tw...` vacancy code is preserved
- the service delegates the final write to the lower-level DB helper

Keeping these tests at the service layer matters because the persistence rules
are not only about SQL correctness. They also define what we consider to be a
usable job/job-spec source pair before anything becomes canonical state.
"""

from decimal import Decimal
from unittest.mock import patch

from backend.services.job_spec_persistence import (
    build_jobadder_job_spec_persistence_payload,
    persist_jobadder_job_with_dropbox_job_spec,
)


def _build_sample_job_detail_response() -> dict[str, object]:
    """
    Return a small live-job-detail shape suitable for persistence tests.

    Example
    -------
    The default call returns a minimal `tw398` JobAdder wrapper with:

    - a real-looking job ID
    - `tw...` vacancy code in the title
    - company, owner, salary, and description fields
    """

    return {
        "jobadder_account": 2236,
        "jobadder_instance": "eu2",
        "api_url": "https://eu2api.jobadder.com/v2/",
        "job_id": 936462,
        "job": {
            "jobId": 936462,
            "jobTitle": "tw398 - KDB Developer",
            "jobDescription": "<p>Senior KDB Developer</p>",
            "company": {"name": "B2C2"},
            "status": {"name": "Open"},
            "workType": {"name": "Permanent"},
            "workplaceType": {"name": "Hybrid"},
            "owner": {"firstName": "Tom", "lastName": "Owens"},
            "salary": {
                "rateLow": 125000,
                "rateHigh": 125000,
                "currency": "GBP",
            },
            "location": {"city": "London", "country": "United Kingdom"},
            "updatedAt": "2026-05-18T14:00:00Z",
        },
    }


def _build_sample_dropbox_job_spec_file() -> dict[str, object]:
    """
    Return a small Dropbox job-spec file payload for persistence tests.

    Example
    -------
    The returned payload mirrors the narrow script-side structure:

    - path
    - file name
    - MIME type
    - extracted text
    - extraction metrics
    """

    return {
        "path": (
            "/new dropbox/# DLV/LIVE JOBS - [Job Specs]/tw398 - B2C2 - "
            "KDB Developer x2/B2C2 - Snr. KDB Developer - London - 2026.pdf"
        ),
        "file_name": "B2C2 - Snr. KDB Developer - London - 2026.pdf",
        "content_type": "application/octet-stream",
        "byte_count": 196449,
        "file_metadata": {"size": 196449},
        "extractor": "pypdf",
        "character_count": 5561,
        "page_count": 4,
        "extracted_text": "Senior KDB Developer role text",
    }


def test_build_jobadder_job_spec_persistence_payload_keeps_key_provenance() -> None:
    """
    Verify that the persistence payload keeps the important provenance slices.

    Notes
    -----
    The first job/job-spec persistence path is intentionally narrow, but it
    still needs to preserve the source-side evidence that explains where the
    canonical update came from:

    - JobAdder job detail
    - Dropbox job-spec file metadata
    - extracted job-spec text
    - inferred `tw...` vacancy code
    """

    payload = build_jobadder_job_spec_persistence_payload(
        jobadder_account=2236,
        job_detail_response=_build_sample_job_detail_response(),
        dropbox_account_id="dbid:AAD6tG3lvKRz-MJoBoYeedYkauD7t5D4IB0",
        dropbox_job_spec_file=_build_sample_dropbox_job_spec_file(),
    )

    assert payload["source_system"] == "jobadder_dropbox_job_spec"
    assert payload["source_job_id"] == 936462
    assert payload["tw_code"] == "tw398"
    assert payload["company_name"] == "B2C2"
    assert payload["job_title"] == "tw398 - KDB Developer"
    assert payload["job_location"] == "London, United Kingdom"
    assert payload["owner_name"] == "Tom Owens"
    assert payload["salary_min"] == Decimal("125000")
    assert payload["salary_max"] == Decimal("125000")
    assert payload["currency"] == "GBP"
    assert payload["job_source_payload"]["job_source_uri"] == (
        "jobadder://accounts/2236/jobs/936462"
    )
    assert payload["job_spec_title"] == "B2C2 - Snr. KDB Developer - London - 2026.pdf"
    assert payload["job_spec_extracted_text"] == "Senior KDB Developer role text"
    assert payload["job_source_payload_hash"]
    assert payload["job_spec_source_payload_hash"]


def test_persist_jobadder_job_with_dropbox_job_spec_delegates_to_db_helper() -> None:
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
        "backend.services.job_spec_persistence.persist_jobadder_job_spec_snapshot"
    ) as mock_persist:
        mock_persist.return_value = {
            "job_id": "job-uuid",
            "document_id": "document-uuid",
        }

        summary = persist_jobadder_job_with_dropbox_job_spec(
            jobadder_account=2236,
            job_detail_response=_build_sample_job_detail_response(),
            dropbox_account_id="dbid:AAD6tG3lvKRz-MJoBoYeedYkauD7t5D4IB0",
            dropbox_job_spec_file=_build_sample_dropbox_job_spec_file(),
        )

    assert summary == {
        "job_id": "job-uuid",
        "document_id": "document-uuid",
    }
    mock_persist.assert_called_once()
