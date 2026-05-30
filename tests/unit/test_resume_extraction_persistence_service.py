"""
Unit tests for resume-extraction persistence service helpers.

This module tests the business-side persistence rules in
`backend.services.resume_extraction_persistence`.

It gives the rest of the repository a stable way to check:

- scored extraction results are considered persistable
- the persistence payload keeps the key provenance material we care about
- the service delegates the final write to the lower-level DB helper

Keeping these tests at the service layer matters because the persistence rules
are not only about SQL correctness. They also define when a result is allowed
to become canonical state at all.
"""

from unittest.mock import patch

import pytest

from backend.services.resume_extraction_persistence import (
    build_jobadder_candidate_profile_persistence_payload,
    build_resume_extraction_persistence_payload,
    persist_jobadder_candidate_profile_without_resume,
    persist_accepted_resume_extraction_result,
    persist_scored_resume_extraction_result,
)


def _build_sample_result(*, quality_status: str = "pass") -> dict[str, object]:
    """
    Return a small accepted-result shape suitable for persistence tests.

    Example
    -------
    The default call returns a minimal `jobadder` result with:

    - one accepted quality assessment
    - one selected resume attachment
    - one cleaned recruiter note

    which is enough to exercise the service-side persistence rules without
    dragging in unrelated extraction detail.
    """

    return {
        "source_system": "jobadder",
        "source_candidate_id": 16496678,
        "jobadder_account": 2236,
        "model_profile": {
            "provider": "openai",
            "model_name": "gpt-4.1-mini",
            "purpose": "extraction",
            "temperature": 0.0,
            "max_output_tokens": 2200,
        },
        "prompt_truncation": {
            "any_truncation": False,
            "resume_was_truncated": False,
            "notes_were_truncated": False,
        },
        "extraction_input": {
            "candidate_context": {
                "first_name": "Roger",
                "last_name": "Campbell",
                "email": "roger@example.com",
                "mobile": "+447700900111",
                "location": None,
                "status": "Active",
            },
            "latest_resume": {
                "attachment_id": 12345,
                "file_name": "Roger-Campbell-CV.pdf",
                "mime_type": "application/pdf",
                "created_at": "2026-05-11T12:00:00Z",
            },
            "cleaned_resume_text": "Roger Campbell CV body text",
            "cleaned_candidate_notes": [
                {
                    "note_id": "abc",
                    "type": "Phone call",
                    "created_at": "2026-05-10T09:00:00Z",
                    "updated_at": "2026-05-10T10:00:00Z",
                    "cleaned_text": "Candidate is open to move.",
                }
            ],
            "prompt_input_metrics": {
                "resume_original_characters": 28,
                "resume_prompt_characters": 28,
                "resume_was_truncated": False,
                "available_note_count": 1,
                "prompt_note_count": 1,
                "available_note_characters": 27,
                "prompt_note_characters": 27,
                "notes_were_truncated": False,
            },
        },
        "structured_extraction": {
            "current_employer": "Ch3rry Pi3 Ltd",
            "current_title": "Software Engineer",
            "professional_summary": "Builds backend systems.",
            "location": "London",
            "emails": ["roger@example.com"],
            "phones": ["+447700900111"],
            "skills": ["Python", "SQL"],
            "tools_and_platforms": ["Postgres", "Supabase"],
            "linkedin_url": "https://www.linkedin.com/in/roger-campbell",
        },
        "quality_assessment": {
            "quality_score": 96,
            "status": quality_status,
            "reasons": [],
        },
        "cv_source_assessment": {
            "richness_score": 88,
            "richness_band": "rich",
            "reasons": [],
        },
        "quality_gate": {
            "enabled": True,
            "first_pass_model_name": "gpt-4.1-mini",
            "fallback_model_name": "gpt-4.1-mini",
            "fallback_invoked": False,
            "final_model_name": "gpt-4.1-mini",
        },
    }


