"""
Database helpers for persisting accepted JobAdder resume-extraction results.

This module contains the first narrow write path for turning a successful
resume-extraction result into canonical Supabase/Postgres records.

It gives the rest of the repository a stable way to talk about:

- saving the accepted extraction result as provenance-bearing source records
- upserting the linked person, candidate, company, and resume document rows
- refreshing candidate-skill links from the latest accepted extraction
- keeping direct SQL write logic out of scripts and service orchestration code

Why this module exists
----------------------
The extraction pipeline is now strong enough to produce repeatable accepted
results against real JobAdder candidates.

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

Instead, it implements the smallest reliable persistence slice that is already
justified by the current extraction maturity:

- source records
- person
- candidate
- current company
- resume document
- candidate skills

Example
-------
Typical service usage looks like:

    from backend.db.resume_extraction_persistence import (
        persist_jobadder_resume_extraction_snapshot,
    )

    summary = persist_jobadder_resume_extraction_snapshot(
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
    "jobadder_resume_attachment",
    "jobadder_resume_extraction",
]


def persist_jobadder_resume_extraction_snapshot(
    persistence_payload: dict[str, Any],
) -> dict[str, Any]:
    """
    Persist one accepted JobAdder resume-extraction result.

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
                sync_status="accepted",
            )

            resume_source_record: dict[str, Any] | None = None
            if latest_resume_attachment_key is not None:
                resume_source_record = _upsert_source_record(
                    cursor,
                    source_system="jobadder",
                    source_record_type="jobadder_resume_attachment",
                    source_record_id=latest_resume_attachment_key,
                    source_payload=persistence_payload["resume_source_payload"],
                    source_payload_hash=persistence_payload[
                        "resume_source_payload_hash"
                    ],
                    import_run_id=persistence_payload.get("import_run_id"),
                    processed_at=persisted_at,
                    sync_status="accepted",
                )

            extraction_source_record = _upsert_source_record(
                cursor,
                source_system="jobadder",
                source_record_type="jobadder_resume_extraction",
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

            person_id = _upsert_person(
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

            candidate_id = _upsert_candidate(
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

            linked_skill_ids = _refresh_candidate_skills(
                cursor,
                candidate_id=candidate_id,
                source_record_id=extraction_source_record["id"],
                extracted_skills=persistence_payload.get("skills", []),
                extracted_tools=persistence_payload.get("tools_and_platforms", []),
            )

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
        "quality_status": persistence_payload.get("quality_status"),
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
) -> str:
    """
    Find or create the canonical person row for the candidate.

    Notes
    -----
    The lookup order is intentionally conservative:

    1. existing link from the candidate source record
    2. existing LinkedIn URL match
    3. existing primary-email match
    4. otherwise create a new person row

    This avoids inventing fuzzy matching rules inside the first write helper.
    """

    existing_person_id = _find_linked_entity_id(
        cursor,
        source_record_id=source_record_id,
        entity_column="person_id",
    )
    if existing_person_id is None and linkedin_url:
        cursor.execute(
            """
            select id
            from people
            where linkedin_url = %(linkedin_url)s
            limit 1
            """,
            {"linkedin_url": linkedin_url},
        )
        row = cursor.fetchone()
        if row is not None:
            existing_person_id = row["id"]

    if existing_person_id is None and primary_email:
        cursor.execute(
            """
            select id
            from people
            where primary_email = %(primary_email)s
            limit 1
            """,
            {"primary_email": primary_email},
        )
        row = cursor.fetchone()
        if row is not None:
            existing_person_id = row["id"]

    if existing_person_id is None:
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
        return inserted_row["id"]

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
            "person_id": existing_person_id,
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
    return existing_person_id


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
) -> str:
    """
    Find or create the canonical candidate row for the person.

    Notes
    -----
    The schema already enforces one candidate row per person through
    `candidates.person_id unique`, so this helper uses that as the stable
    fallback identity after checking the source-record link.
    """

    existing_candidate_id = _find_linked_entity_id(
        cursor,
        source_record_id=source_record_id,
        entity_column="candidate_id",
    )
    if existing_candidate_id is None:
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
        if row is not None:
            existing_candidate_id = row["id"]

    if existing_candidate_id is None:
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
        return inserted_row["id"]

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
            "candidate_id": existing_candidate_id,
            "current_title": current_title,
            "current_company_id": current_company_id,
            "candidate_status": candidate_status,
            "availability_status": availability_status,
            "last_contacted_at": last_contacted_at,
            "resume_updated_at": resume_updated_at,
        },
    )
    return existing_candidate_id


def _upsert_resume_document(
    cursor: Cursor[Any],
    *,
    source_record_id: str,
    resume_title: str | None,
    mime_type: str | None,
    source_uri: str | None,
    content_hash: str | None,
    extracted_text: str | None,
) -> str:
    """
    Find or create the canonical resume document row.

    Notes
    -----
    The resume-source record is treated as the primary identity when possible.
    If a document has not yet been linked to that source record, we fall back to
    the content hash to avoid obvious duplicate document rows for the same CV.
    """

    existing_document_id = _find_linked_entity_id(
        cursor,
        source_record_id=source_record_id,
        entity_column="document_id",
    )

    if existing_document_id is None and content_hash:
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
            existing_document_id = row["id"]

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


__all__ = [
    "persist_jobadder_resume_extraction_snapshot",
]
