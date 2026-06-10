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
    _combine_reconciliation_decisions,
    _find_document_linked_entity_id,
    _find_existing_resume_document_id,
    _refresh_current_resume_links,
    _resolve_person_reconciliation,
    _upsert_candidate_with_reconciliation,
    _upsert_reconciliation_decision,
    _upsert_person,
    _upsert_resume_document,
    find_existing_resume_content_match,
    persist_dropbox_duplicate_resume_snapshot,
    persist_jobadder_candidate_profile_snapshot,
    persist_resume_extraction_snapshot,
)


def test_persist_resume_extraction_snapshot_commits_and_returns_summary() -> None:
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
        "source_system": "jobadder",
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
    mock_cursor.fetchone.side_effect = iter(
        [
            {"id": source_record_uuid},
            None,
            {"id": extraction_source_record_uuid},
        ]
        + [None] * 12
    )

    mock_connection = MagicMock()
    mock_connection.cursor.return_value.__enter__.return_value = mock_cursor

    with patch(
        "backend.db.resume_extraction_persistence.postgres_connection"
    ) as mock_postgres_connection, patch(
        "backend.db.resume_extraction_persistence._refresh_candidate_note_interactions"
    ) as mock_refresh_note_interactions, patch(
        "backend.db.resume_extraction_persistence._upsert_person_with_reconciliation",
        return_value=(
            person_uuid,
            {
                "decision_status": "created_new",
                "decision_reason": "no_existing_person_match",
                "confidence": 0.2,
            },
        ),
    ), patch(
        "backend.db.resume_extraction_persistence._upsert_candidate_with_reconciliation",
        return_value=(
            candidate_uuid,
            {
                "decision_status": "created_new",
                "decision_reason": "no_existing_candidate_match",
                "confidence": 0.2,
            },
        ),
    ), patch(
        "backend.db.resume_extraction_persistence._upsert_reconciliation_decision",
        return_value={"id": "rec-1", "decision_status": "created_new"},
    ):
        mock_postgres_connection.return_value.__enter__.return_value = (
            mock_connection
        )
        mock_refresh_note_interactions.return_value = ["interaction-1"]

        summary = persist_resume_extraction_snapshot(persistence_payload)

    assert summary["person_id"] == str(person_uuid)
    assert summary["candidate_id"] == str(candidate_uuid)
    assert summary["candidate_source_record_id"] == str(source_record_uuid)
    assert (
        summary["extraction_source_record_id"] == str(extraction_source_record_uuid)
    )
    assert summary["resume_source_record_id"] is None
    assert summary["document_id"] is None
    assert summary["candidate_skill_count"] == 0
    assert summary["candidate_note_interaction_count"] == 1
    assert summary["reconciliation_decision_id"] == "rec-1"
    assert summary["reconciliation_status"] == "created_new"
    assert isinstance(summary["person_id"], str)
    assert isinstance(summary["candidate_id"], str)
    mock_connection.commit.assert_called_once()


def test_find_existing_resume_document_id_prefers_content_hash_match() -> None:
    """
    Verify that resume dedupe falls back to content hash when no source link exists.
    """

    mock_cursor = MagicMock()
    document_uuid = uuid4()
    mock_cursor.fetchone.side_effect = [{"id": document_uuid}]

    document_id = _find_existing_resume_document_id(
        mock_cursor,
        source_record_id=None,
        content_hash="resume-content-hash",
    )

    assert document_id == document_uuid


def test_find_document_linked_entity_id_reads_existing_candidate_link() -> None:
    """
    Verify that a resume document can resolve back to an existing candidate.
    """

    mock_cursor = MagicMock()
    candidate_uuid = uuid4()
    mock_cursor.fetchone.return_value = {"candidate_id": candidate_uuid}

    candidate_id = _find_document_linked_entity_id(
        mock_cursor,
        document_id="document-uuid",
        entity_column="candidate_id",
    )

    assert candidate_id == candidate_uuid


