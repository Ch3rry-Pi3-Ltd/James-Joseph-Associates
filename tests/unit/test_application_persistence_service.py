"""
Unit tests for application persistence service helpers.

This module tests the business-side persistence rules in
`backend.services.application_persistence`.

It gives the rest of the repository a stable way to check:

- the persistence payload keeps the important provenance material
- the `tw...` vacancy code is preserved
- the service delegates the final write to the lower-level DB helper

Keeping these tests at the service layer matters because the persistence rules
are not only about SQL correctness. They also define what we consider to be a
usable application/candidate source pair before anything becomes canonical
state.
"""

from unittest.mock import patch

from backend.services.application_persistence import (
    build_jobadder_application_persistence_payload,
    persist_jobadder_application_with_candidate,
)


def _build_sample_application_detail_response() -> dict[str, object]:
    """
    Return a small live-application-detail shape suitable for persistence tests.

    Example
    -------
    The default call returns a minimal `tw398` wrapper with:

    - a real-looking application ID
    - nested candidate and job IDs
    - `tw...` vacancy code in the title
    - one workflow stage and source field
    """

    return {
        "jobadder_account": 2236,
        "jobadder_instance": "eu2",
        "api_url": "https://eu2api.jobadder.com/v2/",
        "application_id": 12204918,
        "application": {
            "applicationId": 12204918,
            "jobTitle": "tw398 - KDB Developer",
            "job": {
                "jobId": 936462,
                "jobTitle": "tw398 - KDB Developer",
            },
            "candidate": {"candidateId": 17071060},
            "status": {
                "name": "Applied",
                "workflow": {
                    "stage": '"INBOX"= New-CV\'s - [So CVR them!]'
                },
            },
            "source": "Database",
            "createdAt": "2026-05-10T09:00:00Z",
        },
    }


def _build_sample_candidate_detail_response() -> dict[str, object]:
    """
    Return a small live-candidate-detail shape suitable for persistence tests.

    Example
    -------
    The returned payload mirrors the first narrow fields the persistence path
    cares about:

    - name
    - email
    - phone
    - LinkedIn
    - current role/employer
    """

    return {
        "jobadder_account": 2236,
        "jobadder_instance": "eu2",
        "api_url": "https://eu2api.jobadder.com/v2/",
        "candidate_id": 17071060,
        "candidate": {
            "candidateId": 17071060,
            "firstName": "Sanjeev",
            "lastName": "Sarda",
            "email": "sanjeev.sarda@gmail.com",
            "mobile": "+44(0)7912 071 369",
            "linkedinUrl": "https://linkedin.com/in/sanjeev-sarda",
            "status": {"name": "Active"},
            "employment": {
                "current": {
                    "position": "Senior Engineer",
                    "employer": "Freelancing, UpWork",
                }
            },
            "updatedAt": "2026-05-18T14:00:00Z",
        },
    }


def test_build_jobadder_application_persistence_payload_keeps_key_provenance() -> None:
    """
    Verify that the persistence payload keeps the important provenance slices.

    Notes
    -----
    The first application persistence path is intentionally narrow, but it
    still needs to preserve the source-side evidence that explains where the
    canonical update came from:

    - application detail
    - candidate detail
    - inferred `tw...` vacancy code
    - flattened application status decision
    """

    payload = build_jobadder_application_persistence_payload(
        jobadder_account=2236,
        application_detail_response=_build_sample_application_detail_response(),
        candidate_detail_response=_build_sample_candidate_detail_response(),
    )

    assert payload["source_system"] == "jobadder_application"
    assert payload["source_application_id"] == 12204918
    assert payload["source_candidate_id"] == 17071060
    assert payload["source_job_id"] == 936462
    assert payload["tw_code"] == "tw398"
    assert payload["full_name"] == "Sanjeev Sarda"
    assert payload["primary_email"] == "sanjeev.sarda@gmail.com"
    assert payload["primary_phone"] == "+44(0)7912 071 369"
    assert payload["current_title"] == "Senior Engineer"
    assert payload["current_employer"] == "Freelancing, UpWork"
    assert payload["application_status"] == '"INBOX"= New-CV\'s - [So CVR them!]'
    assert payload["source"] == "Database"
    assert payload["application_source_payload"]["source_job_id"] == 936462
    assert payload["candidate_source_payload"]["tw_code"] == "tw398"
    assert payload["candidate_source_payload_hash"]
    assert payload["application_source_payload_hash"]


def test_persist_jobadder_application_with_candidate_delegates_to_db_helper() -> None:
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
        "backend.services.application_persistence.persist_jobadder_application_snapshot"
    ) as mock_persist:
        mock_persist.return_value = {
            "candidate_id": "candidate-uuid",
            "application_id": "application-uuid",
        }

        summary = persist_jobadder_application_with_candidate(
            jobadder_account=2236,
            application_detail_response=_build_sample_application_detail_response(),
            candidate_detail_response=_build_sample_candidate_detail_response(),
        )

    assert summary == {
        "candidate_id": "candidate-uuid",
        "application_id": "application-uuid",
    }
    mock_persist.assert_called_once()