def _build_profile_only_ingest_payload() -> dict[str, object]:
    """
    Return a small no-resume JobAdder ingest payload for profile-only tests.

    Example
    -------
    The returned payload keeps:

    - candidate identity/contact data
    - attachment counts showing no resume exists
    - cleaned recruiter notes

    while deliberately leaving `latest_resume` as `None`.
    """

    return {
        "source_system": "jobadder",
        "jobadder_account": 2236,
        "source_candidate_id": 13812978,
        "candidate": {
            "candidateId": 13812978,
            "firstName": "Roger",
            "lastName": "Campbell",
            "email": "roger@example.com",
            "mobile": "+447700900111",
            "status": "Active",
            "location": "London",
            "updatedAt": "2026-05-14T12:00:00Z",
        },
        "attachments": {
            "items": [],
            "attachment_count": 0,
            "resume_attachment_count": 0,
            "links": {},
        },
        "notes": {
            "items": [],
            "cleaned_items": [
                {
                    "note_id": "note-1",
                    "type": "Phone Call",
                    "created_at": "2026-05-13T09:00:00Z",
                    "updated_at": "2026-05-13T10:30:00Z",
                    "text": "Candidate open to new opportunities.",
                    "cleaned_text": "Candidate open to new opportunities.",
                }
            ],
            "note_count": 1,
            "total_count": 1,
            "links": {},
        },
        "latest_resume": None,
        "ingest_shell": {
            "core_identity": {
                "first_name": "Roger",
                "last_name": "Campbell",
                "email": "roger@example.com",
                "mobile": "+447700900111",
                "location": "London",
                "status": "Active",
            }
        },
    }


def test_build_resume_extraction_persistence_payload_keeps_key_provenance() -> None:
    """
    Verify that the persistence payload keeps the important provenance slices.

    Notes
    -----
    The first persistence path is intentionally narrow, but it still needs to
    preserve the source-side evidence that explains where the canonical update
    came from:

    - candidate snapshot
    - selected resume snapshot
    - cleaned recruiter notes
    - accepted structured extraction
    """

    result = _build_sample_result()

    payload = build_resume_extraction_persistence_payload(result)

    assert payload["source_system"] == "jobadder"
    assert payload["source_candidate_id"] == 16496678
    assert payload["full_name"] == "Roger Campbell"
    assert payload["primary_email"] == "roger@example.com"
    assert payload["resume_source_uri"] == (
        "jobadder://accounts/2236/candidates/16496678/attachments/12345"
    )
    assert payload["last_contacted_at"] == "2026-05-10T10:00:00Z"
    assert payload["candidate_source_payload"]["cleaned_candidate_notes"][0][
        "cleaned_text"
    ] == "Candidate is open to move."
    assert payload["resume_source_payload"]["resume_content_hash"]
    assert payload["extraction_source_payload"]["quality_assessment"]["status"] == "pass"


def test_build_resume_extraction_persistence_payload_strips_nul_bytes() -> None:
    """
    Verify that NUL bytes are removed before the persistence payload reaches
    Postgres-facing code.

    Example
    -------
    A source text or extracted field containing embedded ``\\x00`` should be
    sanitised once in the shared builder so every source path inherits the same
    DB-safe behaviour.
    """

    result = _build_sample_result()
    result["extraction_input"]["cleaned_resume_text"] = "Roger\x00 Campbell CV body\x00 text"
    result["structured_extraction"]["professional_summary"] = "Builds\x00 backend systems."
    result["extraction_input"]["cleaned_candidate_notes"][0]["cleaned_text"] = (
        "Candidate is\x00 open to move."
    )

    payload = build_resume_extraction_persistence_payload(result)

    assert payload["cleaned_resume_text"] == "Roger Campbell CV body text"
    assert payload["summary"] == "Builds backend systems."
    assert payload["candidate_source_payload"]["cleaned_candidate_notes"][0][
        "cleaned_text"
    ] == "Candidate is open to move."
    assert "\x00" not in payload["resume_source_payload"]["resume_content_hash"]


def test_persist_accepted_resume_extraction_result_rejects_non_pass_status() -> None:
    """
    Verify that non-pass results are blocked before any database write.

    Example
    -------
    A `review` result should still be blocked by the strict accepted-only helper.
    """

    result = _build_sample_result(quality_status="review")

    with pytest.raises(RuntimeError) as excinfo:
        persist_accepted_resume_extraction_result(result)

    assert "does not accept the current" in str(excinfo.value)


def test_persist_scored_resume_extraction_result_allows_review_status() -> None:
    """
    Verify that review-grade results still persist through the scored path.

    Example
    -------
    A `review` result should delegate to the DB helper so Tom can still see
    the CV and its quality score in the UI.
    """

    result = _build_sample_result(quality_status="review")

    with patch(
        "backend.services.resume_extraction_persistence.persist_resume_extraction_snapshot"
    ) as mock_persist:
        mock_persist.return_value = {
            "candidate_id": "candidate-uuid",
            "person_id": "person-uuid",
            "quality_status": "review",
        }

        persisted_summary = persist_scored_resume_extraction_result(result)

    assert persisted_summary == {
        "candidate_id": "candidate-uuid",
        "person_id": "person-uuid",
        "quality_status": "review",
    }
    mock_persist.assert_called_once()