def test_find_existing_resume_content_match_returns_linked_resume_identity() -> None:
    """
    Verify that content-hash lookup can resolve back to canonical IDs.
    """

    document_uuid = uuid4()
    person_uuid = uuid4()
    candidate_uuid = uuid4()

    with patch(
        "backend.db.resume_extraction_persistence.postgres_connection"
    ) as mock_postgres_connection, patch(
        "backend.db.resume_extraction_persistence._find_document_quality_assessment",
        return_value={"quality_status": "pass", "quality_score": 96},
    ):
        mock_cursor = MagicMock()
        mock_cursor.fetchone.side_effect = [
            {"id": document_uuid},
            {"person_id": person_uuid},
            {"candidate_id": candidate_uuid},
            {
                "id": document_uuid,
                "title": "Jane-Doe-CV.pdf",
                "resume_updated_at": "2026-05-11T12:00:00Z",
            },
        ]
        mock_connection = MagicMock()
        mock_connection.cursor.return_value.__enter__.return_value = mock_cursor
        mock_postgres_connection.return_value.__enter__.return_value = (
            mock_connection
        )

        match = find_existing_resume_content_match(content_hash="resume-hash")

    assert match == {
        "document_id": str(document_uuid),
        "document_title": "Jane-Doe-CV.pdf",
        "resume_updated_at": "2026-05-11T12:00:00Z",
        "person_id": str(person_uuid),
        "candidate_id": str(candidate_uuid),
        "quality_status": "pass",
        "quality_score": 96,
    }


def test_upsert_resume_document_persists_resume_updated_at() -> None:
    """
    Verify that canonical resume documents keep the upstream resume timestamp.
    """

    mock_cursor = MagicMock()
    document_uuid = uuid4()
    mock_cursor.fetchone.side_effect = [None, None, {"id": document_uuid}]

    document_id = _upsert_resume_document(
        mock_cursor,
        source_record_id="resume-source-1",
        resume_title="Roger-Campbell-CV.pdf",
        resume_updated_at="2026-05-11T12:00:00Z",
        mime_type="application/pdf",
        source_uri="dropbox://resume.pdf",
        content_hash="resume-content-hash",
        extracted_text="Resume body",
    )

    assert document_id == document_uuid
    insert_sql = mock_cursor.execute.call_args_list[2].args[0]
    insert_payload = mock_cursor.execute.call_args_list[2].args[1]
    assert "resume_updated_at" in insert_sql
    assert insert_payload["resume_updated_at"] == "2026-05-11T12:00:00Z"


def test_upsert_candidate_with_reconciliation_keeps_latest_resume_timestamp() -> None:
    """
    Verify that candidate resume timestamps never move backwards.
    """

    mock_cursor = MagicMock()

    with patch(
        "backend.db.resume_extraction_persistence._resolve_candidate_reconciliation",
        return_value={
            "decision_status": "auto_matched",
            "decision_reason": "person_unique_candidate",
            "confidence": 0.95,
            "matched_candidate_id": "candidate-1",
        },
    ):
        candidate_id, resolution = _upsert_candidate_with_reconciliation(
            mock_cursor,
            source_record_id="source-record-1",
            person_id="person-1",
            current_title="Software Engineer",
            current_company_id=None,
            candidate_status="Active",
            availability_status=None,
            last_contacted_at=None,
            resume_updated_at="2026-05-11T12:00:00Z",
        )

    assert candidate_id == "candidate-1"
    assert resolution["decision_status"] == "auto_matched"
    update_sql = mock_cursor.execute.call_args.args[0]
    assert "greatest(%(resume_updated_at)s::timestamptz, resume_updated_at)" in update_sql


def test_refresh_current_resume_links_prefers_latest_document() -> None:
    """
    Verify that the newest known resume document becomes `current_resume`.
    """

    mock_cursor = MagicMock()
    mock_cursor.fetchone.side_effect = [
        {"document_id": "document-new"},
        None,
        None,
    ]

    current_document_id = _refresh_current_resume_links(
        mock_cursor,
        candidate_id="candidate-1",
        person_id="person-1",
        source_record_id="resume-source-1",
    )

    assert current_document_id == "document-new"
    executed_sql = "\n".join(
        str(call.args[0]) for call in mock_cursor.execute.call_args_list
    )
    assert "relationship_type = 'current_resume'" in executed_sql
    assert "delete from document_links" in executed_sql


