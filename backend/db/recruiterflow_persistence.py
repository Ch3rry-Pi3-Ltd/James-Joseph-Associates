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
    }
    populated = [(column_name, value) for column_name, value in candidates.items() if value is not None]
    if len(populated) != 1:
        raise RuntimeError(
            "Exactly one entity target must be supplied for a source record link."
        )
    return populated[0]


__all__ = [
    "persist_recruiterflow_candidate_snapshot",
    "persist_recruiterflow_job_snapshot",
]
