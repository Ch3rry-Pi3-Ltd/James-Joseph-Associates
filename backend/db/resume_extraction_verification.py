"""
Database read helpers for verifying persisted resume-extraction writes.

This module sits beside the narrow accepted-output persistence helper and gives
the rest of the repository a stable way to inspect what the persistence slice
actually wrote into the canonical schema.

It answers a different question from the write path:

    "After we persisted one accepted JobAdder extraction result, what canonical
    rows and provenance links now exist in Postgres?"

Why this module exists
----------------------
The project now has a working first write path for accepted JobAdder CV
ingests. That means the next operational concern is no longer only:

    "Can we write?"

It is also:

    "Can we verify what was written before we bulk-load a larger dataset?"

This module provides the narrow read-side snapshot used by that verification
step.

Important scope boundary
------------------------
This is not a generic reporting layer and it is not the final ingestion
observability system.

It currently focuses only on the canonical entities and link tables written by
the first accepted-output persistence slice:

- people
- candidates
- companies
- documents
- source records
- source-record links
- document links
- candidate skills

Example
-------
Typical verification usage looks like:

    from backend.db.resume_extraction_verification import (
        get_resume_extraction_persistence_snapshot,
    )

    snapshot = get_resume_extraction_persistence_snapshot(
        candidate_id="candidate-uuid",
        person_id="person-uuid",
        document_id="document-uuid",
        extraction_source_record_id="source-uuid",
    )

    print(snapshot["candidate_profile"]["full_name"])
    print(len(snapshot["candidate_skills"]))
"""

from __future__ import annotations

from typing import Any

from backend.db.candidates import get_candidate_profile
from backend.db.connection import postgres_connection
from backend.db.skills import get_candidate_skills


def get_resume_extraction_persistence_snapshot(
    *,
    candidate_id: str,
    person_id: str | None = None,
    current_company_id: str | None = None,
    document_id: str | None = None,
    candidate_source_record_id: str | None = None,
    resume_source_record_id: str | None = None,
    extraction_source_record_id: str | None = None,
) -> dict[str, Any]:
    """
    Return the persisted canonical snapshot for one accepted extraction write.

    Parameters
    ----------
    candidate_id : str
        Canonical candidate UUID that should exist after persistence.

    person_id : str | None
        Expected canonical person UUID when known.

    current_company_id : str | None
        Expected canonical company UUID when known.

    document_id : str | None
        Expected canonical resume-document UUID when known.

    candidate_source_record_id : str | None
        Expected source-record UUID for the candidate snapshot.

    resume_source_record_id : str | None
        Expected source-record UUID for the selected resume attachment.

    extraction_source_record_id : str | None
        Expected source-record UUID for the accepted structured extraction.

    Returns
    -------
    dict[str, Any]
        Dictionary containing the persisted canonical snapshot and the
        provenance/link rows needed for higher-level verification.

    Notes
    -----
    This helper prefers explicit expected IDs when available because
    verification is stronger when it can answer:

    - did the candidate row exist?
    - did the expected person/company/document rows exist?
    - did the expected source-record rows exist?
    - did the expected links get created?

    It still returns a useful partial snapshot when some optional IDs are not
    supplied.

    Example
    -------
    A caller can inspect a persisted run by passing the canonical IDs returned
    from the write summary:

        snapshot = get_resume_extraction_persistence_snapshot(
            candidate_id="candidate-uuid",
            person_id="person-uuid",
            document_id="document-uuid",
            candidate_source_record_id="source-1",
            extraction_source_record_id="source-2",
        )
    """

    candidate_profile = get_candidate_profile(candidate_id)
    candidate_skills = get_candidate_skills(candidate_id)

    expected_source_record_ids = [
        source_record_id
        for source_record_id in (
            candidate_source_record_id,
            resume_source_record_id,
            extraction_source_record_id,
        )
        if source_record_id is not None
    ]

    with postgres_connection() as connection:
        with connection.cursor() as cursor:
            current_company = _fetch_optional_row_by_id(
                cursor,
                table_name="companies",
                row_id=current_company_id,
            )
            resume_document = _fetch_optional_row_by_id(
                cursor,
                table_name="documents",
                row_id=document_id,
            )
            source_records = _fetch_source_records_by_ids(
                cursor,
                source_record_ids=expected_source_record_ids,
            )
            source_record_links = _fetch_source_record_links(
                cursor,
                source_record_ids=expected_source_record_ids,
            )
            document_links = _fetch_document_links(
                cursor,
                document_id=document_id,
            )

    return {
        "candidate_profile": candidate_profile,
        "candidate_skills": candidate_skills,
        "current_company": current_company,
        "resume_document": resume_document,
        "source_records": source_records,
        "source_record_links": source_record_links,
        "document_links": document_links,
        "expected_ids": {
            "candidate_id": candidate_id,
            "person_id": person_id,
            "current_company_id": current_company_id,
            "document_id": document_id,
            "candidate_source_record_id": candidate_source_record_id,
            "resume_source_record_id": resume_source_record_id,
            "extraction_source_record_id": extraction_source_record_id,
        },
    }