def test_upsert_person_reuses_primary_phone_match() -> None:
    """
    Verify that phone match can reuse an existing canonical person row.
    """

    mock_cursor = MagicMock()
    person_uuid = uuid4()
    mock_cursor.fetchone.side_effect = [None]
    mock_cursor.fetchall.side_effect = [
        [],  # no email match
        [{"id": person_uuid}],  # phone match
    ]

    person_id = _upsert_person(
        mock_cursor,
        source_record_id="source-record-1",
        full_name="Roger Campbell",
        first_name="Roger",
        last_name="Campbell",
        primary_email="roger@example.com",
        primary_phone="+447700900111",
        linkedin_url=None,
        location="London",
        headline="Software Engineer",
        summary="Builds backend systems.",
    )

    assert person_id == person_uuid


def test_resolve_person_reconciliation_marks_ambiguous_email_for_review() -> None:
    """
    Verify that duplicate email matches are recorded as review-needed.
    """

    mock_cursor = MagicMock()
    first_person_uuid = uuid4()
    second_person_uuid = uuid4()
    mock_cursor.fetchone.side_effect = [None]
    mock_cursor.fetchall.side_effect = [
        [{"id": first_person_uuid}, {"id": second_person_uuid}],
    ]

    resolution = _resolve_person_reconciliation(
        mock_cursor,
        source_record_id="source-record-1",
        preferred_person_id=None,
        linkedin_url=None,
        primary_email="roger@example.com",
        primary_phone=None,
    )

    assert resolution["decision_status"] == "needs_review"
    assert resolution["decision_reason"] == "ambiguous_primary_email_match"
    assert resolution["matched_person_id"] is None
    assert resolution["evidence_payload"]["matched_person_ids"] == [
        str(first_person_uuid),
        str(second_person_uuid),
    ]


def test_combine_reconciliation_decisions_prioritises_review_status() -> None:
    """
    Verify that unresolved entity evidence wins at the combined decision layer.
    """

    combined = _combine_reconciliation_decisions(
        person_reconciliation={
            "decision_status": "needs_review",
            "decision_reason": "ambiguous_primary_email_match",
            "confidence": 0.55,
        },
        candidate_reconciliation={
            "decision_status": "created_new",
            "decision_reason": "no_existing_candidate_match",
            "confidence": 0.2,
        },
    )

    assert combined["decision_status"] == "needs_review"
    assert combined["decision_reason"] == "ambiguous_primary_email_match"
    assert combined["confidence"] == 0.2


def test_upsert_reconciliation_decision_normalises_uuid_evidence_payload() -> None:
    """
    Verify that reconciliation evidence is JSON-safe before it reaches `Jsonb`.
    """

    mock_cursor = MagicMock()
    mock_cursor.fetchone.return_value = {
        "id": "decision-1",
        "decision_status": "auto_matched",
    }
    matched_person_uuid = uuid4()
    matched_candidate_uuid = uuid4()

    result = _upsert_reconciliation_decision(
        mock_cursor,
        source_record_id="source-record-1",
        document_id="document-1",
        person_id="person-1",
        candidate_id="candidate-1",
        person_reconciliation={
            "decision_status": "auto_matched",
            "decision_reason": "email_exact_match",
            "confidence": 0.95,
            "matched_person_id": matched_person_uuid,
            "evidence_payload": {
                "matched_person_ids": [matched_person_uuid],
            },
        },
        candidate_reconciliation={
            "decision_status": "auto_matched",
            "decision_reason": "person_unique_candidate",
            "confidence": 0.94,
            "matched_candidate_id": matched_candidate_uuid,
            "evidence_payload": {
                "matched_candidate_ids": [matched_candidate_uuid],
            },
        },
    )

    execute_payload = mock_cursor.execute.call_args.args[1]
    evidence_payload = execute_payload["evidence_payload"].obj
    assert evidence_payload["person_reconciliation"]["matched_person_id"] == str(
        matched_person_uuid
    )
    assert evidence_payload["candidate_reconciliation"]["matched_candidate_id"] == str(
        matched_candidate_uuid
    )
    assert evidence_payload["person_reconciliation"]["evidence_payload"] == {
        "matched_person_ids": [str(matched_person_uuid)]
    }
    assert evidence_payload["candidate_reconciliation"]["evidence_payload"] == {
        "matched_candidate_ids": [str(matched_candidate_uuid)]
    }
    assert result == {"id": "decision-1", "decision_status": "auto_matched"}


