"""
Database helpers for persisting narrow Recruiterflow job and candidate snapshots.

This module contains the first bounded write path for turning Recruiterflow ZIP
export records into canonical Supabase/Postgres rows.

It gives the rest of the repository a stable way to talk about:

- saving Recruiterflow job snapshots as provenance-bearing source records
- saving Recruiterflow candidate snapshots as provenance-bearing source records
- saving candidate-job relationship snapshots from nested Recruiterflow payloads
- upserting the linked company, person, candidate, job, and application rows
- keeping direct SQL write logic out of importer scripts

Important scope boundary
------------------------
This is intentionally not the full Recruiterflow ingestion system.

It does not attempt to:

- import every Recruiterflow entity type yet
- download candidate or job file attachments yet
- infer skills or chunk documents yet
- model every nested relationship exhaustively

Instead, it implements the smallest write slice already justified by the
archive inspection work:

- one Recruiterflow job source record
- one Recruiterflow candidate source record
- zero or more candidate-job application-link source records
- one canonical job per source job
- one canonical person and candidate per source candidate
- one canonical application per resolved candidate/job pair
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from psycopg import Cursor
from psycopg.types.json import Jsonb

from backend.db.application_persistence import (
    _make_json_safe_summary,
    _upsert_application,
    _upsert_candidate,
    _upsert_company_by_name,
    _upsert_person,
)
from backend.db.connection import postgres_connection
from backend.db.job_spec_persistence import _upsert_job

SourceRecordType = Literal[
    "recruiterflow_job",
    "recruiterflow_candidate",
    "recruiterflow_candidate_job_link",
    "recruiterflow_candidate_file_reference",
    "recruiterflow_candidate_file_content",
    "recruiterflow_job_file_reference",
]


def persist_recruiterflow_job_snapshot(
    persistence_payload: dict[str, Any],
) -> dict[str, Any]:
    """
    Persist one Recruiterflow job snapshot.

    Parameters
    ----------
    persistence_payload : dict[str, Any]
        Normalized payload prepared by the Recruiterflow service layer.

    Returns
    -------
    dict[str, Any]
        Small persistence summary containing the canonical IDs and provenance ID
        written by the transaction.

    Example
    -------
    Persisting a prepared payload returns a summary such as:

        {
            "job_id": "...",
            "job_source_record_id": "...",
            "tw_code": "tw337",
        }
    """

    source_job_id = str(persistence_payload["source_job_id"])
    persisted_at = datetime.now(timezone.utc)

    with postgres_connection() as connection:
        with connection.cursor() as cursor:
            job_source_record = _upsert_source_record(
                cursor,
                source_system="recruiterflow",
                source_record_type="recruiterflow_job",
                source_record_id=source_job_id,
                source_payload=persistence_payload["job_source_payload"],
                source_payload_hash=persistence_payload["job_source_payload_hash"],
                import_run_id=persistence_payload.get("import_run_id"),
                processed_at=persisted_at,
                sync_status="accepted",
            )

            company_id = _upsert_company_by_name(
                cursor,
                company_name=persistence_payload.get("company_name"),
            )

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

        connection.commit()

    return _make_json_safe_summary(
        {
            "persisted_at": persisted_at.isoformat(),
            "tw_code": persistence_payload.get("tw_code"),
            "company_id": company_id,
            "job_id": job_id,
            "job_source_record_id": job_source_record["id"],
        }
    )


def persist_recruiterflow_candidate_snapshot(
    persistence_payload: dict[str, Any],
) -> dict[str, Any]:
    """
    Persist one Recruiterflow candidate snapshot plus any resolvable job links.

    Parameters
    ----------
    persistence_payload : dict[str, Any]
        Normalized payload prepared by the Recruiterflow service layer.

    Returns
    -------
    dict[str, Any]
        Small persistence summary containing the canonical IDs, provenance IDs,
        and job-link resolution counts written by the transaction.

    Example
    -------
    Persisting a prepared payload returns a summary such as:

        {
            "candidate_id": "...",
            "resolved_application_count": 2,
            "unresolved_job_links": [{"source_job_id": 999}],
        }
    """

    source_candidate_id = str(persistence_payload["source_candidate_id"])
    persisted_at = datetime.now(timezone.utc)
    resolved_application_ids: list[str] = []
    unresolved_job_links: list[dict[str, Any]] = []

    with postgres_connection() as connection:
        with connection.cursor() as cursor:
            candidate_source_record = _upsert_source_record(
                cursor,
                source_system="recruiterflow",
                source_record_type="recruiterflow_candidate",
                source_record_id=source_candidate_id,
                source_payload=persistence_payload["candidate_source_payload"],
                source_payload_hash=persistence_payload["candidate_source_payload_hash"],
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

            for job_link in persistence_payload.get("job_links", []):
                try:
                    job_id = _resolve_recruiterflow_job_id(
                        cursor,
                        source_job_id=str(job_link["source_job_id"]),
                        fallback_job_title=job_link.get("job_title"),
                    )
                except RuntimeError:
                    unresolved_job_links.append(
                        {
                            "source_job_id": job_link.get("source_job_id"),
                            "job_title": job_link.get("job_title"),
                        }
                    )
                    continue

                application_source_record = _upsert_source_record(
                    cursor,
                    source_system="recruiterflow",
                    source_record_type="recruiterflow_candidate_job_link",
                    source_record_id=str(job_link["source_record_id"]),
                    source_payload=job_link["source_payload"],
                    source_payload_hash=job_link["source_payload_hash"],
                    import_run_id=persistence_payload.get("import_run_id"),
                    processed_at=persisted_at,
                    sync_status="accepted",
                )

                application_id = _upsert_application(
                    cursor,
                    source_record_id=application_source_record["id"],
                    candidate_id=candidate_id,
                    job_id=job_id,
                    application_status=job_link.get("application_status"),
                    source=job_link.get("source"),
                    rating=None,
                    candidate_rating=None,
                    current_position=persistence_payload.get("current_title"),
                    current_employer=persistence_payload.get("current_employer"),
                    social_profiles=persistence_payload.get("social_profiles"),
                    applied_at=job_link.get("applied_at"),
                )

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

                resolved_application_ids.append(application_id)

        connection.commit()

    return _make_json_safe_summary(
        {
            "persisted_at": persisted_at.isoformat(),
            "tw_code": persistence_payload.get("tw_code"),
            "person_id": person_id,
            "candidate_id": candidate_id,
            "current_company_id": current_company_id,
            "candidate_source_record_id": candidate_source_record["id"],
            "resolved_application_count": len(resolved_application_ids),
            "resolved_application_ids": resolved_application_ids,
            "unresolved_job_link_count": len(unresolved_job_links),
            "unresolved_job_links": unresolved_job_links,
        }
    )


def persist_recruiterflow_candidate_file_reference(
    persistence_payload: dict[str, Any],
) -> dict[str, Any]:
    """
    Persist one Recruiterflow candidate file as a canonical document reference.

    Parameters
    ----------
    persistence_payload : dict[str, Any]
        Normalized payload prepared by the Recruiterflow service layer.

    Returns
    -------
    dict[str, Any]
        Small persistence summary containing the resolved candidate, document,
        and provenance IDs written by the transaction.

    Example
    -------
    Persisting a prepared payload returns a summary such as:

        {
            "candidate_id": "...",
            "document_id": "...",
            "candidate_file_source_record_id": "...",
        }
    """

    persisted_at = datetime.now(timezone.utc)
    source_candidate_id = str(persistence_payload["source_candidate_id"])
    source_file_record_id = str(persistence_payload["source_file_record_id"])

    with postgres_connection() as connection:
        with connection.cursor() as cursor:
            candidate_id = _resolve_recruiterflow_candidate_id(
                cursor,
                source_candidate_id=source_candidate_id,
            )

            candidate_file_source_record = _upsert_source_record(
                cursor,
                source_system="recruiterflow",
                source_record_type="recruiterflow_candidate_file_reference",
                source_record_id=source_file_record_id,
                source_payload=persistence_payload["candidate_file_source_payload"],
                source_payload_hash=persistence_payload[
                    "candidate_file_source_payload_hash"
                ],
                import_run_id=persistence_payload.get("import_run_id"),
                processed_at=persisted_at,
                sync_status="accepted",
            )

            document_id = _upsert_reference_document(
                cursor,
                source_record_id=candidate_file_source_record["id"],
                document_type="candidate_attachment",
                document_title=persistence_payload.get("document_title"),
                mime_type=persistence_payload.get("mime_type"),
                source_uri=persistence_payload.get("source_uri"),
                content_hash=persistence_payload.get("content_hash"),
            )

            _ensure_source_record_link(
                cursor,
                source_record_id=candidate_file_source_record["id"],
                candidate_id=candidate_id,
            )
            _ensure_source_record_link(
                cursor,
                source_record_id=candidate_file_source_record["id"],
                document_id=document_id,
            )
            _ensure_document_link(
                cursor,
                document_id=document_id,
                candidate_id=candidate_id,
                relationship_type="candidate_file_reference",
                source_record_id=candidate_file_source_record["id"],
            )

        connection.commit()

    return _make_json_safe_summary(
        {
            "persisted_at": persisted_at.isoformat(),
            "source_candidate_id": source_candidate_id,
            "source_file_record_id": source_file_record_id,
            "candidate_id": candidate_id,
            "document_id": document_id,
            "candidate_file_source_record_id": candidate_file_source_record["id"],
        }
    )


def persist_recruiterflow_job_file_reference(
    persistence_payload: dict[str, Any],
) -> dict[str, Any]:
    """
    Persist one Recruiterflow job file as a canonical document reference.

    Parameters
    ----------
    persistence_payload : dict[str, Any]
        Normalized payload prepared by the Recruiterflow service layer.

    Returns
    -------
    dict[str, Any]
        Small persistence summary containing the resolved job, document, and
        provenance IDs written by the transaction.

    Example
    -------
    Persisting a prepared payload returns a summary such as:

        {
            "job_id": "...",
            "document_id": "...",
            "job_file_source_record_id": "...",
        }
    """

    persisted_at = datetime.now(timezone.utc)
    source_job_id = str(persistence_payload["source_job_id"])
    source_file_record_id = str(persistence_payload["source_file_record_id"])

    with postgres_connection() as connection:
        with connection.cursor() as cursor:
            job_id = _resolve_recruiterflow_job_id(
                cursor,
                source_job_id=source_job_id,
                fallback_job_title=persistence_payload.get("job_title"),
            )

            job_file_source_record = _upsert_source_record(
                cursor,
                source_system="recruiterflow",
                source_record_type="recruiterflow_job_file_reference",
                source_record_id=source_file_record_id,
                source_payload=persistence_payload["job_file_source_payload"],
                source_payload_hash=persistence_payload["job_file_source_payload_hash"],
                import_run_id=persistence_payload.get("import_run_id"),
                processed_at=persisted_at,
                sync_status="accepted",
            )

            document_id = _upsert_reference_document(
                cursor,
                source_record_id=job_file_source_record["id"],
                document_type="job_attachment",
                document_title=persistence_payload.get("document_title"),
                mime_type=persistence_payload.get("mime_type"),
                source_uri=persistence_payload.get("source_uri"),
                content_hash=persistence_payload.get("content_hash"),
            )

            _ensure_source_record_link(
                cursor,
                source_record_id=job_file_source_record["id"],
                job_id=job_id,
            )
            _ensure_source_record_link(
                cursor,
                source_record_id=job_file_source_record["id"],
                document_id=document_id,
            )
            _ensure_document_link(
                cursor,
                document_id=document_id,
                job_id=job_id,
                relationship_type="job_file_reference",
                source_record_id=job_file_source_record["id"],
            )

        connection.commit()

    return _make_json_safe_summary(
        {
            "persisted_at": persisted_at.isoformat(),
            "source_job_id": source_job_id,
            "source_file_record_id": source_file_record_id,
            "job_id": job_id,
            "document_id": document_id,
            "job_file_source_record_id": job_file_source_record["id"],
        }
    )


def persist_recruiterflow_candidate_file_content(
    persistence_payload: dict[str, Any],
) -> dict[str, Any]:
    """
    Persist one Recruiterflow candidate file download/extraction attempt.

    Parameters
    ----------
    persistence_payload : dict[str, Any]
        Normalized payload prepared by the Recruiterflow service layer.

    Returns
    -------
    dict[str, Any]
        Small persistence summary containing the resolved candidate, document,
        content-source record, and extraction status values.

    Example
    -------
    Persisting a prepared payload returns a summary such as:

        {
            "candidate_id": "...",
            "document_id": "...",
            "sync_status": "extracted",
            "character_count": 6185,
        }
    """

    persisted_at = datetime.now(timezone.utc)
    source_candidate_id = str(persistence_payload["source_candidate_id"])
    source_file_record_id = str(persistence_payload["source_file_record_id"])

    with postgres_connection() as connection:
        with connection.cursor() as cursor:
            candidate_id = _resolve_recruiterflow_candidate_id(
                cursor,
                source_candidate_id=source_candidate_id,
            )
            reference_source_record_id = _resolve_source_record_uuid(
                cursor,
                source_system="recruiterflow",
                source_record_type="recruiterflow_candidate_file_reference",
                source_record_id=source_file_record_id,
            )
            document_id = _find_linked_entity_id(
                cursor,
                source_record_id=reference_source_record_id,
                entity_column="document_id",
            )

            content_source_record = _upsert_source_record(
                cursor,
                source_system="recruiterflow",
                source_record_type="recruiterflow_candidate_file_content",
                source_record_id=source_file_record_id,
                source_payload=persistence_payload["candidate_file_content_source_payload"],
                source_payload_hash=persistence_payload[
                    "candidate_file_content_source_payload_hash"
                ],
                import_run_id=persistence_payload.get("import_run_id"),
                processed_at=persisted_at,
                sync_status=persistence_payload["sync_status"],
                error_message=persistence_payload.get("error_message"),
            )

            if document_id is None:
                document_id = _upsert_reference_document(
                    cursor,
                    source_record_id=reference_source_record_id,
                    document_type="candidate_attachment",
                    document_title=persistence_payload.get("document_title"),
                    mime_type=persistence_payload.get("mime_type"),
                    source_uri=persistence_payload.get("source_uri"),
                    content_hash=persistence_payload.get("content_hash"),
                )

            _update_document_content(
                cursor,
                document_id=document_id,
                document_title=persistence_payload.get("document_title"),
                mime_type=persistence_payload.get("mime_type"),
                source_uri=persistence_payload.get("source_uri"),
                content_hash=persistence_payload.get("content_hash"),
                extracted_text=persistence_payload.get("extracted_text"),
            )

            _ensure_source_record_link(
                cursor,
                source_record_id=content_source_record["id"],
                candidate_id=candidate_id,
            )
            _ensure_source_record_link(
                cursor,
                source_record_id=content_source_record["id"],
                document_id=document_id,
            )

        connection.commit()

    return _make_json_safe_summary(
        {
            "persisted_at": persisted_at.isoformat(),
            "source_candidate_id": source_candidate_id,
            "source_file_record_id": source_file_record_id,
            "candidate_id": candidate_id,
            "document_id": document_id,
            "candidate_file_content_source_record_id": content_source_record["id"],
            "sync_status": persistence_payload["sync_status"],
            "character_count": persistence_payload.get("character_count"),
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
    error_message: str | None = None,
) -> dict[str, Any]:
    """
    Insert or replace one provenance-bearing source record row.

    Example
    -------
    A call with:

        source_record_type="recruiterflow_candidate"
        source_record_id="4847"

    updates the latest accepted Recruiterflow candidate snapshot for that
    upstream key instead of inserting a duplicate row on every rerun.
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
            %(error_message)s
        )
        on conflict (source_system, source_record_type, source_record_id)
        do update set
            source_payload = excluded.source_payload,
            source_payload_hash = excluded.source_payload_hash,
            import_run_id = excluded.import_run_id,
            processed_at = excluded.processed_at,
            sync_status = excluded.sync_status,
            error_message = excluded.error_message
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
            "error_message": error_message,
        },
    )
    row = cursor.fetchone()
    if row is None:
        raise RuntimeError("Failed to upsert source record.")
    return dict(row)


