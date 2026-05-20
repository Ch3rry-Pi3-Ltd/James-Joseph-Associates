"""
Database helpers for persisting narrow JobAdder application snapshots.

This module contains the first narrow write path for turning one live JobAdder
application plus one live JobAdder candidate detail payload into canonical
Supabase/Postgres rows.

It gives the rest of the repository a stable way to talk about:

- saving the upstream JobAdder application snapshot as provenance
- saving the upstream JobAdder candidate snapshot as provenance
- upserting the linked person, candidate, company, and application rows
- linking the two source records back to the canonical entities explicitly
- keeping direct SQL write logic out of service orchestration and operator
  scripts

Why this module exists
----------------------
The project already proved the surrounding source shape:

- JobAdder applications carry the vacancy context
- JobAdder candidate attachments are the structured CV source
- Dropbox `.eml` files preserve advert-response provenance
- Dropbox CV files can mirror the JobAdder attachment bytes exactly

That leaves a narrower next question:

    "Can we persist one real JobAdder application into the canonical schema
    without making a script own the raw SQL and link-table rules?"

This module is the answer to that narrow question.

Current scope
-------------
This is intentionally not the full application-ingestion system.

It does not attempt to:

- persist every application-side child object yet
- derive interactions from recruiter notes here
- store attachments on the application itself
- guess the final source-of-truth rule for every application field

Instead, it implements the smallest reliable write slice already justified by
the current evidence:

- one JobAdder candidate source record
- one JobAdder application source record
- one canonical person
- one canonical candidate
- zero or one current employer company
- one canonical application linked to an already-known canonical job

Example
-------
Typical service usage looks like:

    from backend.db.application_persistence import (
        persist_jobadder_application_snapshot,
    )

    summary = persist_jobadder_application_snapshot(persistence_payload)
    print(summary["application_id"])
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
    "jobadder_application_snapshot",
]


def persist_jobadder_application_snapshot(
    persistence_payload: dict[str, Any],
) -> dict[str, Any]:
    """
    Persist one JobAdder application plus candidate snapshot.

    Parameters
    ----------
    persistence_payload : dict[str, Any]
        Normalized payload prepared by the service layer.

        The payload should already contain:

        - the upstream application and candidate identifiers
        - the canonical application fields to write
        - the candidate/person fields to upsert
        - the canonical job resolver inputs
        - the source payloads and payload hashes for provenance

    Returns
    -------
    dict[str, Any]
        Small persistence summary containing the canonical IDs and important
        source-record IDs written by the transaction.

    Notes
    -----
    The transaction intentionally keeps the candidate snapshot and the
    application snapshot as separate provenance records because they answer
    different lineage questions later:

    - what candidate record did we ingest?
    - what application relationship record did we ingest?

    Example
    -------
    Persisting a prepared payload returns a summary such as:

        {
            "person_id": "...",
            "candidate_id": "...",
            "application_id": "...",
            "job_id": "...",
        }
    """
    source_candidate_id = str(persistence_payload["source_candidate_id"])
    source_application_id = str(persistence_payload["source_application_id"])
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

            application_source_record = _upsert_source_record(
                cursor,
                source_system="jobadder",
                source_record_type="jobadder_application_snapshot",
                source_record_id=source_application_id,
                source_payload=persistence_payload["application_source_payload"],
                source_payload_hash=persistence_payload[
                    "application_source_payload_hash"
                ],
                import_run_id=persistence_payload.get("import_run_id"),
                processed_at=persisted_at,
                sync_status="accepted",
            )

            current_company_id = _upsert_company_by_name(
                cursor,
                company_name=persistence_payload.get("current_employer"),
            )

            # Upsert the canonical person/candidate from the candidate snapshot
            # first because the application row depends on that canonical
            # candidate ID. This also means later application reruns converge on
            # the same person/candidate rows instead of fragmenting identity.
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

            job_id = _resolve_canonical_job_id(
                cursor,
                source_job_id=str(persistence_payload["source_job_id"]),
                fallback_job_title=persistence_payload.get("job_title"),
            )

            application_id = _upsert_application(
                cursor,
                source_record_id=application_source_record["id"],
                candidate_id=candidate_id,
                job_id=job_id,
                application_status=persistence_payload.get("application_status"),
                source=persistence_payload.get("source"),
                rating=persistence_payload.get("rating"),
                candidate_rating=persistence_payload.get("candidate_rating"),
                current_position=persistence_payload.get("current_position"),
                current_employer=persistence_payload.get("current_employer"),
                social_profiles=persistence_payload.get("social_profiles"),
                applied_at=persistence_payload.get("applied_at"),
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
            if current_company_id is not None:
                _ensure_source_record_link(
                    cursor,
                    source_record_id=candidate_source_record["id"],
                    company_id=current_company_id,
                )

            # Keep the application provenance explicit:
            # - it targets the canonical candidate
            # - it targets the canonical job
            # - it targets the canonical application relationship row
            _ensure_source_record_link(
                cursor,
                source_record_id=application_source_record["id"],
                candidate_id=candidate_id,
            )
            _ensure_source_record_link(
                cursor,
                source_record_id=application_source_record["id"],
                job_id=job_id,
            )
            _ensure_source_record_link(
                cursor,
                source_record_id=application_source_record["id"],
                application_id=application_id,
            )

        connection.commit()

    return _make_json_safe_summary(
        {
            "persisted_at": persisted_at.isoformat(),
            "tw_code": persistence_payload.get("tw_code"),
            "person_id": person_id,
            "candidate_id": candidate_id,
            "current_company_id": current_company_id,
            "job_id": job_id,
            "application_id": application_id,
            "candidate_source_record_id": candidate_source_record["id"],
            "application_source_record_id": application_source_record["id"],
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

    Example
    -------
    A call with:

        source_record_type="jobadder_application_snapshot"
        source_record_id="12204918"

    updates the latest accepted application snapshot for that upstream key
    instead of inserting a duplicate row on every rerun.
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
    Find or create the company row by exact case-insensitive name.

    Example
    -------
    A value such as:

        "Freelancing, UpWork"

    returns the existing `companies.id` for that case-insensitive match, or
    creates one new row when no match exists yet.
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
    Find or create the canonical person row for the supplied source record.

    Notes
    -----
    The lookup order is intentionally conservative:

    1. existing link from the source record
    2. existing person with the same LinkedIn URL
    3. existing person with the same primary email
    4. otherwise create a new person row

    Example
    -------
    If the candidate source record is not linked yet but the canonical schema
    already contains the same primary email, this helper reuses that person row
    instead of inserting a duplicate person.
    """

    existing_person_id = _find_linked_entity_id(
        cursor,
        source_record_id=source_record_id,
        entity_column="person_id",
    )

    if existing_person_id is None and linkedin_url is not None:
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

    if existing_person_id is None and primary_email is not None:
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
    Find or create the canonical candidate row for the supplied source record.

    Notes
    -----
    The lookup order is intentionally conservative:

    1. existing link from the source record
    2. existing candidate row for the resolved person
    3. otherwise create a new candidate row

    Example
    -------
    If the person already has a canonical candidate row, this helper refreshes
    that row rather than inserting a second candidate record for the same
    person.
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


