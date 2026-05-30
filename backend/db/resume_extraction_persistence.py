"""
Database helpers for persisting accepted resume-extraction results.

This module contains the first narrow write path for turning a successful
resume-extraction result into canonical Supabase/Postgres records.

It gives the rest of the repository a stable way to talk about:

- saving the accepted extraction result as provenance-bearing source records
- saving no-resume JobAdder candidate profiles as provenance-bearing source
  records
- upserting the linked person, candidate, company, and resume document rows
- refreshing candidate-skill links from the latest accepted extraction
- keeping direct SQL write logic out of scripts and service orchestration code

Why this module exists
----------------------
The extraction pipeline is now strong enough to produce repeatable accepted
results against real upstream candidate sources.

That changes the next question:

    "How do we persist the accepted result into the canonical schema without
    making the scripts own raw SQL and table-level rules?"

This module is the answer to that narrow question.

Important scope boundary
------------------------
This is intentionally not the full ingestion system.

It does not attempt to:

- define the final source-of-truth policy for every field
- explode recruiter notes into first-class interaction records yet
- persist every project or employment-history row into a fully modelled graph
- replace later API-level ingestion endpoints

Instead, it implements the smallest reliable persistence slices that are
already justified by the current extraction maturity:

- source records
- person
- candidate
- current company
- optional resume document
- optional candidate skills

Example
-------
Typical service usage looks like:

    from backend.db.resume_extraction_persistence import (
        persist_resume_extraction_snapshot,
    )

    summary = persist_resume_extraction_snapshot(
        persistence_payload,
    )

    print(summary["candidate_id"])
    print(summary["document_id"])
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal
from uuid import UUID

from psycopg import Cursor
from psycopg.types.json import Jsonb

from backend.db.connection import postgres_connection

SourceRecordType = Literal[
    "jobadder_candidate_snapshot",
    "jobadder_candidate_profile_only",
    "jobadder_resume_attachment",
    "jobadder_resume_extraction",
    "recruiterflow_candidate",
    "recruiterflow_resume_attachment",
    "recruiterflow_resume_extraction",
]


def persist_resume_extraction_snapshot(
    persistence_payload: dict[str, Any],
) -> dict[str, Any]:
    """
    Persist one accepted resume-extraction result.

    Parameters
    ----------
    persistence_payload : dict[str, Any]
        Normalised persistence payload prepared by the service layer.

        The payload should already contain:

        - candidate/source identifiers
        - extracted canonical fields
        - source snapshots for provenance
        - quality metadata proving the result was accepted

    Returns
    -------
    dict[str, Any]
        Small persistence summary containing the important canonical IDs and
        counts created or refreshed by the transaction.

    Notes
    -----
    This helper keeps the write path transaction-scoped and explicit.

    The transaction currently persists:

    - three provenance-bearing source records
    - one canonical person
    - one canonical candidate
    - zero or one current company
    - zero or one resume document
    - candidate-skill links derived from the accepted extraction

    The source records are intentionally split because they answer different
    provenance questions later:

    - what source-side candidate snapshot did we ingest?
    - which resume attachment did we use?
    - what accepted structured extraction did we derive from them?

    Example
    -------
    Persisting a prepared payload returns a summary such as:

        {
            "person_id": "...",
            "candidate_id": "...",
            "current_company_id": "...",
            "document_id": "...",
            "candidate_skill_count": 18,
        }
    """

    source_system = str(persistence_payload["source_system"])
    source_candidate_id = str(persistence_payload["source_candidate_id"])
    latest_resume = persistence_payload.get("latest_resume", {})
    latest_resume_attachment_id = latest_resume.get("attachment_id")
    latest_resume_attachment_key = (
        str(latest_resume_attachment_id)
        if latest_resume_attachment_id is not None
        else None
    )
    extraction_source_record_key = (
        f"{source_candidate_id}:{latest_resume_attachment_key or 'no-resume'}"
    )

    candidate_source_record_type = _get_candidate_source_record_type(
        source_system=source_system
    )
    resume_source_record_type = _get_resume_source_record_type(
        source_system=source_system
    )
    extraction_source_record_type = _get_extraction_source_record_type(
        source_system=source_system
    )

    persisted_at = datetime.now(timezone.utc)

    with postgres_connection() as connection:
        with connection.cursor() as cursor:
            # Keep the three provenance records separate even though they come
            # from one accepted extraction run.
            #
            # That split is deliberate. Later debugging and lineage questions
            # are easier to answer when we can point at:
            # - the upstream candidate snapshot
            # - the selected resume attachment
            # - the accepted structured extraction derived from them
            candidate_source_record = _upsert_source_record(
                cursor,
                source_system=source_system,
                source_record_type=candidate_source_record_type,
                source_record_id=source_candidate_id,
                source_payload=persistence_payload["candidate_source_payload"],
                source_payload_hash=persistence_payload[
                    "candidate_source_payload_hash"
                ],
                import_run_id=persistence_payload.get("import_run_id"),
                processed_at=persisted_at,
                sync_status="accepted",
            )

            resume_source_record: dict[str, Any] | None = None
            if latest_resume_attachment_key is not None:
                resume_source_record = _upsert_source_record(
                    cursor,
                    source_system=source_system,
                    source_record_type=resume_source_record_type,
                    source_record_id=latest_resume_attachment_key,
                    source_payload=persistence_payload["resume_source_payload"],
                    source_payload_hash=persistence_payload[
                        "resume_source_payload_hash"
                    ],
                    import_run_id=persistence_payload.get("import_run_id"),
                    processed_at=persisted_at,
                    sync_status="accepted",
                )

            existing_document_id = _find_existing_resume_document_id(
                cursor,
                source_record_id=(
                    resume_source_record["id"] if resume_source_record is not None else None
                ),
                content_hash=persistence_payload.get("resume_content_hash"),
            )
            preferred_person_id = _find_document_linked_entity_id(
                cursor,
                document_id=existing_document_id,
                entity_column="person_id",
            )
            preferred_candidate_id = _find_document_linked_entity_id(
                cursor,
                document_id=existing_document_id,
                entity_column="candidate_id",
            )

            extraction_source_record = _upsert_source_record(
                cursor,
                source_system=source_system,
                source_record_type=extraction_source_record_type,
                source_record_id=extraction_source_record_key,
                source_payload=persistence_payload["extraction_source_payload"],
                source_payload_hash=persistence_payload[
                    "extraction_source_payload_hash"
                ],
                import_run_id=persistence_payload.get("import_run_id"),
                processed_at=persisted_at,
                sync_status="accepted",
            )

            current_company_id = _upsert_company_by_name(
                cursor,
                company_name=persistence_payload.get("current_employer"),
            )

            # Link-or-create the canonical entities after the source records
            # exist so later link tables can tie both provenance and canonical
            # rows back to the same accepted extraction event.
            person_id, person_reconciliation = _upsert_person_with_reconciliation(
                cursor,
                source_record_id=candidate_source_record["id"],
                full_name=persistence_payload["full_name"],
                first_name=persistence_payload.get("first_name"),
                last_name=persistence_payload.get("last_name"),
                primary_email=persistence_payload.get("primary_email"),
                primary_phone=persistence_payload.get("primary_phone"),
                linkedin_url=persistence_payload.get("linkedin_url"),
                location=persistence_payload.get("location"),
                headline=persistence_payload.get("headline"),
                summary=persistence_payload.get("summary"),
                preferred_person_id=preferred_person_id,
            )

            candidate_id, candidate_reconciliation = _upsert_candidate_with_reconciliation(
                cursor,
                source_record_id=candidate_source_record["id"],
                person_id=person_id,
                current_title=persistence_payload.get("current_title"),
                current_company_id=current_company_id,
                candidate_status=persistence_payload.get("candidate_status"),
                availability_status=persistence_payload.get("availability_status"),
                last_contacted_at=persistence_payload.get("last_contacted_at"),
                resume_updated_at=persistence_payload.get("resume_updated_at"),
                preferred_candidate_id=preferred_candidate_id,
            )

            document_id: str | None = None
            if latest_resume_attachment_key is not None:
                document_id = _upsert_resume_document(
                    cursor,
                    source_record_id=resume_source_record["id"],
                    resume_title=(latest_resume or {}).get("file_name"),
                    mime_type=(latest_resume or {}).get("mime_type"),
                    source_uri=persistence_payload.get("resume_source_uri"),
                    content_hash=persistence_payload.get("resume_content_hash"),
                    extracted_text=persistence_payload.get("cleaned_resume_text"),
                    existing_document_id=existing_document_id,
                )

            # Keep one source-record link row per canonical target rather than
            # mixing several nullable foreign keys into one "wide" link row.
            # That makes the existence checks simple and the resulting lineage
            # much easier to inspect later.
            _ensure_source_record_link(
                cursor,
                source_record_id=candidate_source_record["id"],
                person_id=person_id,
            )
            _ensure_source_record_link(
                cursor,
                source_record_id=candidate_source_record["id"],
                candidate_id=candidate_id,
            )

            if resume_source_record is not None and document_id is not None:
                _ensure_source_record_link(
                    cursor,
                    source_record_id=resume_source_record["id"],
                    document_id=document_id,
                )
                _ensure_source_record_link(
                    cursor,
                    source_record_id=resume_source_record["id"],
                    person_id=person_id,
                )
                _ensure_source_record_link(
                    cursor,
                    source_record_id=resume_source_record["id"],
                    candidate_id=candidate_id,
                )

            _ensure_source_record_link(
                cursor,
                source_record_id=extraction_source_record["id"],
                person_id=person_id,
            )
            _ensure_source_record_link(
                cursor,
                source_record_id=extraction_source_record["id"],
                candidate_id=candidate_id,
            )
            if current_company_id is not None:
                _ensure_source_record_link(
                    cursor,
                    source_record_id=extraction_source_record["id"],
                    company_id=current_company_id,
                )
            if document_id is not None:
                _ensure_source_record_link(
                    cursor,
                    source_record_id=extraction_source_record["id"],
                    document_id=document_id,
                )

            if document_id is not None:
                # Document links answer a slightly different question from
                # source-record links:
                #
                # - source-record links explain provenance
                # - document links explain domain relationships
                #
                # We therefore write both when a selected resume document is
                # present.
                _ensure_document_link(
                    cursor,
                    document_id=document_id,
                    candidate_id=candidate_id,
                    relationship_type="resume",
                    source_record_id=resume_source_record["id"]
                    if resume_source_record is not None
                    else None,
                )
                _ensure_document_link(
                    cursor,
                    document_id=document_id,
                    person_id=person_id,
                    relationship_type="resume",
                    source_record_id=resume_source_record["id"]
                    if resume_source_record is not None
                    else None,
                )

            reconciliation_decision = _upsert_reconciliation_decision(
                cursor,
                source_record_id=extraction_source_record["id"],
                document_id=document_id,
                person_id=person_id,
                candidate_id=candidate_id,
                person_reconciliation=person_reconciliation,
                candidate_reconciliation=candidate_reconciliation,
            )

            linked_skill_ids = _refresh_candidate_skills(
                cursor,
                candidate_id=candidate_id,
                source_record_id=extraction_source_record["id"],
                extracted_skills=persistence_payload.get("skills", []),
                extracted_tools=persistence_payload.get("tools_and_platforms", []),
            )
            if source_system == "jobadder":
                note_interaction_ids = _refresh_candidate_note_interactions(
                    cursor,
                    candidate_id=candidate_id,
                    person_id=person_id,
                    cleaned_candidate_notes=persistence_payload.get(
                        "cleaned_candidate_notes", []
                    ),
                )
            else:
                note_interaction_ids = []

        connection.commit()

    return _make_json_safe_summary(
        {
            "persisted_at": persisted_at.isoformat(),
            "person_id": person_id,
            "candidate_id": candidate_id,
            "current_company_id": current_company_id,
            "document_id": document_id,
            "candidate_source_record_id": candidate_source_record["id"],
            "resume_source_record_id": (
                resume_source_record["id"] if resume_source_record is not None else None
            ),
            "extraction_source_record_id": extraction_source_record["id"],
            "candidate_skill_count": len(linked_skill_ids),
            "candidate_note_interaction_count": len(note_interaction_ids),
            "reconciliation_decision_id": reconciliation_decision["id"],
            "reconciliation_status": reconciliation_decision["decision_status"],
            "quality_status": persistence_payload.get("quality_status"),
        }
    )


def persist_jobadder_candidate_profile_snapshot(
    persistence_payload: dict[str, Any],
) -> dict[str, Any]:
    """
    Persist one JobAdder candidate as a profile-only canonical snapshot.

    Parameters
    ----------
    persistence_payload : dict[str, Any]
        Normalised profile-only payload prepared by the service layer.

    Returns
    -------
    dict[str, Any]
        Small persistence summary containing the canonical IDs and provenance
        rows written by the transaction.

    Notes
    -----
    This helper is the narrow answer to the business case where a candidate
    still matters even though JobAdder does not expose a usable resume
    attachment yet.

    The transaction currently persists:

    - one upstream candidate snapshot source record
    - one profile-only decision source record
    - one canonical person
    - one canonical candidate
    - zero or one current company

    It does not create:

    - resume documents
    - document links
    - candidate skills

    Example
    -------
    Persisting a prepared payload returns a summary such as:

        {
            "person_id": "...",
            "candidate_id": "...",
            "profile_source_record_id": "...",
            "document_id": None,
        }
    """

    source_candidate_id = str(persistence_payload["source_candidate_id"])
    persisted_at = datetime.now(timezone.utc)

    with postgres_connection() as connection:
        with connection.cursor() as cursor:
            candidate_source_record = _upsert_source_record(
                cursor,
                source_system="jobadder",
                source_record_type="jobadder_candidate_snapshot",
                source_record_id=source_candidate_id,
                source_payload=persistence_payload["candidate_source_payload"],
                source_payload_hash=persistence_payload[
                    "candidate_source_payload_hash"
                ],
                import_run_id=persistence_payload.get("import_run_id"),
                processed_at=persisted_at,
                sync_status="profile_only",
            )

            profile_source_record = _upsert_source_record(
                cursor,
                source_system="jobadder",
                source_record_type="jobadder_candidate_profile_only",
                source_record_id=f"{source_candidate_id}:no-resume",
                source_payload=persistence_payload["profile_source_payload"],
                source_payload_hash=persistence_payload["profile_source_payload_hash"],
                import_run_id=persistence_payload.get("import_run_id"),
                processed_at=persisted_at,
                sync_status="profile_only",
            )

            current_company_id = _upsert_company_by_name(
                cursor,
                company_name=persistence_payload.get("current_employer"),
            )

            # Preserve the same canonical person/candidate upsert rules as the
            # accepted CV path so a later resume-backed write can converge on
            # the same rows instead of fragmenting the candidate into two
            # parallel identities.
            person_id, person_reconciliation = _upsert_person_with_reconciliation(
                cursor,
                source_record_id=candidate_source_record["id"],
                full_name=persistence_payload["full_name"],
                first_name=persistence_payload.get("first_name"),
                last_name=persistence_payload.get("last_name"),
                primary_email=persistence_payload.get("primary_email"),
                primary_phone=persistence_payload.get("primary_phone"),
                linkedin_url=persistence_payload.get("linkedin_url"),
                location=persistence_payload.get("location"),
                headline=persistence_payload.get("headline"),
                summary=persistence_payload.get("summary"),
            )

            candidate_id, candidate_reconciliation = _upsert_candidate_with_reconciliation(
                cursor,
                source_record_id=candidate_source_record["id"],
                person_id=person_id,
                current_title=persistence_payload.get("current_title"),
                current_company_id=current_company_id,
                candidate_status=persistence_payload.get("candidate_status"),
                availability_status=persistence_payload.get("availability_status"),
                last_contacted_at=persistence_payload.get("last_contacted_at"),
                resume_updated_at=persistence_payload.get("resume_updated_at"),
            )

            _ensure_source_record_link(
                cursor,
                source_record_id=candidate_source_record["id"],
                person_id=person_id,
            )
            _ensure_source_record_link(
                cursor,
                source_record_id=candidate_source_record["id"],
                candidate_id=candidate_id,
            )
            _ensure_source_record_link(
                cursor,
                source_record_id=profile_source_record["id"],
                person_id=person_id,
            )
            _ensure_source_record_link(
                cursor,
                source_record_id=profile_source_record["id"],
                candidate_id=candidate_id,
            )
            if current_company_id is not None:
                _ensure_source_record_link(
                    cursor,
                    source_record_id=profile_source_record["id"],
                    company_id=current_company_id,
                )
            note_interaction_ids = _refresh_candidate_note_interactions(
                cursor,
                candidate_id=candidate_id,
                person_id=person_id,
                cleaned_candidate_notes=persistence_payload.get(
                    "cleaned_candidate_notes", []
                ),
            )
            reconciliation_decision = _upsert_reconciliation_decision(
                cursor,
                source_record_id=profile_source_record["id"],
                document_id=None,
                person_id=person_id,
                candidate_id=candidate_id,
                person_reconciliation=person_reconciliation,
                candidate_reconciliation=candidate_reconciliation,
            )

        connection.commit()

    return _make_json_safe_summary(
        {
            "persisted_at": persisted_at.isoformat(),
            "person_id": person_id,
            "candidate_id": candidate_id,
            "current_company_id": current_company_id,
            "document_id": None,
            "candidate_source_record_id": candidate_source_record["id"],
            "resume_source_record_id": None,
            # Keep the existing verifier-compatible alias alongside the more
            # honest `profile_source_record_id` name so operator tooling can
            # validate this narrower path without a second bespoke report
            # format.
            "profile_source_record_id": profile_source_record["id"],
            "extraction_source_record_id": profile_source_record["id"],
            "candidate_skill_count": 0,
            "candidate_note_interaction_count": len(note_interaction_ids),
            "reconciliation_decision_id": reconciliation_decision["id"],
            "reconciliation_status": reconciliation_decision["decision_status"],
            "quality_status": "profile_only",
            "profile_persistence_reason": persistence_payload.get(
                "profile_persistence_reason"
            ),
        }
    )


def _upsert_source_record(
    cursor: Cursor[Any],
    *,
    source_system: str,
    source_record_type: SourceRecordType,
    source_record_id: str,
    source_payload: dict[str, Any],
    source_payload_hash: str,
    import_run_id: str | None,
    processed_at: datetime,
    sync_status: str,
) -> dict[str, Any]:
    """
    Insert or replace one provenance-bearing source record row.

    Notes
    -----
    The unique natural key already exists in the schema:

    - `source_system`
    - `source_record_type`
    - `source_record_id`

    That makes `source_records` the right place to keep the latest accepted
    snapshot for each candidate / resume / extraction artefact without creating
    duplicate rows on every rerun.

    Example
    -------
    A call with:

        source_record_type="jobadder_resume_attachment"
        source_record_id="12345"

    updates the latest accepted resume-attachment snapshot for that upstream
    attachment key rather than inserting a duplicate row on every rerun.
    """

    cursor.execute(
        """
        insert into source_records (
            source_system,
            source_record_type,
            source_record_id,
            source_payload,
            source_payload_hash,
            import_run_id,
            processed_at,
            sync_status,
            error_message
        )
        values (
            %(source_system)s,
            %(source_record_type)s,
            %(source_record_id)s,
            %(source_payload)s,
            %(source_payload_hash)s,
            %(import_run_id)s,
            %(processed_at)s,
            %(sync_status)s,
            null
        )
        on conflict (source_system, source_record_type, source_record_id)
        do update set
            source_payload = excluded.source_payload,
            source_payload_hash = excluded.source_payload_hash,
            import_run_id = excluded.import_run_id,
            processed_at = excluded.processed_at,
            sync_status = excluded.sync_status,
            error_message = null
        returning id, source_system, source_record_type, source_record_id
        """,
        {
            "source_system": source_system,
            "source_record_type": source_record_type,
            "source_record_id": source_record_id,
            "source_payload": Jsonb(source_payload),
            "source_payload_hash": source_payload_hash,
            "import_run_id": import_run_id,
            "processed_at": processed_at,
            "sync_status": sync_status,
        },
    )
    row = cursor.fetchone()
    if row is None:
        raise RuntimeError("Failed to persist source_record row.")
    return dict(row)


def _get_candidate_source_record_type(*, source_system: str) -> SourceRecordType:
    """
    Return the candidate snapshot source-record type for one source system.

    Examples
    --------
    `jobadder` returns `jobadder_candidate_snapshot`, while `recruiterflow`
    returns `recruiterflow_candidate`.
    """

    if source_system == "jobadder":
        return "jobadder_candidate_snapshot"
    if source_system == "recruiterflow":
        return "recruiterflow_candidate"
    raise RuntimeError(f"Unsupported source system for candidate persistence: {source_system}")


def _get_resume_source_record_type(*, source_system: str) -> SourceRecordType:
    """
    Return the resume-attachment source-record type for one source system.
    """

    if source_system == "jobadder":
        return "jobadder_resume_attachment"
    if source_system == "recruiterflow":
        return "recruiterflow_resume_attachment"
    raise RuntimeError(f"Unsupported source system for resume persistence: {source_system}")


def _get_extraction_source_record_type(*, source_system: str) -> SourceRecordType:
    """
    Return the accepted extraction source-record type for one source system.
    """

    if source_system == "jobadder":
        return "jobadder_resume_extraction"
    if source_system == "recruiterflow":
        return "recruiterflow_resume_extraction"
    raise RuntimeError(f"Unsupported source system for extraction persistence: {source_system}")


def _upsert_company_by_name(
    cursor: Cursor[Any],
    *,
    company_name: str | None,
) -> str | None:
    """
    Find or create the current employer row by name.

    Notes
    -----
    This is deliberately narrow.

    We are only using the extracted current employer name at this stage because
    the richer company-identity policy still depends on wider source-system
    design work. Exact company modelling can become more sophisticated later
    without rewriting the rest of the persistence slice.

    Example
    -------
    A value such as:

        "NHS Practitioner Health"

    returns the existing `companies.id` for that case-insensitive name match,
    or creates one new row when no match exists yet.
    """

    if company_name is None or company_name.strip() == "":
        return None

    cleaned_name = company_name.strip()
    cursor.execute(
        """
        select id
        from companies
        where lower(name) = lower(%(name)s)
        limit 1
        """,
        {"name": cleaned_name},
    )
    row = cursor.fetchone()
    if row is not None:
        return row["id"]

    cursor.execute(
        """
        insert into companies (name)
        values (%(name)s)
        returning id
        """,
        {"name": cleaned_name},
    )
    inserted_row = cursor.fetchone()
    if inserted_row is None:
        raise RuntimeError("Failed to create company row.")
    return inserted_row["id"]


def _upsert_person(
    cursor: Cursor[Any],
    *,
    source_record_id: str,
    full_name: str,
    first_name: str | None,
    last_name: str | None,
    primary_email: str | None,
    primary_phone: str | None,
    linkedin_url: str | None,
    location: str | None,
    headline: str | None,
    summary: str | None,
    preferred_person_id: str | None = None,
) -> str:
    """
    Find or create the canonical person row for the candidate.

    Notes
    -----
    This is the compatibility wrapper that returns only the canonical person ID.
    The full reconciliation-aware helper also returns decision metadata for the
    review queue.
    """

    person_id, _ = _upsert_person_with_reconciliation(
        cursor,
        source_record_id=source_record_id,
        full_name=full_name,
        first_name=first_name,
        last_name=last_name,
        primary_email=primary_email,
        primary_phone=primary_phone,
        linkedin_url=linkedin_url,
        location=location,
        headline=headline,
        summary=summary,
        preferred_person_id=preferred_person_id,
    )
    return person_id


def _upsert_person_with_reconciliation(
    cursor: Cursor[Any],
    *,
    source_record_id: str,
    full_name: str,
    first_name: str | None,
    last_name: str | None,
    primary_email: str | None,
    primary_phone: str | None,
    linkedin_url: str | None,
    location: str | None,
    headline: str | None,
    summary: str | None,
    preferred_person_id: str | None = None,
) -> tuple[str, dict[str, Any]]:
    """
    Find or create the canonical person row for the candidate.

    Notes
    -----
    The lookup order is intentionally conservative:

    1. existing link from the candidate source record
    2. person already linked to the same canonical resume document
    3. existing LinkedIn URL match
    4. existing primary-email match
    5. existing primary-phone match
    6. otherwise create a new person row

    This avoids inventing fuzzy matching rules inside the first write helper.

    Example
    -------
    If the candidate source record is not linked yet but the extracted result
    contains:

        linkedin_url="https://www.linkedin.com/in/example"

    then an existing `people` row with that exact LinkedIn URL is reused.
    """
    resolution = _resolve_person_reconciliation(
        cursor,
        source_record_id=source_record_id,
        preferred_person_id=preferred_person_id,
        linkedin_url=linkedin_url,
        primary_email=primary_email,
        primary_phone=primary_phone,
    )

    resolved_person_id = resolution.get("matched_person_id")
    if resolved_person_id is None:
        cursor.execute(
            """
            insert into people (
                full_name,
                first_name,
                last_name,
                primary_email,
                primary_phone,
                linkedin_url,
                location,
                headline,
                summary
            )
            values (
                %(full_name)s,
                %(first_name)s,
                %(last_name)s,
                %(primary_email)s,
                %(primary_phone)s,
                %(linkedin_url)s,
                %(location)s,
                %(headline)s,
                %(summary)s
            )
            returning id
            """,
            {
                "full_name": full_name,
                "first_name": first_name,
                "last_name": last_name,
                "primary_email": primary_email,
                "primary_phone": primary_phone,
                "linkedin_url": linkedin_url,
                "location": location,
                "headline": headline,
                "summary": summary,
            },
        )
        inserted_row = cursor.fetchone()
        if inserted_row is None:
            raise RuntimeError("Failed to create person row.")
        inserted_person_id = inserted_row["id"]
        resolution["matched_person_id"] = inserted_person_id
        return inserted_person_id, resolution

    cursor.execute(
        """
        update people
        set
            full_name = %(full_name)s,
            first_name = coalesce(%(first_name)s, first_name),
            last_name = coalesce(%(last_name)s, last_name),
            primary_email = coalesce(%(primary_email)s, primary_email),
            primary_phone = coalesce(%(primary_phone)s, primary_phone),
            linkedin_url = coalesce(%(linkedin_url)s, linkedin_url),
            location = coalesce(%(location)s, location),
            headline = coalesce(%(headline)s, headline),
            summary = coalesce(%(summary)s, summary)
        where id = %(person_id)s
        """,
        {
            "person_id": resolved_person_id,
            "full_name": full_name,
            "first_name": first_name,
            "last_name": last_name,
            "primary_email": primary_email,
            "primary_phone": primary_phone,
            "linkedin_url": linkedin_url,
            "location": location,
            "headline": headline,
            "summary": summary,
        },
    )
    return resolved_person_id, resolution


def _upsert_candidate(
    cursor: Cursor[Any],
    *,
    source_record_id: str,
    person_id: str,
    current_title: str | None,
    current_company_id: str | None,
    candidate_status: str | None,
    availability_status: str | None,
    last_contacted_at: str | None,
    resume_updated_at: str | None,
    preferred_candidate_id: str | None = None,
) -> str:
    """
    Find or create the canonical candidate row for the person.

    Notes
    -----
    This compatibility wrapper preserves the older return type while the
    reconciliation-aware helper now also returns decision metadata.
    """

    candidate_id, _ = _upsert_candidate_with_reconciliation(
        cursor,
        source_record_id=source_record_id,
        person_id=person_id,
        current_title=current_title,
        current_company_id=current_company_id,
        candidate_status=candidate_status,
        availability_status=availability_status,
        last_contacted_at=last_contacted_at,
        resume_updated_at=resume_updated_at,
        preferred_candidate_id=preferred_candidate_id,
    )
    return candidate_id


def _upsert_candidate_with_reconciliation(
    cursor: Cursor[Any],
    *,
    source_record_id: str,
    person_id: str,
    current_title: str | None,
    current_company_id: str | None,
    candidate_status: str | None,
    availability_status: str | None,
    last_contacted_at: str | None,
    resume_updated_at: str | None,
    preferred_candidate_id: str | None = None,
) -> tuple[str, dict[str, Any]]:
    """
    Find or create the canonical candidate row for the person.

    Notes
    -----
    The schema already enforces one candidate row per person through
    `candidates.person_id unique`, so this helper uses that as the stable
    fallback identity after checking the source-record link.

    Example
    -------
    If the candidate source record is not linked yet but the matched person row
    already has a canonical candidate row, this helper updates that row rather
    than inserting a duplicate candidate.
    """
    resolution = _resolve_candidate_reconciliation(
        cursor,
        source_record_id=source_record_id,
        person_id=person_id,
        preferred_candidate_id=preferred_candidate_id,
    )

    resolved_candidate_id = resolution.get("matched_candidate_id")
    if resolved_candidate_id is None:
        cursor.execute(
            """
            insert into candidates (
                person_id,
                current_title,
                current_company_id,
                candidate_status,
                availability_status,
                last_contacted_at,
                resume_updated_at
            )
            values (
                %(person_id)s,
                %(current_title)s,
                %(current_company_id)s,
                %(candidate_status)s,
                %(availability_status)s,
                %(last_contacted_at)s,
                %(resume_updated_at)s
            )
            returning id
            """,
            {
                "person_id": person_id,
                "current_title": current_title,
                "current_company_id": current_company_id,
                "candidate_status": candidate_status,
                "availability_status": availability_status,
                "last_contacted_at": last_contacted_at,
                "resume_updated_at": resume_updated_at,
            },
        )
        inserted_row = cursor.fetchone()
        if inserted_row is None:
            raise RuntimeError("Failed to create candidate row.")
        inserted_candidate_id = inserted_row["id"]
        resolution["matched_candidate_id"] = inserted_candidate_id
        return inserted_candidate_id, resolution

    cursor.execute(
        """
        update candidates
        set
            current_title = coalesce(%(current_title)s, current_title),
            current_company_id = coalesce(
                %(current_company_id)s,
                current_company_id
            ),
            candidate_status = coalesce(%(candidate_status)s, candidate_status),
            availability_status = coalesce(
                %(availability_status)s,
                availability_status
            ),
            last_contacted_at = coalesce(
                %(last_contacted_at)s,
                last_contacted_at
            ),
            resume_updated_at = coalesce(
                %(resume_updated_at)s,
                resume_updated_at
            )
        where id = %(candidate_id)s
        """,
        {
            "candidate_id": resolved_candidate_id,
            "current_title": current_title,
            "current_company_id": current_company_id,
            "candidate_status": candidate_status,
            "availability_status": availability_status,
            "last_contacted_at": last_contacted_at,
            "resume_updated_at": resume_updated_at,
        },
    )
    return resolved_candidate_id, resolution


def _resolve_person_reconciliation(
    cursor: Cursor[Any],
    *,
    source_record_id: str,
    preferred_person_id: str | None,
    linkedin_url: str | None,
    primary_email: str | None,
    primary_phone: str | None,
) -> dict[str, Any]:
    """
    Resolve the strongest current person match for one incoming CV snapshot.

    Notes
    -----
    The resolution order is intentionally strict:

    1. existing source-record link
    2. person already linked to the matched resume document
    3. exact LinkedIn URL
    4. exact email
    5. exact phone
    6. otherwise create a new canonical person

    If any of the soft identity signals produce more than one match, the helper
    records a `needs_review` decision instead of guessing.
    """

    linked_person_id = _find_linked_entity_id(
        cursor,
        source_record_id=source_record_id,
        entity_column="person_id",
    )
    if linked_person_id is not None:
        return {
            "decision_status": "auto_matched",
            "decision_reason": "source_record_link",
            "confidence": 1.0,
            "matched_person_id": linked_person_id,
            "evidence_payload": {"matched_person_ids": [str(linked_person_id)]},
        }

    if preferred_person_id is not None:
        return {
            "decision_status": "auto_matched",
            "decision_reason": "resume_document_link",
            "confidence": 0.99,
            "matched_person_id": preferred_person_id,
            "evidence_payload": {
                "matched_person_ids": [str(preferred_person_id)],
            },
        }

    for column_name, signal_value, reason, confidence in (
        ("linkedin_url", linkedin_url, "linkedin_exact_match", 0.98),
        ("primary_email", primary_email, "email_exact_match", 0.95),
        ("primary_phone", primary_phone, "phone_exact_match", 0.93),
    ):
        if not signal_value:
            continue

        matched_person_ids = _find_person_ids_by_field(
            cursor,
            field_name=column_name,
            field_value=signal_value,
        )
        if len(matched_person_ids) == 1:
            return {
                "decision_status": "auto_matched",
                "decision_reason": reason,
                "confidence": confidence,
                "matched_person_id": matched_person_ids[0],
                "evidence_payload": {
                    "matched_person_ids": [str(matched_person_ids[0])],
                    "matched_field": column_name,
                    "matched_value": signal_value,
                },
            }
        if len(matched_person_ids) > 1:
            return {
                "decision_status": "needs_review",
                "decision_reason": f"ambiguous_{column_name}_match",
                "confidence": 0.55,
                "matched_person_id": None,
                "evidence_payload": {
                    "matched_person_ids": [str(person_id) for person_id in matched_person_ids],
                    "matched_field": column_name,
                    "matched_value": signal_value,
                },
            }

    return {
        "decision_status": "created_new",
        "decision_reason": "no_existing_person_match",
        "confidence": 0.2,
        "matched_person_id": None,
        "evidence_payload": {},
    }


def _resolve_candidate_reconciliation(
    cursor: Cursor[Any],
    *,
    source_record_id: str,
    person_id: str,
    preferred_candidate_id: str | None,
) -> dict[str, Any]:
    """
    Resolve the strongest current candidate match for one canonical person.

    Notes
    -----
    Candidate resolution is narrower than person resolution because the schema
    already enforces one candidate row per person.

    The main remaining ambiguity is when the resume-document path points at one
    candidate row while the resolved person already points at another. That is
    rare, but when it happens we record `needs_review` rather than silently
    choosing one explanation and discarding the other.
    """

    linked_candidate_id = _find_linked_entity_id(
        cursor,
        source_record_id=source_record_id,
        entity_column="candidate_id",
    )
    if linked_candidate_id is not None:
        return {
            "decision_status": "auto_matched",
            "decision_reason": "source_record_link",
            "confidence": 1.0,
            "matched_candidate_id": linked_candidate_id,
            "evidence_payload": {
                "matched_candidate_ids": [str(linked_candidate_id)],
            },
        }

    person_candidate_id = _find_candidate_id_by_person_id(cursor, person_id=person_id)
    if (
        preferred_candidate_id is not None
        and person_candidate_id is not None
        and preferred_candidate_id != person_candidate_id
    ):
        return {
            "decision_status": "needs_review",
            "decision_reason": "document_candidate_conflicts_with_person_candidate",
            "confidence": 0.6,
            "matched_candidate_id": person_candidate_id,
            "evidence_payload": {
                "matched_candidate_ids": [
                    str(person_candidate_id),
                    str(preferred_candidate_id),
                ],
            },
        }

    if preferred_candidate_id is not None:
        return {
            "decision_status": "auto_matched",
            "decision_reason": "resume_document_link",
            "confidence": 0.99,
            "matched_candidate_id": preferred_candidate_id,
            "evidence_payload": {
                "matched_candidate_ids": [str(preferred_candidate_id)],
            },
        }

    if person_candidate_id is not None:
        return {
            "decision_status": "auto_matched",
            "decision_reason": "person_unique_candidate",
            "confidence": 0.94,
            "matched_candidate_id": person_candidate_id,
            "evidence_payload": {
                "matched_candidate_ids": [str(person_candidate_id)],
            },
        }

    return {
        "decision_status": "created_new",
        "decision_reason": "no_existing_candidate_match",
        "confidence": 0.2,
        "matched_candidate_id": None,
        "evidence_payload": {},
    }


def _find_person_ids_by_field(
    cursor: Cursor[Any],
    *,
    field_name: Literal["linkedin_url", "primary_email", "primary_phone"],
    field_value: str,
) -> list[str]:
    """
    Return all canonical person IDs that exactly match one identity field.

    Example
    -------
    If two people rows share the same imported email, both IDs are returned so
    the caller can record a review-needed reconciliation decision.
    """

    cursor.execute(
        f"""
        select id
        from people
        where {field_name} = %(field_value)s
        """,
        {"field_value": field_value},
    )
    return [row["id"] for row in cursor.fetchall()]


def _find_candidate_id_by_person_id(
    cursor: Cursor[Any],
    *,
    person_id: str,
) -> str | None:
    """
    Return the one canonical candidate row already attached to a person.
    """

    cursor.execute(
        """
        select id
        from candidates
        where person_id = %(person_id)s
        limit 1
        """,
        {"person_id": person_id},
    )
    row = cursor.fetchone()
    if row is None:
        return None
    return row["id"]


def _upsert_resume_document(
    cursor: Cursor[Any],
    *,
    source_record_id: str,
    resume_title: str | None,
    mime_type: str | None,
    source_uri: str | None,
    content_hash: str | None,
    extracted_text: str | None,
    existing_document_id: str | None = None,
) -> str:
    """
    Find or create the canonical resume document row.

    Notes
    -----
    The resume-source record is treated as the primary identity when possible.
    If a document has not yet been linked to that source record, we fall back to
    the content hash to avoid obvious duplicate document rows for the same CV.

    Example
    -------
    If the selected resume attachment changed upstream but still contains the
    same extracted text, the `content_hash` path lets this helper reuse the
    existing canonical resume document row instead of inserting a duplicate.
    """

    if existing_document_id is None:
        existing_document_id = _find_existing_resume_document_id(
            cursor,
            source_record_id=source_record_id,
            content_hash=content_hash,
        )

    if existing_document_id is None:
        cursor.execute(
            """
            insert into documents (
                document_type,
                title,
                source_uri,
                mime_type,
                content_hash,
                extracted_text
            )
            values (
                'resume',
                %(title)s,
                %(source_uri)s,
                %(mime_type)s,
                %(content_hash)s,
                %(extracted_text)s
            )
            returning id
            """,
            {
                "title": resume_title,
                "source_uri": source_uri,
                "mime_type": mime_type,
                "content_hash": content_hash,
                "extracted_text": extracted_text,
            },
        )
        inserted_row = cursor.fetchone()
        if inserted_row is None:
            raise RuntimeError("Failed to create document row.")
        return inserted_row["id"]

    cursor.execute(
        """
        update documents
        set
            title = coalesce(%(title)s, title),
            source_uri = coalesce(%(source_uri)s, source_uri),
            mime_type = coalesce(%(mime_type)s, mime_type),
            content_hash = coalesce(%(content_hash)s, content_hash),
            extracted_text = coalesce(%(extracted_text)s, extracted_text)
        where id = %(document_id)s
        """,
        {
            "document_id": existing_document_id,
            "title": resume_title,
            "source_uri": source_uri,
            "mime_type": mime_type,
            "content_hash": content_hash,
            "extracted_text": extracted_text,
        },
    )
    return existing_document_id


def _upsert_reconciliation_decision(
    cursor: Cursor[Any],
    *,
    source_record_id: str,
    document_id: str | None,
    person_id: str,
    candidate_id: str,
    person_reconciliation: dict[str, Any],
    candidate_reconciliation: dict[str, Any],
) -> dict[str, Any]:
    """
    Insert or update the current reconciliation decision for one source record.

    Notes
    -----
    Reconciliation is stored as data rather than hidden in importer control
    flow. That gives operators one explicit row explaining whether we:

    - auto-matched onto an existing canonical identity
    - created a new canonical identity cleanly
    - or need review because the identity evidence was ambiguous

    Example
    -------
    A content-hash match from Recruiterflow onto an existing JobAdder candidate
    produces an `auto_matched` decision, while two exact email hits produce a
    `needs_review` decision with both candidate IDs recorded in the evidence.
    """

    combined_decision = _combine_reconciliation_decisions(
        person_reconciliation=person_reconciliation,
        candidate_reconciliation=candidate_reconciliation,
    )

    cursor.execute(
        """
        insert into reconciliation_decisions (
            source_record_id,
            document_id,
            person_id,
            candidate_id,
            decision_status,
            decision_reason,
            confidence,
            evidence_payload
        )
        values (
            %(source_record_id)s,
            %(document_id)s,
            %(person_id)s,
            %(candidate_id)s,
            %(decision_status)s,
            %(decision_reason)s,
            %(confidence)s,
            %(evidence_payload)s
        )
        on conflict (source_record_id)
        do update set
            document_id = excluded.document_id,
            person_id = excluded.person_id,
            candidate_id = excluded.candidate_id,
            decision_status = excluded.decision_status,
            decision_reason = excluded.decision_reason,
            confidence = excluded.confidence,
            evidence_payload = excluded.evidence_payload
        returning id, decision_status
        """,
        {
            "source_record_id": source_record_id,
            "document_id": document_id,
            "person_id": person_id,
            "candidate_id": candidate_id,
            "decision_status": combined_decision["decision_status"],
            "decision_reason": combined_decision["decision_reason"],
            "confidence": combined_decision["confidence"],
            "evidence_payload": Jsonb(
                _make_json_safe_summary(combined_decision["evidence_payload"])
            ),
        },
    )
    row = cursor.fetchone()
    if row is None:
        raise RuntimeError("Failed to persist reconciliation decision row.")
    return dict(row)


def _combine_reconciliation_decisions(
    *,
    person_reconciliation: dict[str, Any],
    candidate_reconciliation: dict[str, Any],
) -> dict[str, Any]:
    """
    Collapse person and candidate resolution outcomes into one decision row.

    Notes
    -----
    The operator page needs one current decision per accepted source record.
    This helper keeps that top-level status intentionally simple:

    - `needs_review` wins if either entity layer is ambiguous
    - `created_new` is used when no safe existing identity was available
    - otherwise the result is `auto_matched`
    """

    person_status = str(person_reconciliation["decision_status"])
    candidate_status = str(candidate_reconciliation["decision_status"])

    if "needs_review" in {person_status, candidate_status}:
        decision_status = "needs_review"
        decision_reason = (
            person_reconciliation["decision_reason"]
            if person_status == "needs_review"
            else candidate_reconciliation["decision_reason"]
        )
    elif "created_new" in {person_status, candidate_status}:
        decision_status = "created_new"
        if person_status == "created_new":
            decision_reason = str(person_reconciliation["decision_reason"])
        else:
            decision_reason = str(candidate_reconciliation["decision_reason"])
    else:
        decision_status = "auto_matched"
        decision_reason = (
            f"{person_reconciliation['decision_reason']} + "
            f"{candidate_reconciliation['decision_reason']}"
        )

    confidence_values = [
        float(value)
        for value in (
            person_reconciliation.get("confidence"),
            candidate_reconciliation.get("confidence"),
        )
        if value is not None
    ]
    confidence = min(confidence_values) if confidence_values else None

    return {
        "decision_status": decision_status,
        "decision_reason": decision_reason,
        "confidence": confidence,
        "evidence_payload": {
            "person_reconciliation": person_reconciliation,
            "candidate_reconciliation": candidate_reconciliation,
        },
    }


def _refresh_candidate_skills(
    cursor: Cursor[Any],
    *,
    candidate_id: str,
    source_record_id: str,
    extracted_skills: list[str],
    extracted_tools: list[str],
) -> list[str]:
    """
    Refresh candidate-skill links for the accepted extraction result.

    Notes
    -----
    This helper treats the accepted extraction as the latest truth for the
    resume-derived skill set tied to this specific extraction source record.

    It therefore:

    - upserts the normalised skill rows
    - upserts candidate-skill links for the current accepted set
    - removes stale links previously written by the same extraction source row

    The current schema stores both conventional skills and tools in the same
    `skills` table. We therefore keep the write policy simple here:

    - ordinary skills first
    - tools/platforms second
    - duplicate labels collapse into one canonical skill row by name

    Example
    -------
    Calling with:

        extracted_skills=["Python", "SQL"]
        extracted_tools=["Power BI", "SQL"]

    results in candidate-skill links for:

        - Python
        - SQL
        - Power BI

    with the duplicate `SQL` label collapsing to one canonical skill row.
    """

    ordered_skill_entries = _build_ordered_skill_entries(
        extracted_skills=extracted_skills,
        extracted_tools=extracted_tools,
    )

    target_skill_ids: list[str] = []

    for skill_name, skill_type, evidence_text in ordered_skill_entries:
        skill_id = _upsert_skill(
            cursor,
            skill_name=skill_name,
            skill_type=skill_type,
        )
        target_skill_ids.append(skill_id)

        cursor.execute(
            """
            insert into candidate_skills (
                candidate_id,
                skill_id,
                source_record_id,
                confidence,
                evidence_text
            )
            values (
                %(candidate_id)s,
                %(skill_id)s,
                %(source_record_id)s,
                %(confidence)s,
                %(evidence_text)s
            )
            on conflict (candidate_id, skill_id)
            do update set
                source_record_id = excluded.source_record_id,
                confidence = excluded.confidence,
                evidence_text = excluded.evidence_text
            """,
            {
                "candidate_id": candidate_id,
                "skill_id": skill_id,
                "source_record_id": source_record_id,
                "confidence": 1.0,
                "evidence_text": evidence_text,
            },
        )

    if target_skill_ids:
        cursor.execute(
            """
            delete from candidate_skills
            where candidate_id = %(candidate_id)s
              and source_record_id = %(source_record_id)s
              and not (skill_id = any(%(target_skill_ids)s))
            """,
            {
                "candidate_id": candidate_id,
                "source_record_id": source_record_id,
                "target_skill_ids": target_skill_ids,
            },
        )
    else:
        cursor.execute(
            """
            delete from candidate_skills
            where candidate_id = %(candidate_id)s
              and source_record_id = %(source_record_id)s
            """,
            {
                "candidate_id": candidate_id,
                "source_record_id": source_record_id,
            },
        )

    return target_skill_ids


def _refresh_candidate_note_interactions(
    cursor: Cursor[Any],
    *,
    candidate_id: str,
    person_id: str,
    cleaned_candidate_notes: list[dict[str, Any]],
) -> list[str]:
    """
    Refresh first-class JobAdder note interactions for one candidate.

    Parameters
    ----------
    cursor : Cursor[Any]
        Open transaction cursor.

    candidate_id : str
        Canonical candidate UUID receiving the refreshed note interactions.

    person_id : str
        Canonical person UUID linked to that candidate.

    cleaned_candidate_notes : list[dict[str, Any]]
        Cleaned JobAdder note payload prepared by the service layer.

    Returns
    -------
    list[str]
        Interaction IDs created for the current note set.

    Notes
    -----
    This first interaction slice is intentionally narrow and source-synchronised.

    We currently treat JobAdder candidate notes as:

    - `interactions.source_system = "jobadder"`
    - `interactions.interaction_type = "jobadder_candidate_note"`

    The helper first removes the previously persisted JobAdder note
    interactions for this candidate, then recreates the current set from the
    latest source snapshot.

    That replacement strategy is deliberate:

    - the source of truth is still the latest JobAdder note set
    - the current schema has no direct `interaction_id` target inside
      `source_record_links`
    - replacing the candidate's JobAdder-note interactions is simpler and more
      reliable than guessing note identity across reruns

    Empty notes are still preserved in provenance payloads, but they are not
    promoted into first-class `interactions` rows because they add no useful
    queryable body content.

    Example
    -------
    A note item such as:

        {
            "type": "Phone Call",
            "created_at": "2026-05-13T09:00:00Z",
            "cleaned_text": "Candidate open to move.",
        }

    becomes one `interactions` row plus:

        - one candidate participant link
        - one person participant link
    """

    interaction_entries = _build_candidate_note_interaction_entries(
        cleaned_candidate_notes=cleaned_candidate_notes
    )
    _delete_existing_candidate_note_interactions(
        cursor,
        candidate_id=candidate_id,
    )

    interaction_ids: list[str] = []

    for entry in interaction_entries:
        cursor.execute(
            """
            insert into interactions (
                interaction_type,
                occurred_at,
                subject,
                body,
                summary,
                source_system
            )
            values (
                %(interaction_type)s,
                %(occurred_at)s,
                %(subject)s,
                %(body)s,
                %(summary)s,
                %(source_system)s
            )
            returning id
            """,
            entry,
        )
        row = cursor.fetchone()
        if row is None:
            raise RuntimeError("Failed to create interaction row.")

        interaction_id = row["id"]
        interaction_ids.append(interaction_id)

        _insert_interaction_participant(
            cursor,
            interaction_id=interaction_id,
            candidate_id=candidate_id,
            role_in_interaction="candidate_subject",
        )
        _insert_interaction_participant(
            cursor,
            interaction_id=interaction_id,
            person_id=person_id,
            role_in_interaction="person_subject",
        )

    return interaction_ids


def _build_candidate_note_interaction_entries(
    *,
    cleaned_candidate_notes: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """
    Convert cleaned JobAdder note items into insert-ready interaction entries.

    Parameters
    ----------
    cleaned_candidate_notes : list[dict[str, Any]]
        Cleaned note dictionaries prepared by the service layer.

    Returns
    -------
    list[dict[str, Any]]
        Interaction insert payloads for non-empty note bodies.

    Notes
    -----
    We keep the interaction model deliberately factual:

    - `subject` is the JobAdder note type when available
    - `body` is the cleaned note text
    - `summary` is a short preview of that body

    Notes with no usable text are skipped here because the first-class
    interaction layer should stay queryable and meaningful. Their existence is
    still preserved in the upstream provenance payloads.

    Example
    -------
    A cleaned note such as:

        {
            "type": "Email Reply",
            "cleaned_text": "Happy to discuss the role next week.",
        }

    becomes an interaction entry with:

        subject="Email Reply"
        body="Happy to discuss the role next week."
    """

    entries: list[dict[str, Any]] = []

    for note in cleaned_candidate_notes:
        body = _build_candidate_note_interaction_body(note)
        if body is None:
            continue

        subject = _clean_optional_string(note.get("type")) or "JobAdder note"
        occurred_at = _clean_optional_string(
            note.get("updated_at")
        ) or _clean_optional_string(note.get("created_at"))

        entries.append(
            {
                "interaction_type": "jobadder_candidate_note",
                "occurred_at": occurred_at,
                "subject": subject,
                "body": body,
                "summary": _build_interaction_summary_preview(body),
                "source_system": "jobadder",
            }
        )

    return entries


def _build_candidate_note_interaction_body(note: dict[str, Any]) -> str | None:
    """
    Return the queryable interaction body for one cleaned JobAdder note.

    Example
    -------
    A note with:

        cleaned_text="Candidate open to new roles."

    returns:

        "Candidate open to new roles."
    """

    for key in ("cleaned_text", "text"):
        body = _clean_optional_string(note.get(key))
        if body is not None:
            return body
    return None


def _build_interaction_summary_preview(body: str) -> str:
    """
    Build a short summary preview for one interaction body.

    Example
    -------
    A long note body is shortened to a compact preview of at most 240
    characters for easier operator inspection.
    """

    if len(body) <= 240:
        return body
    return body[:237].rstrip() + "..."


def _delete_existing_candidate_note_interactions(
    cursor: Cursor[Any],
    *,
    candidate_id: str,
) -> None:
    """
    Delete the previously persisted JobAdder note interactions for one candidate.

    Notes
    -----
    This helper removes only the narrow interaction slice created by
    `_refresh_candidate_note_interactions(...)`:

    - `source_system = "jobadder"`
    - `interaction_type = "jobadder_candidate_note"`
    - linked to the supplied candidate

    It intentionally leaves any future non-note interactions untouched.
    """

    cursor.execute(
        """
        select distinct i.id
        from interactions i
        inner join interaction_participants ip
            on ip.interaction_id = i.id
        where i.source_system = 'jobadder'
          and i.interaction_type = 'jobadder_candidate_note'
          and ip.candidate_id = %(candidate_id)s
        """,
        {"candidate_id": candidate_id},
    )
    interaction_ids = [row["id"] for row in cursor.fetchall()]

    if not interaction_ids:
        return

    cursor.execute(
        """
        delete from interaction_participants
        where interaction_id = any(%(interaction_ids)s)
        """,
        {"interaction_ids": interaction_ids},
    )
    cursor.execute(
        """
        delete from interactions
        where id = any(%(interaction_ids)s)
        """,
        {"interaction_ids": interaction_ids},
    )


def _insert_interaction_participant(
    cursor: Cursor[Any],
    *,
    interaction_id: str,
    role_in_interaction: str,
    person_id: str | None = None,
    candidate_id: str | None = None,
) -> None:
    """
    Insert one interaction participant row.

    Example
    -------
    A note interaction can create both:

        - a candidate participant row
        - a person participant row
    """

    cursor.execute(
        """
        insert into interaction_participants (
            interaction_id,
            person_id,
            candidate_id,
            role_in_interaction
        )
        values (
            %(interaction_id)s,
            %(person_id)s,
            %(candidate_id)s,
            %(role_in_interaction)s
        )
        """,
        {
            "interaction_id": interaction_id,
            "person_id": person_id,
            "candidate_id": candidate_id,
            "role_in_interaction": role_in_interaction,
        },
    )


def _build_ordered_skill_entries(
    *,
    extracted_skills: list[str],
    extracted_tools: list[str],
) -> list[tuple[str, str, str]]:
    """
    Merge extracted skills and tools into one ordered deduplicated list.

    Example
    -------
    Calling with:

        extracted_skills=["Python", "SQL"]
        extracted_tools=["Power BI", "SQL"]

    returns entries for:

        - Python
        - SQL
        - Power BI

    where `SQL` is kept only once because the canonical table is unique on
    skill name.
    """

    seen: set[str] = set()
    merged: list[tuple[str, str, str]] = []

    for raw_name, skill_type, evidence_text in (
        *(
            (
                skill_name,
                "skill",
                "Extracted from the structured resume skills list.",
            )
            for skill_name in extracted_skills
        ),
        *(
            (
                tool_name,
                "tool",
                "Extracted from the structured resume tools/platforms list.",
            )
            for tool_name in extracted_tools
        ),
    ):
        cleaned_name = raw_name.strip()
        if cleaned_name == "":
            continue

        dedupe_key = cleaned_name.casefold()
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        merged.append((cleaned_name, skill_type, evidence_text))

    return merged


def _upsert_skill(
    cursor: Cursor[Any],
    *,
    skill_name: str,
    skill_type: str,
) -> str:
    """
    Insert or update one canonical skill row by name.

    Notes
    -----
    The schema already enforces `skills.name unique`, so the write path can use
    a straightforward upsert without needing a separate pre-read.

    Example
    -------
    If `skill_name="Python"` already exists, this helper returns the existing
    canonical row ID instead of creating a second `Python` entry.
    """

    cursor.execute(
        """
        insert into skills (
            name,
            canonical_name,
            skill_type
        )
        values (
            %(name)s,
            %(canonical_name)s,
            %(skill_type)s
        )
        on conflict (name)
        do update set
            canonical_name = coalesce(
                skills.canonical_name,
                excluded.canonical_name
            ),
            skill_type = coalesce(skills.skill_type, excluded.skill_type)
        returning id
        """,
        {
            "name": skill_name,
            "canonical_name": skill_name,
            "skill_type": skill_type,
        },
    )
    row = cursor.fetchone()
    if row is None:
        raise RuntimeError("Failed to persist skill row.")
    return row["id"]


def _find_existing_resume_document_id(
    cursor: Cursor[Any],
    *,
    source_record_id: str | None,
    content_hash: str | None,
) -> str | None:
    """
    Return the best existing canonical resume document match.

    Notes
    -----
    The lookup order is intentionally conservative:

    1. document already linked to the current source record
    2. existing resume document with the same content hash

    Example
    -------
    If the same CV arrives from Outlook after JobAdder already persisted it,
    the content-hash lookup can reuse the existing canonical resume document.
    """

    if source_record_id is not None:
        linked_document_id = _find_linked_entity_id(
            cursor,
            source_record_id=source_record_id,
            entity_column="document_id",
        )
        if linked_document_id is not None:
            return linked_document_id

    if content_hash:
        cursor.execute(
            """
            select id
            from documents
            where document_type = 'resume'
              and content_hash = %(content_hash)s
            limit 1
            """,
            {"content_hash": content_hash},
        )
        row = cursor.fetchone()
        if row is not None:
            return row["id"]

    return None


def _find_document_linked_entity_id(
    cursor: Cursor[Any],
    *,
    document_id: str | None,
    entity_column: Literal["person_id", "candidate_id"],
) -> str | None:
    """
    Return one canonical person/candidate already linked to a resume document.

    Notes
    -----
    This is the first narrow cross-source reconciliation rule:

    - if the same resume content already maps to one canonical document
    - and that document already belongs to one person/candidate
    - reuse those canonical rows before inventing a new identity

    Example
    -------
    A content-hash match from Recruiterflow to an existing JobAdder resume can
    resolve straight back to the same canonical candidate.
    """

    if document_id is None:
        return None

    cursor.execute(
        f"""
        select {entity_column}
        from document_links
        where document_id = %(document_id)s
          and {entity_column} is not null
        limit 1
        """,
        {"document_id": document_id},
    )
    row = cursor.fetchone()
    if row is None:
        return None
    return row[entity_column]


def _find_linked_entity_id(
    cursor: Cursor[Any],
    *,
    source_record_id: str,
    entity_column: Literal[
        "person_id",
        "candidate_id",
        "company_id",
        "document_id",
    ],
) -> str | None:
    """
    Return one linked canonical entity ID from `source_record_links`.

    Notes
    -----
    The `entity_column` argument is restricted to a small literal set so the
    dynamic SQL here stays explicit and safe.

    Example
    -------
    A call with:

        entity_column="candidate_id"

    returns the candidate linked to that source record when such a link already
    exists, otherwise `None`.
    """

    cursor.execute(
        f"""
        select {entity_column}
        from source_record_links
        where source_record_id = %(source_record_id)s
          and {entity_column} is not null
        limit 1
        """,
        {"source_record_id": source_record_id},
    )
    row = cursor.fetchone()
    if row is None:
        return None
    return row[entity_column]


def _ensure_source_record_link(
    cursor: Cursor[Any],
    *,
    source_record_id: str,
    person_id: str | None = None,
    candidate_id: str | None = None,
    company_id: str | None = None,
    document_id: str | None = None,
) -> None:
    """
    Insert one `source_record_links` row only when it does not already exist.

    Notes
    -----
    The table does not currently expose a natural unique constraint across the
    nullable foreign-key columns, so the helper performs an existence check
    first. This keeps reruns idempotent without forcing a schema change in the
    same step.

    Example
    -------
    A call with:

        source_record_id="..."
        candidate_id="..."

    inserts one candidate-target link on the first accepted run and becomes a
    no-op on later identical reruns.
    """

    column_name, entity_id = _pick_single_entity_target(
        person_id=person_id,
        candidate_id=candidate_id,
        company_id=company_id,
        document_id=document_id,
    )

    cursor.execute(
        f"""
        select id
        from source_record_links
        where source_record_id = %(source_record_id)s
          and {column_name} = %(entity_id)s
        limit 1
        """,
        {
            "source_record_id": source_record_id,
            "entity_id": entity_id,
        },
    )
    if cursor.fetchone() is not None:
        return

    payload = {
        "source_record_id": source_record_id,
        "person_id": person_id,
        "candidate_id": candidate_id,
        "company_id": company_id,
        "document_id": document_id,
    }
    cursor.execute(
        """
        insert into source_record_links (
            source_record_id,
            person_id,
            candidate_id,
            company_id,
            document_id
        )
        values (
            %(source_record_id)s,
            %(person_id)s,
            %(candidate_id)s,
            %(company_id)s,
            %(document_id)s
        )
        """,
        payload,
    )


def _ensure_document_link(
    cursor: Cursor[Any],
    *,
    document_id: str,
    relationship_type: str,
    source_record_id: str | None,
    person_id: str | None = None,
    candidate_id: str | None = None,
) -> None:
    """
    Insert one `document_links` row only when it does not already exist.

    Notes
    -----
    `document_links` capture domain relationships such as "this resume belongs
    to this candidate" independently of the broader provenance graph recorded
    in `source_record_links`.

    Example
    -------
    A call with:

        document_id="..."
        candidate_id="..."
        relationship_type="resume"

    creates one candidate-resume link and then becomes idempotent on later
    reruns.
    """

    column_name, entity_id = _pick_single_document_target(
        person_id=person_id,
        candidate_id=candidate_id,
    )

    cursor.execute(
        f"""
        select id
        from document_links
        where document_id = %(document_id)s
          and relationship_type = %(relationship_type)s
          and {column_name} = %(entity_id)s
        limit 1
        """,
        {
            "document_id": document_id,
            "relationship_type": relationship_type,
            "entity_id": entity_id,
        },
    )
    if cursor.fetchone() is not None:
        return

    cursor.execute(
        """
        insert into document_links (
            document_id,
            person_id,
            candidate_id,
            source_record_id,
            relationship_type
        )
        values (
            %(document_id)s,
            %(person_id)s,
            %(candidate_id)s,
            %(source_record_id)s,
            %(relationship_type)s
        )
        """,
        {
            "document_id": document_id,
            "person_id": person_id,
            "candidate_id": candidate_id,
            "source_record_id": source_record_id,
            "relationship_type": relationship_type,
        },
    )


def _pick_single_entity_target(
    *,
    person_id: str | None,
    candidate_id: str | None,
    company_id: str | None,
    document_id: str | None,
) -> tuple[str, str]:
    """
    Return the one non-null source-link target column and value.

    Notes
    -----
    These helpers intentionally insert one source-record link row per entity
    target rather than mixing several entity types into one row. That makes the
    existence checks and later debugging much easier to reason about.

    Example
    -------
    A call with only:

        person_id="person-uuid"

    returns:

        ("person_id", "person-uuid")
    """

    populated_targets = [
        ("person_id", person_id),
        ("candidate_id", candidate_id),
        ("company_id", company_id),
        ("document_id", document_id),
    ]
    resolved_targets = [
        (column_name, value)
        for column_name, value in populated_targets
        if value is not None
    ]
    if len(resolved_targets) != 1:
        raise ValueError(
            "Expected exactly one entity target when inserting a source_record link."
        )
    return resolved_targets[0]


def _pick_single_document_target(
    *,
    person_id: str | None,
    candidate_id: str | None,
) -> tuple[str, str]:
    """
    Return the one non-null document-link target column and value.

    Example
    -------
    A call with only:

        candidate_id="candidate-uuid"

    returns:

        ("candidate_id", "candidate-uuid")
    """

    populated_targets = [
        ("person_id", person_id),
        ("candidate_id", candidate_id),
    ]
    resolved_targets = [
        (column_name, value)
        for column_name, value in populated_targets
        if value is not None
    ]
    if len(resolved_targets) != 1:
        raise ValueError(
            "Expected exactly one person/candidate target when inserting a document link."
        )
    return resolved_targets[0]


def _make_json_safe_summary(value: Any) -> Any:
    """
    Convert the persistence summary into JSON-safe plain Python types.

    Notes
    -----
    `psycopg` helpfully returns native Python objects for Postgres columns,
    including `uuid.UUID` values for canonical IDs. That is useful inside the
    transaction, but the operator-facing scripts later write the returned
    summary directly to JSON.

    Rather than forcing every caller to special-case DB-native types, this
    helper normalises them once at the persistence boundary.

    Example
    -------
    A summary such as:

        {"candidate_id": UUID("...")}

    becomes:

        {"candidate_id": "..."}
    """

    if isinstance(value, UUID):
        return str(value)

    if isinstance(value, datetime):
        return value.isoformat()

    if isinstance(value, dict):
        return {
            key: _make_json_safe_summary(nested_value)
            for key, nested_value in value.items()
        }

    if isinstance(value, list):
        return [_make_json_safe_summary(item) for item in value]

    if isinstance(value, tuple):
        return [_make_json_safe_summary(item) for item in value]

    return value


def _clean_optional_string(value: Any) -> str | None:
    """
    Return a stripped string or `None` when the input is blank-like.

    Example
    -------
    Inputs such as:

        "  Phone Call  "
        ""
        None

    become:

        "Phone Call"
        None
        None
    """

    if not isinstance(value, str):
        return None

    cleaned_value = value.strip()
    if cleaned_value == "":
        return None
    return cleaned_value


__all__ = [
    "persist_jobadder_candidate_profile_snapshot",
    "persist_resume_extraction_snapshot",
]