def _resolve_recruiterflow_job_id(
    cursor: Cursor[Any],
    *,
    source_job_id: str,
    fallback_job_title: str | None,
) -> str:
    """
    Resolve the canonical job row for one upstream Recruiterflow job ID.

    Example
    -------
    For a Recruiterflow job link such as `job_id=102`, this helper resolves the
    canonical job through the persisted `recruiterflow_job` source record first.
    """

    cursor.execute(
        """
        select srl.job_id
        from source_records sr
        join source_record_links srl
          on srl.source_record_id = sr.id
        where sr.source_system = 'recruiterflow'
          and sr.source_record_type = 'recruiterflow_job'
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
        f"Canonical job row was not found for Recruiterflow job {source_job_id}."
    )


def _resolve_recruiterflow_candidate_id(
    cursor: Cursor[Any],
    *,
    source_candidate_id: str,
) -> str:
    """
    Resolve the canonical candidate row for one upstream Recruiterflow candidate ID.

    Example
    -------
    For a Recruiterflow candidate file reference such as `candidate_id=4847`,
    this helper resolves the canonical candidate through the persisted
    `recruiterflow_candidate` source record.
    """

    cursor.execute(
        """
        select srl.candidate_id
        from source_records sr
        join source_record_links srl
          on srl.source_record_id = sr.id
        where sr.source_system = 'recruiterflow'
          and sr.source_record_type = 'recruiterflow_candidate'
          and sr.source_record_id = %(source_candidate_id)s
          and srl.candidate_id is not null
        limit 1
        """,
        {"source_candidate_id": source_candidate_id},
    )
    row = cursor.fetchone()
    if row is not None:
        return row["candidate_id"]

    raise RuntimeError(
        "Canonical candidate row was not found for Recruiterflow candidate "
        f"{source_candidate_id}."
    )


def _resolve_source_record_uuid(
    cursor: Cursor[Any],
    *,
    source_system: str,
    source_record_type: SourceRecordType,
    source_record_id: str,
) -> str:
    """
    Resolve one `source_records.id` UUID from the external natural key.

    Example
    -------
    A call with:

        source_record_type="recruiterflow_candidate_file_reference"

    returns the canonical source-record UUID for that upstream reference row.
    """

    cursor.execute(
        """
        select id
        from source_records
        where source_system = %(source_system)s
          and source_record_type = %(source_record_type)s
          and source_record_id = %(source_record_id)s
        limit 1
        """,
        {
            "source_system": source_system,
            "source_record_type": source_record_type,
            "source_record_id": source_record_id,
        },
    )
    row = cursor.fetchone()
    if row is None:
        raise RuntimeError(
            "Source record was not found for "
            f"{source_system}:{source_record_type}:{source_record_id}."
        )
    return row["id"]


def _upsert_reference_document(
    cursor: Cursor[Any],
    *,
    source_record_id: str,
    document_type: str,
    document_title: str | None,
    mime_type: str | None,
    source_uri: str | None,
    content_hash: str | None,
) -> str:
    """
    Find or create one canonical document row for a file reference.

    Notes
    -----
    These rows are deliberately lightweight. The Recruiterflow file metadata is
    useful immediately for operator visibility and later byte-download work,
    even before we have extracted text.

    Example
    -------
    A candidate file with filename `Alice CV.pdf` and link `https://...` can
    become one `candidate_attachment` document row without downloading the
    actual PDF bytes yet.
    """

    existing_document_id = _find_linked_entity_id(
        cursor,
        source_record_id=source_record_id,
        entity_column="document_id",
    )

    if existing_document_id is None and source_uri:
        cursor.execute(
            """
            select id
            from documents
            where document_type = %(document_type)s
              and source_uri = %(source_uri)s
            limit 1
            """,
            {
                "document_type": document_type,
                "source_uri": source_uri,
            },
        )
        row = cursor.fetchone()
        if row is not None:
            existing_document_id = row["id"]

    if existing_document_id is None and content_hash:
        cursor.execute(
            """
            select id
            from documents
            where document_type = %(document_type)s
              and content_hash = %(content_hash)s
            limit 1
            """,
            {
                "document_type": document_type,
                "content_hash": content_hash,
            },
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
                %(document_type)s,
                %(title)s,
                %(source_uri)s,
                %(mime_type)s,
                %(content_hash)s,
                null
            )
            returning id
            """,
            {
                "document_type": document_type,
                "title": document_title,
                "source_uri": source_uri,
                "mime_type": mime_type,
                "content_hash": content_hash,
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
            content_hash = coalesce(%(content_hash)s, content_hash)
        where id = %(document_id)s
        """,
        {
            "document_id": existing_document_id,
            "title": document_title,
            "source_uri": source_uri,
            "mime_type": mime_type,
            "content_hash": content_hash,
        },
    )
    return existing_document_id


def _update_document_content(
    cursor: Cursor[Any],
    *,
    document_id: str,
    document_title: str | None,
    mime_type: str | None,
    source_uri: str | None,
    content_hash: str | None,
    extracted_text: str | None,
) -> None:
    """
    Update one existing canonical document row with downloaded-file data.

    Notes
    -----
    This helper keeps updates conservative:

    - title/source metadata are only filled when newer values exist
    - content hashes can be added once bytes are downloaded
    - extracted text is only replaced when a non-empty string is available

    Example
    -------
    A reference-only `candidate_attachment` row can be upgraded later with:

        - `content_hash`
        - `mime_type`
        - `extracted_text`
    """

    cursor.execute(
        """
        update documents
        set
            title = coalesce(%(title)s, title),
            source_uri = coalesce(%(source_uri)s, source_uri),
            mime_type = coalesce(%(mime_type)s, mime_type),
            content_hash = coalesce(%(content_hash)s, content_hash),
            extracted_text = case
                when %(extracted_text)s::text is not null
                 and btrim(%(extracted_text)s::text) <> ''
                then %(extracted_text)s::text
                else extracted_text
            end
        where id = %(document_id)s
        """,
        {
            "document_id": document_id,
            "title": document_title,
            "source_uri": source_uri,
            "mime_type": mime_type,
            "content_hash": content_hash,
            "extracted_text": extracted_text,
        },
    )


def _find_linked_entity_id(
    cursor: Cursor[Any],
    *,
    source_record_id: str,
    entity_column: Literal[
        "candidate_id",
        "company_id",
        "job_id",
        "application_id",
        "document_id",
    ],
) -> str | None:
    """
    Return one linked canonical entity ID from `source_record_links`.

    Example
    -------
    A call with:

        entity_column="document_id"

    returns the document linked to that source record when such a link already
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
    job_id: str | None = None,
    application_id: str | None = None,
    document_id: str | None = None,
) -> None:
    """
    Insert one `source_record_links` row only when it does not already exist.

    Example
    -------
    A call with:

        source_record_id="..."
        job_id="..."

    inserts one job-target link on the first accepted run and becomes a no-op
    on later identical reruns.
    """

    column_name, entity_id = _pick_single_entity_target(
        person_id=person_id,
        candidate_id=candidate_id,
        company_id=company_id,
        job_id=job_id,
        application_id=application_id,
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
            person_id,
            candidate_id,
            company_id,
            job_id,
            application_id,
            document_id
        )
        values (
            %(source_record_id)s,
            %(person_id)s,
            %(candidate_id)s,
            %(company_id)s,
            %(job_id)s,
            %(application_id)s,
            %(document_id)s
        )
        """,
        {
            "source_record_id": source_record_id,
            "person_id": person_id,
            "candidate_id": candidate_id,
            "company_id": company_id,
            "job_id": job_id,
            "application_id": application_id,
            "document_id": document_id,
        },
    )


def _ensure_document_link(
    cursor: Cursor[Any],
    *,
    document_id: str,
    relationship_type: str,
    source_record_id: str | None,
    candidate_id: str | None = None,
    job_id: str | None = None,
) -> None:
    """
    Insert one `document_links` row only when it does not already exist.

    Example
    -------
    A call with:

        document_id="..."
        candidate_id="..."
        relationship_type="candidate_file_reference"

    creates one candidate-targeted document reference and becomes idempotent on
    later reruns.
    """

    column_name, entity_id = _pick_single_document_target(
        candidate_id=candidate_id,
        job_id=job_id,
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
            candidate_id,
            job_id,
            source_record_id,
            relationship_type
        )
        values (
            %(document_id)s,
            %(candidate_id)s,
            %(job_id)s,
            %(source_record_id)s,
            %(relationship_type)s
        )
        """,
        {
            "document_id": document_id,
            "candidate_id": candidate_id,
            "job_id": job_id,
            "source_record_id": source_record_id,
            "relationship_type": relationship_type,
        },
    )