def test_persist_jobadder_candidate_profile_snapshot_commits_and_returns_summary() -> None:
    """
    Verify that the profile-only persistence helper commits and returns JSON-safe IDs.

    Notes
    -----
    This path is narrower than the accepted CV flow:

    - no resume document
    - no extraction source record
    - no candidate skills

    It still needs to upsert the source rows, person, candidate, and the
    provenance links that explain why the candidate exists canonically.

    Example
    -------
    The returned summary should expose both:

        - `profile_source_record_id`
        - verifier-compatible `extraction_source_record_id`

    as strings.
    """

    persistence_payload = {
        "source_candidate_id": 13812978,
        "candidate_source_payload": {"candidate": {"firstName": "Roger"}},
        "candidate_source_payload_hash": "candidate-hash",
        "profile_source_payload": {
            "persistence_reason": "no_resume_attachment",
        },
        "profile_source_payload_hash": "profile-hash",
        "profile_persistence_reason": "no_resume_attachment",
        "import_run_id": "run-456",
        "current_employer": None,
        "full_name": "Roger Campbell",
        "first_name": "Roger",
        "last_name": "Campbell",
        "primary_email": "roger@example.com",
        "primary_phone": "+447700900111",
        "linkedin_url": None,
        "location": "London",
        "headline": None,
        "summary": None,
        "candidate_status": "Active",
        "availability_status": None,
        "current_title": None,
        "last_contacted_at": "2026-05-13T10:30:00Z",
        "resume_updated_at": None,
    }

    mock_cursor = MagicMock()
    person_uuid = uuid4()
    candidate_uuid = uuid4()
    candidate_source_record_uuid = uuid4()
    profile_source_record_uuid = uuid4()
    mock_cursor.fetchone.side_effect = iter(
        [
            {"id": candidate_source_record_uuid},
            {"id": profile_source_record_uuid},
        ]
        + [None] * 10
    )

    mock_connection = MagicMock()
    mock_connection.cursor.return_value.__enter__.return_value = mock_cursor

    with patch(
        "backend.db.resume_extraction_persistence.postgres_connection"
    ) as mock_postgres_connection, patch(
        "backend.db.resume_extraction_persistence._refresh_candidate_note_interactions"
    ) as mock_refresh_note_interactions, patch(
        "backend.db.resume_extraction_persistence._upsert_person_with_reconciliation",
        return_value=(
            person_uuid,
            {
                "decision_status": "created_new",
                "decision_reason": "no_existing_person_match",
                "confidence": 0.2,
            },
        ),
    ), patch(
        "backend.db.resume_extraction_persistence._upsert_candidate_with_reconciliation",
        return_value=(
            candidate_uuid,
            {
                "decision_status": "created_new",
                "decision_reason": "no_existing_candidate_match",
                "confidence": 0.2,
            },
        ),
    ), patch(
        "backend.db.resume_extraction_persistence._upsert_reconciliation_decision",
        return_value={"id": "rec-2", "decision_status": "created_new"},
    ):
        mock_postgres_connection.return_value.__enter__.return_value = (
            mock_connection
        )
        mock_refresh_note_interactions.return_value = ["interaction-1", "interaction-2"]

        summary = persist_jobadder_candidate_profile_snapshot(persistence_payload)

    assert summary["person_id"] == str(person_uuid)
    assert summary["candidate_id"] == str(candidate_uuid)
    assert (
        summary["candidate_source_record_id"] == str(candidate_source_record_uuid)
    )
    assert summary["profile_source_record_id"] == str(profile_source_record_uuid)
    assert summary["extraction_source_record_id"] == str(profile_source_record_uuid)
    assert summary["document_id"] is None
    assert summary["candidate_skill_count"] == 0
    assert summary["candidate_note_interaction_count"] == 2
    assert summary["reconciliation_decision_id"] == "rec-2"
    assert summary["reconciliation_status"] == "created_new"
    assert summary["quality_status"] == "profile_only"
    mock_connection.commit.assert_called_once()