def test_persist_scored_resume_extraction_result_rejects_missing_resume_artifact() -> None:
    """
    Verify that scored persistence refuses resume-like results without an artefact.

    Notes
    -----
    Resume extraction rows should only exist when a real selected resume file
    exists. Profile-only candidates belong on the separate no-resume path.
    """

    result = _build_sample_result(quality_status="review")
    result["extraction_input"]["latest_resume"]["attachment_id"] = None

    with pytest.raises(RuntimeError) as excinfo:
        persist_scored_resume_extraction_result(result)

    assert "real selected resume artefact" in str(excinfo.value)


def test_persist_accepted_resume_extraction_result_delegates_to_db_helper() -> None:
    """
    Verify that the service delegates accepted results to the DB helper.

    Notes
    -----
    This test intentionally stops at the service boundary. The SQL write logic
    is covered separately. Here we only want to prove that:

    - accepted results are allowed through
    - the prepared payload is handed to the lower layer
    - the DB helper's summary is passed back unchanged
    """

    result = _build_sample_result()

    with patch(
        "backend.services.resume_extraction_persistence.persist_resume_extraction_snapshot"
    ) as mock_persist:
        mock_persist.return_value = {
            "candidate_id": "candidate-uuid",
            "person_id": "person-uuid",
        }

        persisted_summary = persist_accepted_resume_extraction_result(result)

    assert persisted_summary == {
        "candidate_id": "candidate-uuid",
        "person_id": "person-uuid",
    }
    mock_persist.assert_called_once()


def test_build_jobadder_candidate_profile_persistence_payload_keeps_no_resume_provenance() -> None:
    """
    Verify that the profile-only payload keeps the source notes and no-resume reason.

    Notes
    -----
    This is the narrow business case Tom highlighted:

    - no usable CV exists
    - but the candidate/contact data still matters
    - and the source notes still need to survive into provenance
    """

    ingest_payload = _build_profile_only_ingest_payload()

    payload = build_jobadder_candidate_profile_persistence_payload(ingest_payload)

    assert payload["source_system"] == "jobadder"
    assert payload["source_candidate_id"] == 13812978
    assert payload["full_name"] == "Roger Campbell"
    assert payload["primary_email"] == "roger@example.com"
    assert payload["resume_updated_at"] is None
    assert payload["profile_persistence_reason"] == "no_resume_attachment"
    assert payload["profile_source_payload"]["persistence_reason"] == (
        "no_resume_attachment"
    )
    assert payload["candidate_source_payload"]["latest_resume"] is None
    assert payload["candidate_source_payload"]["notes"]["cleaned_items"][0][
        "cleaned_text"
    ] == "Candidate open to new opportunities."


def test_persist_jobadder_candidate_profile_without_resume_rejects_payload_with_resume() -> None:
    """
    Verify that the profile-only path refuses candidates that already have a resume.

    Example
    -------
    A payload with `latest_resume={"attachmentId": 12345}` should be routed
    through the normal CV extraction path, not the profile-only path.
    """

    ingest_payload = _build_profile_only_ingest_payload()
    ingest_payload["latest_resume"] = {"attachmentId": 12345}

    with pytest.raises(RuntimeError) as excinfo:
        persist_jobadder_candidate_profile_without_resume(ingest_payload)

    assert "without a selected resume attachment" in str(excinfo.value)


def test_persist_jobadder_candidate_profile_without_resume_delegates_to_db_helper() -> None:
    """
    Verify that a valid no-resume payload delegates to the DB helper unchanged.

    Notes
    -----
    This test stops at the service boundary for the same reason as the accepted
    CV tests above: here we are proving the business rule and delegation path,
    not re-testing the SQL write implementation.
    """

    ingest_payload = _build_profile_only_ingest_payload()

    with patch(
        "backend.services.resume_extraction_persistence.persist_jobadder_candidate_profile_snapshot"
    ) as mock_persist:
        mock_persist.return_value = {
            "candidate_id": "candidate-uuid",
            "person_id": "person-uuid",
            "profile_source_record_id": "profile-source-uuid",
        }

        persisted_summary = persist_jobadder_candidate_profile_without_resume(
            ingest_payload
        )

    assert persisted_summary == {
        "candidate_id": "candidate-uuid",
        "person_id": "person-uuid",
        "profile_source_record_id": "profile-source-uuid",
    }
    mock_persist.assert_called_once()