def _fetch_optional_row_by_id(
    cursor: Any,
    *,
    table_name: str,
    row_id: str | None,
) -> dict[str, Any] | None:
    """
    Return one row by ID from a small allowed verification table set.

    Notes
    -----
    The table name is still dynamic here, so we keep the allowed set explicit.
    This keeps the helper small and safe while avoiding repeated one-off query
    functions for the verification-only path.

    Example
    -------
    A call with:

        table_name="documents"
        row_id="document-uuid"

    returns the matching document row as a plain dict, or `None`.
    """

    if row_id is None:
        return None

    if table_name not in {"companies", "documents"}:
        raise ValueError(f"Unsupported verification table: {table_name}")

    cursor.execute(
        f"""
        select *
        from {table_name}
        where id = %(row_id)s
        limit 1
        """,
        {"row_id": row_id},
    )
    row = cursor.fetchone()
    return None if row is None else dict(row)


def _fetch_source_records_by_ids(
    cursor: Any,
    *,
    source_record_ids: list[str],
) -> list[dict[str, Any]]:
    """
    Return source-record rows for the supplied verification IDs.

    Example
    -------
    Passing the three expected source-record IDs from the persistence summary
    returns the matching candidate/resume/extraction source-record rows.
    """

    if not source_record_ids:
        return []

    cursor.execute(
        """
        select
            id,
            source_system,
            source_record_type,
            source_record_id,
            source_payload_hash,
            import_run_id,
            processed_at,
            sync_status
        from source_records
        where id = any(%(source_record_ids)s)
        order by source_record_type, source_record_id
        """,
        {"source_record_ids": source_record_ids},
    )
    return [dict(row) for row in cursor.fetchall()]


def _fetch_source_record_links(
    cursor: Any,
    *,
    source_record_ids: list[str],
) -> list[dict[str, Any]]:
    """
    Return source-record links for the supplied verification IDs.

    Notes
    -----
    Verification cares about the actual link rows, not only whether the target
    entities exist. This helper therefore returns the matching link rows rather
    than collapsing them to counts too early.
    """

    if not source_record_ids:
        return []

    cursor.execute(
        """
        select
            id,
            source_record_id,
            person_id,
            candidate_id,
            company_id,
            document_id,
            linked_at
        from source_record_links
        where source_record_id = any(%(source_record_ids)s)
        order by source_record_id, linked_at
        """,
        {"source_record_ids": source_record_ids},
    )
    return [dict(row) for row in cursor.fetchall()]


def _fetch_document_links(
    cursor: Any,
    *,
    document_id: str | None,
) -> list[dict[str, Any]]:
    """
    Return document-link rows for the persisted resume document when present.

    Example
    -------
    A persisted resume document should usually produce at least:

        - one candidate resume link
        - one person resume link
    """

    if document_id is None:
        return []

    cursor.execute(
        """
        select
            id,
            document_id,
            person_id,
            candidate_id,
            source_record_id,
            relationship_type,
            created_at
        from document_links
        where document_id = %(document_id)s
        order by relationship_type, created_at
        """,
        {"document_id": document_id},
    )
    return [dict(row) for row in cursor.fetchall()]


__all__ = [
    "get_resume_extraction_persistence_snapshot",
]