def test_persist_dropbox_duplicate_resume_snapshot_commits_and_returns_summary() -> None:
    """
    Verify that Dropbox duplicate reuse writes provenance and reuses canonical IDs.
    """

    persistence_payload = {
        "source_candidate_id": "/folder/Jane-Doe-CV.pdf",
        "candidate_source_payload": {"candidate_context": {"full_name": "Jane Doe"}},
        "candidate_source_payload_hash": "candidate-hash",
        "resume_source_payload": {"latest_resume": {"file_name": "Jane-Doe-CV.pdf"}},
        "resume_source_payload_hash": "resume-hash",
        "extraction_source_payload": {"llm_extraction_skipped": True},
        "extraction_source_payload_hash": "extraction-hash",
        "import_run_id": "run-789",
        "quality_status": "pass",
        "quality_score": 96,
        "matched_person_id": "person-uuid",
        "matched_candidate_id": "candidate-uuid",
        "matched_document_id": "document-uuid",
        "latest_resume": {
            "file_name": "Jane-Doe-CV.pdf",
            "mime_type": "application/pdf",
        },
        "resume_updated_at": "2026-05-11T12:00:00Z",
        "resume_source_uri": "dropbox:///folder/Jane-Doe-CV.pdf#candidate=/folder/Jane-Doe-CV.pdf&attachment=/folder/Jane-Doe-CV.pdf",
        "resume_content_hash": "resume-content-hash",
        "cleaned_resume_text": "Jane Doe CV body text",
    }

    mock_cursor = MagicMock()
    candidate_source_record_uuid = uuid4()
    resume_source_record_uuid = uuid4()
    extraction_source_record_uuid = uuid4()
    mock_cursor.fetchone.side_effect = [
        {"id": candidate_source_record_uuid},
        {"id": resume_source_record_uuid},
        {"id": extraction_source_record_uuid},
    ]

    mock_connection = MagicMock()
    mock_connection.cursor.return_value.__enter__.return_value = mock_cursor

    with patch(
        "backend.db.resume_extraction_persistence.postgres_connection"
    ) as mock_postgres_connection, patch(
        "backend.db.resume_extraction_persistence._upsert_resume_document",
        return_value="document-uuid",
    ), patch(
        "backend.db.resume_extraction_persistence._ensure_source_record_link",
    ), patch(
        "backend.db.resume_extraction_persistence._ensure_document_link",
    ), patch(
        "backend.db.resume_extraction_persistence._refresh_current_resume_links",
        return_value="document-uuid",
    ), patch(
        "backend.db.resume_extraction_persistence._upsert_reconciliation_decision",
        return_value={"id": "rec-3", "decision_status": "auto_matched"},
    ):
        mock_postgres_connection.return_value.__enter__.return_value = (
            mock_connection
        )

        summary = persist_dropbox_duplicate_resume_snapshot(persistence_payload)

    assert summary["person_id"] == "person-uuid"
    assert summary["candidate_id"] == "candidate-uuid"
    assert summary["document_id"] == "document-uuid"
    assert summary["current_resume_document_id"] == "document-uuid"
    assert summary["candidate_source_record_id"] == str(candidate_source_record_uuid)
    assert summary["resume_source_record_id"] == str(resume_source_record_uuid)
    assert summary["extraction_source_record_id"] == str(extraction_source_record_uuid)
    assert summary["quality_status"] == "pass"
    assert summary["persistence_mode"] == "reused_existing_resume"
    mock_connection.commit.assert_called_once()