def _resolve_canonical_job_id(
    cursor: Cursor[Any],
    *,
    source_job_id: str,
    fallback_job_title: str | None,
) -> str:
    """
    Resolve the canonical job row for one upstream JobAdder job ID.

    Notes
    -----
    This first applications persistence slice assumes the canonical job should
    already exist because the job/job-spec persistence proof runs first.

    The lookup order is therefore:

    1. canonical job linked to `jobadder_job` source record
    2. conservative title match fallback
    3. fail clearly

    Example
    -------
    For `tw398`, the helper resolves the canonical job through the persisted
    JobAdder job source record rather than trying to create a new job here.
    """

    cursor.execute(
        """
        select srl.job_id
        from source_records sr
        join source_record_links srl
          on srl.source_record_id = sr.id
        where sr.source_system = 'jobadder'
          and sr.source_record_type = 'jobadder_job'
          and sr.source_record_id = %(source_job_id)s
          and srl.job_id is not null
        limit 1
        """,
        {"source_job_id": source_job_id},
    )
    row = cursor.fetchone()
    if row is not None:
        return row["job_id"]

    if isinstance(fallback_job_title, str) and fallback_job_title.strip() != "":
        cursor.execute(
            """
            select id
            from jobs
            where lower(title) = lower(%(title)s)
            limit 1
            """,
            {"title": fallback_job_title.strip()},
        )
        row = cursor.fetchone()
        if row is not None:
            return row["id"]

    raise RuntimeError(
        f"Canonical job row was not found for JobAdder job {source_job_id}."
    )


