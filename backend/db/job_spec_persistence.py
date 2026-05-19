"""
Database helpers for persisting narrow JobAdder job and Dropbox job-spec data.

This module contains the first narrow write path for turning a confirmed
JobAdder job record plus one Dropbox job-spec document into canonical
Supabase/Postgres rows.

It gives the rest of the repository a stable way to talk about:

- saving a JobAdder job snapshot as a provenance-bearing source record
- saving a Dropbox job-spec file snapshot as a provenance-bearing source record
- upserting the linked company, job, and job-spec document rows
- linking those source records back to the canonical entities explicitly
- keeping direct SQL write logic out of service orchestration and operator
  scripts

Why this module exists
----------------------
We now have enough live evidence to stop treating jobs and job specs as
abstract future entities.

For `tw398`, we have already proved all of the following:

- JobAdder has a real job record
- JobAdder applications carry the same vacancy context
- Dropbox contains the matching job-spec PDF
- Dropbox `.eml` files preserve advert-response provenance
- Dropbox CV files can mirror the JobAdder candidate attachments exactly

That changes the next question:

    "How do we persist one real job/opportunity plus one real job-spec
    document into the canonical schema without making scripts own raw SQL?"

This module is the answer to that narrow question.

Important scope boundary
------------------------
This is intentionally not the full job-ingestion system.

It does not attempt to:

- sync every JobAdder job field exhaustively
- chunk the job spec into embeddings yet
- infer or persist required skills yet
- ingest applications or candidates through the same path yet
- formalise the final source-of-truth policy for every job-related field

Instead, it implements the smallest reliable write slice already justified by
the current evidence:

- one JobAdder job source record
- one Dropbox job-spec source record
- one canonical company
- one canonical job
- one canonical `job_spec` document
- the provenance and domain links between them

Example
-------
Typical service usage looks like:

    from backend.db.job_spec_persistence import (
        persist_jobadder_job_spec_snapshot,
    )

    summary = persist_jobadder_job_spec_snapshot(persistence_payload)

    print(summary["job_id"])
    print(summary["document_id"])
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID

from psycopg import Cursor
from psycopg.types.json import Jsonb

from backend.db.connection import postgres_connection

SourceRecordType = Literal[
    "jobadder_job",
    "dropbox_job_spec_document",
]


def persist_jobadder_job_spec_snapshot(
    persistence_payload: dict[str, Any],
) -> dict[str, Any]:
    """
    Persist one JobAdder job plus one Dropbox job-spec document snapshot.

    Parameters
    ----------
    persistence_payload : dict[str, Any]
        Normalised payload prepared by the service layer.

        The payload should already contain:

        - JobAdder job identifiers and canonical fields
        - Dropbox job-spec file identifiers and extracted text
        - source payloads for provenance
        - stable source payload hashes

    Returns
    -------
    dict[str, Any]
        Small persistence summary containing the canonical IDs and important
        source-record IDs written by the transaction.

    Notes
    -----
    This helper keeps the write path transaction-scoped and explicit.

    The transaction currently persists:

    - one JobAdder job source record
    - one Dropbox job-spec source record
    - zero or one company
    - one canonical job
    - one canonical `job_spec` document

    The two source records are intentionally kept separate because they answer
    different provenance questions later:

    - what structured upstream job/opportunity did we ingest?
    - what file-level job specification did we pair with it?

    Example
    -------
    Persisting a prepared payload returns a summary such as:

        {
            "company_id": "...",
            "job_id": "...",
            "document_id": "...",
            "job_source_record_id": "...",
            "job_spec_source_record_id": "...",
        }
    """

    source_job_id = str(persistence_payload["source_job_id"])
    source_job_spec_path = str(persistence_payload["job_spec_source_uri"])
    persisted_at = datetime.now(timezone.utc)

    with postgres_connection() as connection:
        with connection.cursor() as cursor:
            # Keep the structured JobAdder job payload and the Dropbox job-spec
            # payload as separate source records. That split lets later
            # debugging answer both:
            # - "which upstream job record drove this canonical job?"
            # - "which physical document file supplied this job-spec text?"
            job_source_record = _upsert_source_record(
                cursor,
                source_system="jobadder",
                source_record_type="jobadder_job",
                source_record_id=source_job_id,
                source_payload=persistence_payload["job_source_payload"],
                source_payload_hash=persistence_payload["job_source_payload_hash"],
                import_run_id=persistence_payload.get("import_run_id"),
                processed_at=persisted_at,
                sync_status="accepted",
            )

            job_spec_source_record = _upsert_source_record(
                cursor,
                source_system="dropbox",
                source_record_type="dropbox_job_spec_document",
                source_record_id=source_job_spec_path,
                source_payload=persistence_payload["job_spec_source_payload"],
                source_payload_hash=persistence_payload[
                    "job_spec_source_payload_hash"
                ],
                import_run_id=persistence_payload.get("import_run_id"),
                processed_at=persisted_at,
                sync_status="accepted",
            )

            company_id = _upsert_company_by_name(
                cursor,
                company_name=persistence_payload.get("company_name"),
            )

            # Upsert the canonical job after the JobAdder source record exists
            # so we can use prior source links first and only fall back to a
            # conservative natural-key lookup second.
            job_id = _upsert_job(
                cursor,
                source_record_id=job_source_record["id"],
                company_id=company_id,
                title=persistence_payload["job_title"],
                description=persistence_payload.get("job_description"),
                location=persistence_payload.get("job_location"),
                workplace_type=persistence_payload.get("workplace_type"),
                employment_type=persistence_payload.get("employment_type"),
                work_type=persistence_payload.get("work_type"),
                source=persistence_payload.get("source"),
                owner_name=persistence_payload.get("owner_name"),
                salary_min=persistence_payload.get("salary_min"),
                salary_max=persistence_payload.get("salary_max"),
                currency=persistence_payload.get("currency"),
                status=persistence_payload.get("status"),
                opened_at=persistence_payload.get("opened_at"),
                closed_at=persistence_payload.get("closed_at"),
                updated_from_source_at=persistence_payload.get(
                    "updated_from_source_at"
                ),
            )

            document_id = _upsert_job_spec_document(
                cursor,
                source_record_id=job_spec_source_record["id"],
                document_title=persistence_payload.get("job_spec_title"),
                mime_type=persistence_payload.get("job_spec_mime_type"),
                source_uri=persistence_payload.get("job_spec_source_uri"),
                content_hash=persistence_payload.get("job_spec_content_hash"),
                extracted_text=persistence_payload.get("job_spec_extracted_text"),
            )

            # Keep one source-record link per canonical target. That makes
            # idempotency checks simple and keeps provenance inspection
            # readable when operators need to understand what was linked.
            _ensure_source_record_link(
                cursor,
                source_record_id=job_source_record["id"],
                job_id=job_id,
            )
            if company_id is not None:
                _ensure_source_record_link(
                    cursor,
                    source_record_id=job_source_record["id"],
                    company_id=company_id,
                )

            _ensure_source_record_link(
                cursor,
                source_record_id=job_spec_source_record["id"],
                job_id=job_id,
            )
            _ensure_source_record_link(
                cursor,
                source_record_id=job_spec_source_record["id"],
                document_id=document_id,
            )

            # `document_links` capture the domain relationship:
            # "this document is the job specification for this job".
            # That is a different question from the provenance graph.
            _ensure_document_link(
                cursor,
                document_id=document_id,
                job_id=job_id,
                relationship_type="job_spec",
                source_record_id=job_spec_source_record["id"],
            )

        connection.commit()

    return _make_json_safe_summary(
        {
            "persisted_at": persisted_at.isoformat(),
            "tw_code": persistence_payload.get("tw_code"),
            "company_id": company_id,
            "job_id": job_id,
            "document_id": document_id,
            "job_source_record_id": job_source_record["id"],
            "job_spec_source_record_id": job_spec_source_record["id"],
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
    snapshot for both:

    - one upstream JobAdder job
    - one upstream Dropbox file

    without creating duplicate rows on every rerun.

    Example
    -------
    A call with:

        source_record_type="jobadder_job"
        source_record_id="936462"

    updates the latest accepted JobAdder job snapshot for that upstream job key
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

    Notes
    -----
    This remains deliberately narrow.

    We are only using the confirmed company name from the JobAdder job record
    at this stage because broader company reconciliation still depends on later
    source-system design work.

    Example
    -------
    A value such as:

        "B2C2"

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


def _upsert_job(
    cursor: Cursor[Any],
    *,
    source_record_id: str,
    company_id: str | None,
    title: str,
    description: str | None,
    location: str | None,
    workplace_type: str | None,
    employment_type: str | None,
    work_type: str | None,
    source: str | None,
    owner_name: str | None,
    salary_min: Decimal | None,
    salary_max: Decimal | None,
    currency: str | None,
    status: str | None,
    opened_at: str | None,
    closed_at: str | None,
    updated_from_source_at: str | None,
) -> str:
    """
    Find or create the canonical job row for the supplied JobAdder source record.

    Notes
    -----
    The lookup order is intentionally conservative:

    1. existing link from the JobAdder source record
    2. existing job row with the same title and company
    3. otherwise create a new job row

    That keeps the first write slice narrow while still avoiding obvious
    duplicate canonical jobs on rerun.

    Example
    -------
    If the JobAdder source record is not linked yet but the canonical schema
    already contains:

        company = "B2C2"
        title = "tw398 - KDB Developer"

    then that existing job row is reused instead of inserting a duplicate.
    """

    existing_job_id = _find_linked_entity_id(
        cursor,
        source_record_id=source_record_id,
        entity_column="job_id",
    )

    if existing_job_id is None and company_id is not None:
        cursor.execute(
            """
            select id
            from jobs
            where company_id = %(company_id)s
              and lower(title) = lower(%(title)s)
            limit 1
            """,
            {
                "company_id": company_id,
                "title": title,
            },
        )
        row = cursor.fetchone()
        if row is not None:
            existing_job_id = row["id"]

    if existing_job_id is None:
        cursor.execute(
            """
            insert into jobs (
                company_id,
                title,
                description,
                location,
                workplace_type,
                employment_type,
                work_type,
                source,
                owner_name,
                salary_min,
                salary_max,
                currency,
                status,
                opened_at,
                closed_at,
                updated_from_source_at
            )
            values (
                %(company_id)s,
                %(title)s,
                %(description)s,
                %(location)s,
                %(workplace_type)s,
                %(employment_type)s,
                %(work_type)s,
                %(source)s,
                %(owner_name)s,
                %(salary_min)s,
                %(salary_max)s,
                %(currency)s,
                %(status)s,
                %(opened_at)s,
                %(closed_at)s,
                %(updated_from_source_at)s
            )
            returning id
            """,
            {
                "company_id": company_id,
                "title": title,
                "description": description,
                "location": location,
                "workplace_type": workplace_type,
                "employment_type": employment_type,
                "work_type": work_type,
                "source": source,
                "owner_name": owner_name,
                "salary_min": salary_min,
                "salary_max": salary_max,
                "currency": currency,
                "status": status,
                "opened_at": opened_at,
                "closed_at": closed_at,
                "updated_from_source_at": updated_from_source_at,
            },
        )
        inserted_row = cursor.fetchone()
        if inserted_row is None:
            raise RuntimeError("Failed to create job row.")
        return inserted_row["id"]

    cursor.execute(
        """
        update jobs
        set
            company_id = coalesce(%(company_id)s, company_id),
            title = %(title)s,
            description = coalesce(%(description)s, description),
            location = coalesce(%(location)s, location),
            workplace_type = coalesce(%(workplace_type)s, workplace_type),
            employment_type = coalesce(%(employment_type)s, employment_type),
            work_type = coalesce(%(work_type)s, work_type),
            source = coalesce(%(source)s, source),
            owner_name = coalesce(%(owner_name)s, owner_name),
            salary_min = coalesce(%(salary_min)s, salary_min),
            salary_max = coalesce(%(salary_max)s, salary_max),
            currency = coalesce(%(currency)s, currency),
            status = coalesce(%(status)s, status),
            opened_at = coalesce(%(opened_at)s, opened_at),
            closed_at = coalesce(%(closed_at)s, closed_at),
            updated_from_source_at = coalesce(
                %(updated_from_source_at)s,
                updated_from_source_at
            )
        where id = %(job_id)s
        """,
        {
            "job_id": existing_job_id,
            "company_id": company_id,
            "title": title,
            "description": description,
            "location": location,
            "workplace_type": workplace_type,
            "employment_type": employment_type,
            "work_type": work_type,
            "source": source,
            "owner_name": owner_name,
            "salary_min": salary_min,
            "salary_max": salary_max,
            "currency": currency,
            "status": status,
            "opened_at": opened_at,
            "closed_at": closed_at,
            "updated_from_source_at": updated_from_source_at,
        },
    )
    return existing_job_id


def _upsert_job_spec_document(
    cursor: Cursor[Any],
    *,
    source_record_id: str,
    document_title: str | None,
    mime_type: str | None,
    source_uri: str | None,
    content_hash: str | None,
    extracted_text: str | None,
) -> str:
    """
    Find or create the canonical job-spec document row.

    Notes
    -----
    The Dropbox source-record link is treated as the primary identity when
    possible. If a document has not yet been linked to that source record, we
    fall back to the content hash to avoid obvious duplicate document rows for
    the same job spec.

    Example
    -------
    If the Dropbox file path changes later but the downloaded PDF is still the
    same document text, the `content_hash` path lets this helper reuse the
    existing canonical `job_spec` document row instead of inserting a
    duplicate.
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
            where document_type = 'job_spec'
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
                'job_spec',
                %(title)s,
                %(source_uri)s,
                %(mime_type)s,
                %(content_hash)s,
                %(extracted_text)s
            )
            returning id
            """,
            {
                "title": document_title,
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
            "title": document_title,
            "source_uri": source_uri,
            "mime_type": mime_type,
            "content_hash": content_hash,
            "extracted_text": extracted_text,
        },
    )
    return existing_document_id


def _find_linked_entity_id(
    cursor: Cursor[Any],
    *,
    source_record_id: str,
    entity_column: Literal[
        "company_id",
        "job_id",
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

        entity_column="job_id"

    returns the job linked to that source record when such a link already
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
    company_id: str | None = None,
    job_id: str | None = None,
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
        job_id="..."

    inserts one job-target link on the first accepted run and becomes a no-op
    on later identical reruns.
    """

    column_name, entity_id = _pick_single_entity_target(
        company_id=company_id,
        job_id=job_id,
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

    cursor.execute(
        """
        insert into source_record_links (
            source_record_id,
            company_id,
            job_id,
            document_id
        )
        values (
            %(source_record_id)s,
            %(company_id)s,
            %(job_id)s,
            %(document_id)s
        )
        """,
        {
            "source_record_id": source_record_id,
            "company_id": company_id,
            "job_id": job_id,
            "document_id": document_id,
        },
    )


def _ensure_document_link(
    cursor: Cursor[Any],
    *,
    document_id: str,
    relationship_type: str,
    source_record_id: str | None,
    job_id: str | None = None,
) -> None:
    """
    Insert one `document_links` row only when it does not already exist.

    Notes
    -----
    `document_links` capture domain relationships such as
    "this job-spec document belongs to this job" independently of the broader
    provenance graph recorded in `source_record_links`.

    Example
    -------
    A call with:

        document_id="..."
        job_id="..."
        relationship_type="job_spec"

    creates one job-spec link and then becomes idempotent on later reruns.
    """

    column_name, entity_id = _pick_single_document_target(job_id=job_id)

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
            job_id,
            source_record_id,
            relationship_type
        )
        values (
            %(document_id)s,
            %(job_id)s,
            %(source_record_id)s,
            %(relationship_type)s
        )
        """,
        {
            "document_id": document_id,
            "job_id": job_id,
            "source_record_id": source_record_id,
            "relationship_type": relationship_type,
        },
    )


def _pick_single_entity_target(
    *,
    company_id: str | None,
    job_id: str | None,
    document_id: str | None,
) -> tuple[str, str]:
    """
    Return the one non-null source-link target column and value.

    Example
    -------
    A call with only:

        job_id="job-uuid"

    returns:

        ("job_id", "job-uuid")
    """

    populated_targets = [
        ("company_id", company_id),
        ("job_id", job_id),
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


def _pick_single_document_target(*, job_id: str | None) -> tuple[str, str]:
    """
    Return the one non-null document-link target column and value.

    Example
    -------
    A call with only:

        job_id="job-uuid"

    returns:

        ("job_id", "job-uuid")
    """

    populated_targets = [
        ("job_id", job_id),
    ]
    resolved_targets = [
        (column_name, value)
        for column_name, value in populated_targets
        if value is not None
    ]
    if len(resolved_targets) != 1:
        raise ValueError(
            "Expected exactly one job target when inserting a document link."
        )
    return resolved_targets[0]


def _make_json_safe_summary(value: Any) -> Any:
    """
    Convert the persistence summary into JSON-safe plain Python types.

    Notes
    -----
    `psycopg` returns native Python objects for Postgres columns, including
    `uuid.UUID` values and `Decimal` salary values. That is useful inside the
    transaction, but the operator-facing scripts later write the returned
    summary directly to JSON.

    Example
    -------
    A summary such as:

        {"job_id": UUID("..."), "salary_min": Decimal("125000")}

    becomes:

        {"job_id": "...", "salary_min": "125000"}
    """

    if isinstance(value, UUID):
        return str(value)

    if isinstance(value, Decimal):
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
    "persist_jobadder_job_spec_snapshot",
]