def _pick_single_entity_target(
    *,
    person_id: str | None,
    candidate_id: str | None,
    company_id: str | None,
    job_id: str | None,
    application_id: str | None,
    document_id: str | None,
) -> tuple[str, str]:
    """
    Return the single non-null entity target column and ID.

    Example
    -------
    A call with only `candidate_id="..."` returns:

        ("candidate_id", "...")
    """

    candidates = {
        "person_id": person_id,
        "candidate_id": candidate_id,
        "company_id": company_id,
        "job_id": job_id,
        "application_id": application_id,
        "document_id": document_id,
    }
    populated = [(column_name, value) for column_name, value in candidates.items() if value is not None]
    if len(populated) != 1:
        raise RuntimeError(
            "Exactly one entity target must be supplied for a source record link."
        )
    return populated[0]


def _pick_single_document_target(
    *,
    candidate_id: str | None,
    job_id: str | None,
) -> tuple[str, str]:
    """
    Return the single non-null document-link target column and ID.

    Example
    -------
    A call with only `job_id="..."` returns:

        ("job_id", "...")
    """

    candidates = {
        "candidate_id": candidate_id,
        "job_id": job_id,
    }
    populated = [(column_name, value) for column_name, value in candidates.items() if value is not None]
    if len(populated) != 1:
        raise RuntimeError(
            "Exactly one entity target must be supplied for a document link."
        )
    return populated[0]


__all__ = [
    "persist_recruiterflow_candidate_file_reference",
    "persist_recruiterflow_candidate_snapshot",
    "persist_recruiterflow_job_file_reference",
    "persist_recruiterflow_job_snapshot",
]