def _upsert_application(
    cursor: Cursor[Any],
    *,
    source_record_id: str,
    candidate_id: str,
    job_id: str,
    application_status: str | None,
    source: str | None,
    rating: str | None,
    candidate_rating: str | None,
    current_position: str | None,
    current_employer: str | None,
    social_profiles: dict[str, Any] | None,
    applied_at: str | None,
) -> str:
    """
    Find or create the canonical application row for the supplied source record.

    Notes
    -----
    The lookup order is intentionally conservative:

    1. existing link from the application source record
    2. existing application row for the same candidate/job pair
    3. otherwise create a new application row

    The current schema is already unique on `(candidate_id, job_id)`, so that
    pair is the natural fallback identity when the explicit source link does
    not exist yet.

    Example
    -------
    If the same candidate applies to the same canonical job again through a
    rerun of this persistence slice, the existing application row is refreshed
    instead of duplicated.
    """

    existing_application_id = _find_linked_entity_id(
        cursor,
        source_record_id=source_record_id,
        entity_column="application_id",
    )

    if existing_application_id is None:
        cursor.execute(
            """
            select id
            from applications
            where candidate_id = %(candidate_id)s
              and job_id = %(job_id)s
            limit 1
            """,
            {
                "candidate_id": candidate_id,
                "job_id": job_id,
            },
        )
        row = cursor.fetchone()
        if row is not None:
            existing_application_id = row["id"]

    if existing_application_id is None:
        cursor.execute(
            """
            insert into applications (
                candidate_id,
                job_id,
                application_status,
                source,
                rating,
                candidate_rating,
                current_position,
                current_employer,
                social_profiles,
                applied_at
            )
            values (
                %(candidate_id)s,
                %(job_id)s,
                %(application_status)s,
                %(source)s,
                %(rating)s,
                %(candidate_rating)s,
                %(current_position)s,
                %(current_employer)s,
                %(social_profiles)s,
                %(applied_at)s
            )
            returning id
            """,
            {
                "candidate_id": candidate_id,
                "job_id": job_id,
                "application_status": application_status,
                "source": source,
                "rating": rating,
                "candidate_rating": candidate_rating,
                "current_position": current_position,
                "current_employer": current_employer,
                "social_profiles": Jsonb(social_profiles)
                if social_profiles is not None
                else None,
                "applied_at": applied_at,
            },
        )
        inserted_row = cursor.fetchone()
        if inserted_row is None:
            raise RuntimeError("Failed to create application row.")
        return inserted_row["id"]

    cursor.execute(
        """
        update applications
        set
            application_status = coalesce(
                %(application_status)s,
                application_status
            ),
            source = coalesce(%(source)s, source),
            rating = coalesce(%(rating)s, rating),
            candidate_rating = coalesce(
                %(candidate_rating)s,
                candidate_rating
            ),
            current_position = coalesce(
                %(current_position)s,
                current_position
            ),
            current_employer = coalesce(
                %(current_employer)s,
                current_employer
            ),
            social_profiles = coalesce(%(social_profiles)s, social_profiles),
            applied_at = coalesce(%(applied_at)s, applied_at)
        where id = %(application_id)s
        """,
        {
            "application_id": existing_application_id,
            "application_status": application_status,
            "source": source,
            "rating": rating,
            "candidate_rating": candidate_rating,
            "current_position": current_position,
            "current_employer": current_employer,
            "social_profiles": Jsonb(social_profiles)
            if social_profiles is not None
            else None,
            "applied_at": applied_at,
        },
    )
    return existing_application_id


def _find_linked_entity_id(
    cursor: Cursor[Any],
    *,
    source_record_id: str,
    entity_column: Literal[
        "person_id",
        "candidate_id",
        "company_id",
        "job_id",
        "application_id",
    ],
) -> str | None:
    """
    Return one linked canonical entity ID from `source_record_links`.

    Example
    -------
    A call with:

        entity_column="application_id"

    returns the application linked to that source record when such a link
    already exists, otherwise `None`.
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
    job_id: str | None = None,
    application_id: str | None = None,
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
        application_id="..."

    inserts one application-target link on the first accepted run and becomes a
    no-op on later identical reruns.
    """

    column_name, entity_id = _pick_single_entity_target(
        person_id=person_id,
        candidate_id=candidate_id,
        company_id=company_id,
        job_id=job_id,
        application_id=application_id,
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

    cursor.execute(
        """
        insert into source_record_links (
            source_record_id,
            person_id,
            candidate_id,
            company_id,
            job_id,
            application_id
        )
        values (
            %(source_record_id)s,
            %(person_id)s,
            %(candidate_id)s,
            %(company_id)s,
            %(job_id)s,
            %(application_id)s
        )
        """,
        {
            "source_record_id": source_record_id,
            "person_id": person_id,
            "candidate_id": candidate_id,
            "company_id": company_id,
            "job_id": job_id,
            "application_id": application_id,
        },
    )


def _pick_single_entity_target(
    *,
    person_id: str | None,
    candidate_id: str | None,
    company_id: str | None,
    job_id: str | None,
    application_id: str | None,
) -> tuple[str, str]:
    """
    Return the one non-null source-link target column and value.

    Example
    -------
    A call with only:

        application_id="application-uuid"

    returns:

        ("application_id", "application-uuid")
    """

    populated_targets = [
        ("person_id", person_id),
        ("candidate_id", candidate_id),
        ("company_id", company_id),
        ("job_id", job_id),
        ("application_id", application_id),
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


def _make_json_safe_summary(value: Any) -> Any:
    """
    Convert the persistence summary into JSON-safe plain Python types.

    Example
    -------
    A summary such as:

        {"application_id": UUID("...")}

    becomes:

        {"application_id": "..."}
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
    "persist_jobadder_application_snapshot",
]
