"""
Unit tests for persisted resume-extraction verification helpers.

This module tests the service-side verification layer that checks whether the
first narrow accepted-output persistence slice actually landed in canonical
Postgres as expected.

It gives the rest of the repository a stable way to check:

- persistence summaries are validated before verification begins
- verification reports distinguish pass/fail checks explicitly
- optional company/document expectations are handled correctly
"""

from backend.services.resume_extraction_verification import (
    verify_persisted_resume_extraction_result,
)


def test_verify_persisted_resume_extraction_result_passes_for_matching_snapshot() -> None:
    """
    Verify that a matching canonical snapshot produces an all-pass report.

    Example
    -------
    When the DB snapshot contains the expected candidate, person, source
    records, links, document links, and skill count, the verification report
    should pass cleanly.
    """

    from unittest.mock import patch

    persistence_result = {
        "candidate_id": "candidate-uuid",
        "person_id": "person-uuid",
        "current_company_id": "company-uuid",
        "document_id": "document-uuid",
        "candidate_source_record_id": "source-candidate",
        "resume_source_record_id": "source-resume",
        "extraction_source_record_id": "source-extraction",
        "candidate_skill_count": 2,
    }

    snapshot = {
        "candidate_profile": {
            "candidate_id": "candidate-uuid",
            "person_id": "person-uuid",
        },
        "candidate_skills": [{"skill_id": "1"}, {"skill_id": "2"}],
        "current_company": {"id": "company-uuid"},
        "resume_document": {"id": "document-uuid"},
        "source_records": [
            {"id": "source-candidate"},
            {"id": "source-resume"},
            {"id": "source-extraction"},
        ],
        "source_record_links": [
            {"source_record_id": "source-candidate", "candidate_id": "candidate-uuid"},
            {"source_record_id": "source-candidate", "person_id": "person-uuid"},
            {"source_record_id": "source-extraction", "candidate_id": "candidate-uuid"},
            {"source_record_id": "source-extraction", "person_id": "person-uuid"},
            {"source_record_id": "source-extraction", "company_id": "company-uuid"},
            {"source_record_id": "source-extraction", "document_id": "document-uuid"},
        ],
        "document_links": [
            {"candidate_id": "candidate-uuid"},
            {"person_id": "person-uuid"},
        ],
        "expected_ids": {},
    }

    with patch(
        "backend.services.resume_extraction_verification.get_resume_extraction_persistence_snapshot",
        return_value=snapshot,
    ):
        report = verify_persisted_resume_extraction_result(
            persistence_result=persistence_result,
        )

    assert report.verification_passed is True
    assert report.failed_check_count == 0
    assert report.passed_check_count == len(report.checks)


def test_verify_persisted_resume_extraction_result_flags_missing_document_link() -> None:
    """
    Verify that a missing expected document/person link produces a failed check.

    Example
    -------
    A persistence summary that expects a resume document should fail
    verification when the candidate document link is missing from the snapshot.
    """

    from unittest.mock import patch

    persistence_result = {
        "candidate_id": "candidate-uuid",
        "person_id": "person-uuid",
        "document_id": "document-uuid",
        "candidate_source_record_id": "source-candidate",
        "resume_source_record_id": "source-resume",
        "extraction_source_record_id": "source-extraction",
    }

    snapshot = {
        "candidate_profile": {
            "candidate_id": "candidate-uuid",
            "person_id": "person-uuid",
        },
        "candidate_skills": [],
        "current_company": None,
        "resume_document": {"id": "document-uuid"},
        "source_records": [
            {"id": "source-candidate"},
            {"id": "source-resume"},
            {"id": "source-extraction"},
        ],
        "source_record_links": [
            {"source_record_id": "source-candidate", "candidate_id": "candidate-uuid"},
            {"source_record_id": "source-candidate", "person_id": "person-uuid"},
            {"source_record_id": "source-extraction", "candidate_id": "candidate-uuid"},
            {"source_record_id": "source-extraction", "person_id": "person-uuid"},
            {"source_record_id": "source-extraction", "document_id": "document-uuid"},
        ],
        "document_links": [
            {"person_id": "person-uuid"},
        ],
        "expected_ids": {},
    }

    with patch(
        "backend.services.resume_extraction_verification.get_resume_extraction_persistence_snapshot",
        return_value=snapshot,
    ):
        report = verify_persisted_resume_extraction_result(
            persistence_result=persistence_result,
        )

    assert report.verification_passed is False
    assert any(
        check.name == "document_link_candidate_exists" and not check.passed
        for check in report.checks
    )
