"""
Persistence helpers for Recruitly company/contact ingestion.

This module keeps the raw Recruitly payload in `source_records`, then refreshes
the canonical company, person, contact, and role tables that drive recruiter
workflows elsewhere in the app.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any, Literal
from uuid import UUID

from psycopg import Cursor
from psycopg.types.json import Jsonb

from backend.db.connection import postgres_connection

RecruitlySourceRecordType = Literal[
    "recruitly_company",
    "recruitly_contact",
    "recruitly_job",
    "recruitly_opportunity",
    "recruitly_journal_entry",
]


def persist_recruitly_company_snapshot(
    persistence_payload: dict[str, Any],
) -> dict[str, Any]:
    """
    Persist one Recruitly company snapshot.
    """

    persisted_at = datetime.now(timezone.utc)

    with postgres_connection() as connection:
        with connection.cursor() as cursor:
            source_record = _upsert_source_record(
                cursor,
                source_record_type="recruitly_company",
                source_record_id=str(persistence_payload["source_record_id"]),
                source_payload=persistence_payload["source_payload"],
                source_payload_hash=str(persistence_payload["source_payload_hash"]),
                import_run_id=persistence_payload.get("import_run_id"),
                processed_at=persisted_at,
            )

            company_id = _upsert_company(
                cursor,
                recruitly_company_source_record_id=str(
                    persistence_payload["source_record_id"]
                ),
                company_name=persistence_payload.get("company_name"),
                domain=persistence_payload.get("company_domain"),
                website_url=persistence_payload.get("company_website_url"),
                industry=persistence_payload.get("industry"),
                location=persistence_payload.get("location"),
                status=persistence_payload.get("status"),
                description=persistence_payload.get("description"),
            )

            _ensure_source_record_link(
                cursor,
                source_record_id=source_record["id"],
                company_id=company_id,
            )

        connection.commit()

    return _make_json_safe_summary(
        {
            "persisted_at": persisted_at.isoformat(),
            "source_record_id": source_record["id"],
            "company_id": company_id,
            "record_kind": "company",
        }
    )


def persist_recruitly_contact_snapshot(
    persistence_payload: dict[str, Any],
) -> dict[str, Any]:
    """
    Persist one Recruitly contact snapshot.
    """

    persisted_at = datetime.now(timezone.utc)

    with postgres_connection() as connection:
        with connection.cursor() as cursor:
            source_record = _upsert_source_record(
                cursor,
                source_record_type="recruitly_contact",
                source_record_id=str(persistence_payload["source_record_id"]),
                source_payload=persistence_payload["source_payload"],
                source_payload_hash=str(persistence_payload["source_payload_hash"]),
                import_run_id=persistence_payload.get("import_run_id"),
                processed_at=persisted_at,
            )

            company_id = _upsert_company(
                cursor,
                recruitly_company_source_record_id=persistence_payload.get(
                    "company_source_record_id"
                ),
                company_name=persistence_payload.get("company_name"),
                domain=persistence_payload.get("company_domain"),
                website_url=persistence_payload.get("company_website_url"),
                industry=persistence_payload.get("industry"),
                location=persistence_payload.get("company_location"),
                status=persistence_payload.get("company_status"),
                description=None,
            )

            person_id = _upsert_person(
                cursor,
                source_record_id=source_record["id"],
                full_name=str(persistence_payload["full_name"]),
                first_name=persistence_payload.get("first_name"),
                last_name=persistence_payload.get("last_name"),
                primary_email=persistence_payload.get("primary_email"),
                primary_phone=persistence_payload.get("primary_phone"),
                linkedin_url=persistence_payload.get("linkedin_url"),
                location=persistence_payload.get("location"),
                headline=persistence_payload.get("headline"),
                summary=persistence_payload.get("summary"),
            )

            contact_id = _upsert_contact(
                cursor,
                source_record_id=source_record["id"],
                person_id=person_id,
                company_id=company_id,
                role_title=persistence_payload.get("role_title"),
                contact_type=persistence_payload.get("contact_type"),
                seniority=persistence_payload.get("seniority"),
                is_hiring_manager=bool(persistence_payload.get("is_hiring_manager")),
                postcode=persistence_payload.get("postcode"),
            )

            person_company_role_id: str | None = None
            if company_id is not None:
                person_company_role_id = _upsert_person_company_role(
                    cursor,
                    person_id=person_id,
                    company_id=company_id,
                    role_title=persistence_payload.get("role_title"),
                    start_date=persistence_payload.get("role_start_date"),
                    end_date=persistence_payload.get("role_end_date"),
                    is_current=bool(persistence_payload.get("is_current_company", True)),
                    source_record_id=source_record["id"],
                )

            _ensure_source_record_link(
                cursor,
                source_record_id=source_record["id"],
                person_id=person_id,
            )
            if company_id is not None:
                _ensure_source_record_link(
                    cursor,
                    source_record_id=source_record["id"],
                    company_id=company_id,
                )
            _ensure_source_record_link(
                cursor,
                source_record_id=source_record["id"],
                contact_id=contact_id,
            )

        connection.commit()

    return _make_json_safe_summary(
        {
            "persisted_at": persisted_at.isoformat(),
            "source_record_id": source_record["id"],
            "person_id": person_id,
            "company_id": company_id,
            "contact_id": contact_id,
            "person_company_role_id": person_company_role_id,
            "record_kind": "contact",
        }
    )


def persist_recruitly_job_snapshot(
    persistence_payload: dict[str, Any],
) -> dict[str, Any]:
    """
    Persist one Recruitly job snapshot.
    """

    persisted_at = datetime.now(timezone.utc)

    with postgres_connection() as connection:
        with connection.cursor() as cursor:
            source_record = _upsert_source_record(
                cursor,
                source_record_type="recruitly_job",
                source_record_id=str(persistence_payload["source_record_id"]),
                source_payload=persistence_payload["source_payload"],
                source_payload_hash=str(persistence_payload["source_payload_hash"]),
                import_run_id=persistence_payload.get("import_run_id"),
                processed_at=persisted_at,
            )

            company_id = _upsert_company(
                cursor,
                recruitly_company_source_record_id=persistence_payload.get(
                    "company_source_record_id"
                ),
                company_name=persistence_payload.get("company_name"),
                domain=None,
                website_url=None,
                industry=None,
                location=None,
                status=None,
                description=None,
            )
            hiring_manager_contact_id = _find_entity_id_by_source_identity(
                cursor,
                source_record_type="recruitly_contact",
                source_record_id=persistence_payload.get("contact_source_record_id"),
                entity_column="contact_id",
            )
            job_id = _upsert_job(
                cursor,
                source_record_id=source_record["id"],
                company_id=company_id,
                hiring_manager_contact_id=hiring_manager_contact_id,
                title=str(persistence_payload["title"]),
                description=persistence_payload.get("description"),
                location=persistence_payload.get("location"),
                workplace_type=persistence_payload.get("workplace_type"),
                employment_type=persistence_payload.get("employment_type"),
                work_type=persistence_payload.get("work_type"),
                source="recruitly",
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
                source_record_id=source_record["id"],
                job_id=job_id,
            )
            if company_id is not None:
                _ensure_source_record_link(
                    cursor,
                    source_record_id=source_record["id"],
                    company_id=company_id,
                )
            if hiring_manager_contact_id is not None:
                _ensure_source_record_link(
                    cursor,
                    source_record_id=source_record["id"],
                    contact_id=hiring_manager_contact_id,
                )

        connection.commit()

    return _make_json_safe_summary(
        {
            "persisted_at": persisted_at.isoformat(),
            "source_record_id": source_record["id"],
            "company_id": company_id,
            "hiring_manager_contact_id": hiring_manager_contact_id,
            "job_id": job_id,
            "record_kind": "job",
        }
    )


def persist_recruitly_opportunity_snapshot(
    persistence_payload: dict[str, Any],
) -> dict[str, Any]:
    """
    Persist one Recruitly opportunity snapshot.
    """

    persisted_at = datetime.now(timezone.utc)

    with postgres_connection() as connection:
        with connection.cursor() as cursor:
            source_record = _upsert_source_record(
                cursor,
                source_record_type="recruitly_opportunity",
                source_record_id=str(persistence_payload["source_record_id"]),
                source_payload=persistence_payload["source_payload"],
                source_payload_hash=str(persistence_payload["source_payload_hash"]),
                import_run_id=persistence_payload.get("import_run_id"),
                processed_at=persisted_at,
            )

            company_id = _upsert_company(
                cursor,
                recruitly_company_source_record_id=persistence_payload.get(
                    "company_source_record_id"
                ),
                company_name=persistence_payload.get("company_name"),
                domain=None,
                website_url=None,
                industry=None,
                location=None,
                status=None,
                description=None,
            )
            contact_id = _find_entity_id_by_source_identity(
                cursor,
                source_record_type="recruitly_contact",
                source_record_id=persistence_payload.get("contact_source_record_id"),
                entity_column="contact_id",
            )
            opportunity_id = _upsert_opportunity(
                cursor,
                source_record_id=source_record["id"],
                title=str(persistence_payload["title"]),
                smart_summary=persistence_payload.get("smart_summary"),
                company_id=company_id,
                contact_id=contact_id,
                stage=persistence_payload.get("stage"),
                last_contact_at=persistence_payload.get("last_contact_at"),
                next_task_at=persistence_payload.get("next_task_at"),
                value=persistence_payload.get("value"),
            )

            _ensure_source_record_link(
                cursor,
                source_record_id=source_record["id"],
                opportunity_id=opportunity_id,
            )
            if company_id is not None:
                _ensure_source_record_link(
                    cursor,
                    source_record_id=source_record["id"],
                    company_id=company_id,
                )
            if contact_id is not None:
                _ensure_source_record_link(
                    cursor,
                    source_record_id=source_record["id"],
                    contact_id=contact_id,
                )

        connection.commit()

    return _make_json_safe_summary(
        {
            "persisted_at": persisted_at.isoformat(),
            "source_record_id": source_record["id"],
            "company_id": company_id,
            "contact_id": contact_id,
            "opportunity_id": opportunity_id,
            "record_kind": "opportunity",
        }
    )


def persist_recruitly_journal_entries(
    persistence_payload: dict[str, Any],
) -> dict[str, Any]:
    """
    Persist one bounded Recruitly journal slice as canonical interactions.
    """

    persisted_at = datetime.now(timezone.utc)
    entries = list(persistence_payload.get("entries", []))
    persisted_entries: list[dict[str, Any]] = []

    with postgres_connection() as connection:
        with connection.cursor() as cursor:
            linked_targets = _resolve_journal_targets(
                cursor,
                record_type=str(persistence_payload["record_type"]),
                record_source_record_id=str(
                    persistence_payload["record_source_record_id"]
                ),
            )

            for entry in entries:
                source_record = _upsert_source_record(
                    cursor,
                    source_record_type="recruitly_journal_entry",
                    source_record_id=str(entry["source_record_id"]),
                    source_payload=entry["source_payload"],
                    source_payload_hash=str(entry["source_payload_hash"]),
                    import_run_id=persistence_payload.get("import_run_id"),
                    processed_at=persisted_at,
                )

                interaction_id = _upsert_journal_interaction(
                    cursor,
                    interaction_type=str(entry["interaction_type"]),
                    occurred_at=entry.get("occurred_at"),
                    subject=entry.get("subject"),
                    body=entry.get("body"),
                    summary=entry.get("summary"),
                    linked_targets=linked_targets,
                )
                _ensure_journal_participants(
                    cursor,
                    interaction_id=interaction_id,
                    linked_targets=linked_targets,
                )
                persisted_entries.append(
                    {
                        "source_record_id": source_record["id"],
                        "interaction_id": interaction_id,
                    }
                )

        connection.commit()

    return _make_json_safe_summary(
        {
            "persisted_at": persisted_at.isoformat(),
            "record_type": persistence_payload["record_type"],
            "record_source_record_id": persistence_payload["record_source_record_id"],
            "interaction_count": len(persisted_entries),
            "persisted": persisted_entries,
        }
    )


def _upsert_source_record(
    cursor: Cursor[Any],
    *,
    source_record_type: RecruitlySourceRecordType,
    source_record_id: str,
    source_payload: dict[str, Any],
    source_payload_hash: str,
    import_run_id: str | None,
    processed_at: datetime,
) -> dict[str, Any]:
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
            'recruitly',
            %(source_record_type)s,
            %(source_record_id)s,
            %(source_payload)s,
            %(source_payload_hash)s,
            %(import_run_id)s,
            %(processed_at)s,
            'accepted',
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
        returning id, source_record_type, source_record_id
        """,
        {
            "source_record_type": source_record_type,
            "source_record_id": source_record_id,
            "source_payload": Jsonb(source_payload),
            "source_payload_hash": source_payload_hash,
            "import_run_id": import_run_id,
            "processed_at": processed_at,
        },
    )
    row = cursor.fetchone()
    if row is None:
        raise RuntimeError("Failed to persist Recruitly source record.")
    return dict(row)


def _upsert_company(
    cursor: Cursor[Any],
    *,
    recruitly_company_source_record_id: str | None,
    company_name: str | None,
    domain: str | None,
    website_url: str | None,
    industry: str | None,
    location: str | None,
    status: str | None,
    description: str | None,
) -> str:
    existing_company_id: str | None = None

    if recruitly_company_source_record_id is not None:
        existing_company_id = _find_entity_id_by_source_identity(
            cursor,
            source_record_type="recruitly_company",
            source_record_id=recruitly_company_source_record_id,
            entity_column="company_id",
        )

    if existing_company_id is None and domain is not None:
        cursor.execute(
            """
            select id
            from companies
            where domain = %(domain)s
            limit 1
            """,
            {"domain": domain},
        )
        row = cursor.fetchone()
        if row is not None:
            existing_company_id = row["id"]

    if existing_company_id is None and company_name is not None:
        cursor.execute(
            """
            select id
            from companies
            where lower(name) = lower(%(company_name)s)
            limit 1
            """,
            {"company_name": company_name},
        )
        row = cursor.fetchone()
        if row is not None:
            existing_company_id = row["id"]

    if existing_company_id is None:
        cursor.execute(
            """
            insert into companies (
                name,
                domain,
                website_url,
                industry,
                location,
                description,
                status
            )
            values (
                %(company_name)s,
                %(domain)s,
                %(website_url)s,
                %(industry)s,
                %(location)s,
                %(description)s,
                %(status)s
            )
            returning id
            """,
            {
                "company_name": company_name or domain or website_url or "Unknown Company",
                "domain": domain,
                "website_url": website_url,
                "industry": industry,
                "location": location,
                "description": description,
                "status": status,
            },
        )
        row = cursor.fetchone()
        if row is None:
            raise RuntimeError("Failed to create company row.")
        return row["id"]

    cursor.execute(
        """
        update companies
        set
            name = coalesce(%(company_name)s, name),
            domain = coalesce(%(domain)s, domain),
            website_url = coalesce(%(website_url)s, website_url),
            industry = coalesce(%(industry)s, industry),
            location = coalesce(%(location)s, location),
            description = coalesce(%(description)s, description),
            status = coalesce(%(status)s, status)
        where id = %(company_id)s
        """,
        {
            "company_id": existing_company_id,
            "company_name": company_name,
            "domain": domain,
            "website_url": website_url,
            "industry": industry,
            "location": location,
            "description": description,
            "status": status,
        },
    )
    return existing_company_id


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
        row = cursor.fetchone()
        if row is None:
            raise RuntimeError("Failed to create person row.")
        return row["id"]

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


def _upsert_job(
    cursor: Cursor[Any],
    *,
    source_record_id: str,
    company_id: str | None,
    hiring_manager_contact_id: str | None,
    title: str,
    description: str | None,
    location: str | None,
    workplace_type: str | None,
    employment_type: str | None,
    work_type: str | None,
    source: str | None,
    owner_name: str | None,
    salary_min: Any,
    salary_max: Any,
    currency: str | None,
    status: str | None,
    opened_at: datetime | None,
    closed_at: datetime | None,
    updated_from_source_at: datetime | None,
) -> str:
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
                hiring_manager_contact_id,
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
                %(hiring_manager_contact_id)s,
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
                "hiring_manager_contact_id": hiring_manager_contact_id,
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
        row = cursor.fetchone()
        if row is None:
            raise RuntimeError("Failed to create job row.")
        return row["id"]

    cursor.execute(
        """
        update jobs
        set
            company_id = coalesce(%(company_id)s, company_id),
            hiring_manager_contact_id = coalesce(
                %(hiring_manager_contact_id)s,
                hiring_manager_contact_id
            ),
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
            "hiring_manager_contact_id": hiring_manager_contact_id,
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


def _upsert_opportunity(
    cursor: Cursor[Any],
    *,
    source_record_id: str,
    title: str,
    smart_summary: str | None,
    company_id: str | None,
    contact_id: str | None,
    stage: str | None,
    last_contact_at: datetime | None,
    next_task_at: datetime | None,
    value: Any,
) -> str:
    existing_opportunity_id = _find_linked_entity_id(
        cursor,
        source_record_id=source_record_id,
        entity_column="opportunity_id",
    )

    if existing_opportunity_id is None and company_id is not None:
        cursor.execute(
            """
            select id
            from opportunities
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
            existing_opportunity_id = row["id"]

    if existing_opportunity_id is None:
        cursor.execute(
            """
            insert into opportunities (
                title,
                smart_summary,
                company_id,
                contact_id,
                stage,
                last_contact_at,
                next_task_at,
                value
            )
            values (
                %(title)s,
                %(smart_summary)s,
                %(company_id)s,
                %(contact_id)s,
                %(stage)s,
                %(last_contact_at)s,
                %(next_task_at)s,
                %(value)s
            )
            returning id
            """,
            {
                "title": title,
                "smart_summary": smart_summary,
                "company_id": company_id,
                "contact_id": contact_id,
                "stage": stage,
                "last_contact_at": last_contact_at,
                "next_task_at": next_task_at,
                "value": value,
            },
        )
        row = cursor.fetchone()
        if row is None:
            raise RuntimeError("Failed to create opportunity row.")
        return row["id"]

    cursor.execute(
        """
        update opportunities
        set
            title = %(title)s,
            smart_summary = coalesce(%(smart_summary)s, smart_summary),
            company_id = coalesce(%(company_id)s, company_id),
            contact_id = coalesce(%(contact_id)s, contact_id),
            stage = coalesce(%(stage)s, stage),
            last_contact_at = coalesce(%(last_contact_at)s, last_contact_at),
            next_task_at = coalesce(%(next_task_at)s, next_task_at),
            value = coalesce(%(value)s, value)
        where id = %(opportunity_id)s
        """,
        {
            "opportunity_id": existing_opportunity_id,
            "title": title,
            "smart_summary": smart_summary,
            "company_id": company_id,
            "contact_id": contact_id,
            "stage": stage,
            "last_contact_at": last_contact_at,
            "next_task_at": next_task_at,
            "value": value,
        },
    )
    return existing_opportunity_id


def _upsert_contact(
    cursor: Cursor[Any],
    *,
    source_record_id: str,
    person_id: str,
    company_id: str | None,
    role_title: str | None,
    contact_type: str | None,
    seniority: str | None,
    is_hiring_manager: bool,
    postcode: str | None,
) -> str:
    existing_contact_id = _find_linked_entity_id(
        cursor,
        source_record_id=source_record_id,
        entity_column="contact_id",
    )

    if existing_contact_id is None:
        cursor.execute(
            """
            select id
            from contacts
            where person_id = %(person_id)s
              and (
                    company_id = %(company_id)s
                    or (
                        company_id is null
                        and %(company_id)s is null
                    )
              )
            limit 1
            """,
            {
                "person_id": person_id,
                "company_id": company_id,
            },
        )
        row = cursor.fetchone()
        if row is not None:
            existing_contact_id = row["id"]

    if existing_contact_id is None:
        cursor.execute(
            """
            insert into contacts (
                person_id,
                company_id,
                role_title,
                contact_type,
                seniority,
                is_hiring_manager,
                postcode
            )
            values (
                %(person_id)s,
                %(company_id)s,
                %(role_title)s,
                %(contact_type)s,
                %(seniority)s,
                %(is_hiring_manager)s,
                %(postcode)s
            )
            returning id
            """,
            {
                "person_id": person_id,
                "company_id": company_id,
                "role_title": role_title,
                "contact_type": contact_type,
                "seniority": seniority,
                "is_hiring_manager": is_hiring_manager,
                "postcode": postcode,
            },
        )
        row = cursor.fetchone()
        if row is None:
            raise RuntimeError("Failed to create contact row.")
        return row["id"]

    cursor.execute(
        """
        update contacts
        set
            company_id = coalesce(%(company_id)s, company_id),
            role_title = coalesce(%(role_title)s, role_title),
            contact_type = coalesce(%(contact_type)s, contact_type),
            seniority = coalesce(%(seniority)s, seniority),
            is_hiring_manager = contacts.is_hiring_manager or %(is_hiring_manager)s,
            postcode = coalesce(%(postcode)s, postcode)
        where id = %(contact_id)s
        """,
        {
            "contact_id": existing_contact_id,
            "company_id": company_id,
            "role_title": role_title,
            "contact_type": contact_type,
            "seniority": seniority,
            "is_hiring_manager": is_hiring_manager,
            "postcode": postcode,
        },
    )
    return existing_contact_id


def _upsert_person_company_role(
    cursor: Cursor[Any],
    *,
    person_id: str,
    company_id: str,
    role_title: str | None,
    start_date: date | None,
    end_date: date | None,
    is_current: bool,
    source_record_id: str,
) -> str:
    cursor.execute(
        """
        select id
        from person_company_roles
        where person_id = %(person_id)s
          and company_id = %(company_id)s
          and coalesce(role_title, '') = coalesce(%(role_title)s, '')
          and coalesce(start_date, date '1900-01-01') = coalesce(%(start_date)s, date '1900-01-01')
        limit 1
        """,
        {
            "person_id": person_id,
            "company_id": company_id,
            "role_title": role_title,
            "start_date": start_date,
        },
    )
    row = cursor.fetchone()
    if row is not None:
        cursor.execute(
            """
            update person_company_roles
            set
                end_date = coalesce(%(end_date)s, end_date),
                is_current = %(is_current)s,
                source_record_id = coalesce(%(source_record_id)s, source_record_id)
            where id = %(role_id)s
            """,
            {
                "role_id": row["id"],
                "end_date": end_date,
                "is_current": is_current,
                "source_record_id": source_record_id,
            },
        )
        return row["id"]

    cursor.execute(
        """
        insert into person_company_roles (
            person_id,
            company_id,
            role_title,
            start_date,
            end_date,
            is_current,
            source_record_id
        )
        values (
            %(person_id)s,
            %(company_id)s,
            %(role_title)s,
            %(start_date)s,
            %(end_date)s,
            %(is_current)s,
            %(source_record_id)s
        )
        returning id
        """,
        {
            "person_id": person_id,
            "company_id": company_id,
            "role_title": role_title,
            "start_date": start_date,
            "end_date": end_date,
            "is_current": is_current,
            "source_record_id": source_record_id,
        },
    )
    row = cursor.fetchone()
    if row is None:
        raise RuntimeError("Failed to create person_company_role row.")
    return row["id"]


def _find_linked_entity_id(
    cursor: Cursor[Any],
    *,
    source_record_id: str,
    entity_column: Literal[
        "person_id",
        "company_id",
        "contact_id",
        "job_id",
        "opportunity_id",
    ],
) -> str | None:
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


def _find_entity_id_by_source_identity(
    cursor: Cursor[Any],
    *,
    source_record_type: RecruitlySourceRecordType,
    source_record_id: str | None,
    entity_column: Literal[
        "company_id",
        "contact_id",
        "person_id",
        "job_id",
        "opportunity_id",
    ],
) -> str | None:
    if source_record_id is None:
        return None
    cursor.execute(
        f"""
        select srl.{entity_column}
        from source_records sr
        join source_record_links srl
          on srl.source_record_id = sr.id
        where sr.source_system = 'recruitly'
          and sr.source_record_type = %(source_record_type)s
          and sr.source_record_id = %(source_record_id)s
          and srl.{entity_column} is not null
        limit 1
        """,
        {
            "source_record_type": source_record_type,
            "source_record_id": source_record_id,
        },
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
    company_id: str | None = None,
    contact_id: str | None = None,
    job_id: str | None = None,
    opportunity_id: str | None = None,
) -> None:
    column_name, entity_id = _pick_single_entity_target(
        person_id=person_id,
        company_id=company_id,
        contact_id=contact_id,
        job_id=job_id,
        opportunity_id=opportunity_id,
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
            company_id,
            contact_id,
            job_id,
            opportunity_id
        )
        values (
            %(source_record_id)s,
            %(person_id)s,
            %(company_id)s,
            %(contact_id)s,
            %(job_id)s,
            %(opportunity_id)s
        )
        """,
        {
            "source_record_id": source_record_id,
            "person_id": person_id,
            "company_id": company_id,
            "contact_id": contact_id,
            "job_id": job_id,
            "opportunity_id": opportunity_id,
        },
    )


def _pick_single_entity_target(
    *,
    person_id: str | None,
    company_id: str | None,
    contact_id: str | None,
    job_id: str | None,
    opportunity_id: str | None,
) -> tuple[str, str]:
    populated_targets = [
        ("person_id", person_id),
        ("company_id", company_id),
        ("contact_id", contact_id),
        ("job_id", job_id),
        ("opportunity_id", opportunity_id),
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


def _resolve_journal_targets(
    cursor: Cursor[Any],
    *,
    record_type: str,
    record_source_record_id: str,
) -> dict[str, str | None]:
    normalized_record_type = record_type.strip().lower()
    targets: dict[str, str | None] = {
        "person_id": None,
        "company_id": None,
        "contact_id": None,
        "job_id": None,
        "opportunity_id": None,
    }

    source_record_type = f"recruitly_{normalized_record_type}"

    if normalized_record_type in {"company", "contact", "job", "opportunity"}:
        targets["person_id"] = _find_entity_id_by_source_identity(
            cursor,
            source_record_type=source_record_type,  # type: ignore[arg-type]
            source_record_id=record_source_record_id,
            entity_column="person_id",
        )
        targets["company_id"] = _find_entity_id_by_source_identity(
            cursor,
            source_record_type=source_record_type,  # type: ignore[arg-type]
            source_record_id=record_source_record_id,
            entity_column="company_id",
        )
        targets["contact_id"] = _find_entity_id_by_source_identity(
            cursor,
            source_record_type=source_record_type,  # type: ignore[arg-type]
            source_record_id=record_source_record_id,
            entity_column="contact_id",
        )
        targets["job_id"] = _find_entity_id_by_source_identity(
            cursor,
            source_record_type=source_record_type,  # type: ignore[arg-type]
            source_record_id=record_source_record_id,
            entity_column="job_id",
        )
        targets["opportunity_id"] = _find_entity_id_by_source_identity(
            cursor,
            source_record_type=source_record_type,  # type: ignore[arg-type]
            source_record_id=record_source_record_id,
            entity_column="opportunity_id",
        )

    if normalized_record_type == "contact" and targets["contact_id"] is not None:
        cursor.execute(
            """
            select person_id, company_id
            from contacts
            where id = %(contact_id)s
            limit 1
            """,
            {"contact_id": targets["contact_id"]},
        )
        row = cursor.fetchone()
        if row is not None:
            targets["person_id"] = row["person_id"]
            targets["company_id"] = row["company_id"]

    if normalized_record_type == "job" and targets["job_id"] is not None:
        cursor.execute(
            """
            select j.company_id, j.hiring_manager_contact_id, ct.person_id
            from jobs j
            left join contacts ct
              on ct.id = j.hiring_manager_contact_id
            where j.id = %(job_id)s
            limit 1
            """,
            {"job_id": targets["job_id"]},
        )
        row = cursor.fetchone()
        if row is not None:
            targets["company_id"] = row["company_id"]
            targets["contact_id"] = row["hiring_manager_contact_id"]
            targets["person_id"] = row["person_id"]

    if normalized_record_type == "opportunity" and targets["opportunity_id"] is not None:
        cursor.execute(
            """
            select o.company_id, o.contact_id, ct.person_id
            from opportunities o
            left join contacts ct
              on ct.id = o.contact_id
            where o.id = %(opportunity_id)s
            limit 1
            """,
            {"opportunity_id": targets["opportunity_id"]},
        )
        row = cursor.fetchone()
        if row is not None:
            targets["company_id"] = row["company_id"]
            targets["contact_id"] = row["contact_id"]
            targets["person_id"] = row["person_id"]

    return targets


def _upsert_journal_interaction(
    cursor: Cursor[Any],
    *,
    interaction_type: str,
    occurred_at: datetime | None,
    subject: str | None,
    body: str | None,
    summary: str | None,
    linked_targets: dict[str, str | None],
) -> str:
    existing_interaction_id = _find_matching_recruitly_interaction(
        cursor,
        interaction_type=interaction_type,
        occurred_at=occurred_at,
        subject=subject,
        body=body,
        linked_targets=linked_targets,
    )

    if existing_interaction_id is None:
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
                'recruitly'
            )
            returning id
            """,
            {
                "interaction_type": interaction_type,
                "occurred_at": occurred_at,
                "subject": subject,
                "body": body,
                "summary": summary,
            },
        )
        row = cursor.fetchone()
        if row is None:
            raise RuntimeError("Failed to create Recruitly interaction row.")
        return row["id"]

    cursor.execute(
        """
        update interactions
        set
            occurred_at = coalesce(%(occurred_at)s, occurred_at),
            subject = coalesce(%(subject)s, subject),
            body = coalesce(%(body)s, body),
            summary = coalesce(%(summary)s, summary)
        where id = %(interaction_id)s
        """,
        {
            "interaction_id": existing_interaction_id,
            "occurred_at": occurred_at,
            "subject": subject,
            "body": body,
            "summary": summary,
        },
    )
    return existing_interaction_id


def _find_matching_recruitly_interaction(
    cursor: Cursor[Any],
    *,
    interaction_type: str,
    occurred_at: datetime | None,
    subject: str | None,
    body: str | None,
    linked_targets: dict[str, str | None],
) -> str | None:
    cursor.execute(
        """
        select distinct i.id
        from interactions i
        left join interaction_participants ip
          on ip.interaction_id = i.id
        where i.source_system = 'recruitly'
          and i.interaction_type = %(interaction_type)s
          and coalesce(i.subject, '') = coalesce(%(subject)s, '')
          and coalesce(i.body, '') = coalesce(%(body)s, '')
          and (
                i.occurred_at = %(occurred_at)s
                or (
                    i.occurred_at is null
                    and %(occurred_at)s is null
                )
          )
          and (
                (%(person_id)s is not null and ip.person_id = %(person_id)s)
                or (%(contact_id)s is not null and ip.contact_id = %(contact_id)s)
                or (%(company_id)s is not null and ip.company_id = %(company_id)s)
                or (%(job_id)s is not null and ip.job_id = %(job_id)s)
              )
        limit 1
        """,
        {
            "interaction_type": interaction_type,
            "occurred_at": occurred_at,
            "subject": subject,
            "body": body,
            "person_id": linked_targets.get("person_id"),
            "contact_id": linked_targets.get("contact_id"),
            "company_id": linked_targets.get("company_id"),
            "job_id": linked_targets.get("job_id"),
        },
    )
    row = cursor.fetchone()
    if row is None:
        return None
    return row["id"]


def _ensure_journal_participants(
    cursor: Cursor[Any],
    *,
    interaction_id: str,
    linked_targets: dict[str, str | None],
) -> None:
    for column_name, role_in_interaction in (
        ("person_id", "person_subject"),
        ("contact_id", "contact_subject"),
        ("company_id", "company_subject"),
        ("job_id", "job_subject"),
    ):
        entity_id = linked_targets.get(column_name)
        if entity_id is None:
            continue
        cursor.execute(
            f"""
            select id
            from interaction_participants
            where interaction_id = %(interaction_id)s
              and {column_name} = %(entity_id)s
            limit 1
            """,
            {
                "interaction_id": interaction_id,
                "entity_id": entity_id,
            },
        )
        if cursor.fetchone() is not None:
            continue

        cursor.execute(
            """
            insert into interaction_participants (
                interaction_id,
                person_id,
                contact_id,
                company_id,
                job_id,
                role_in_interaction
            )
            values (
                %(interaction_id)s,
                %(person_id)s,
                %(contact_id)s,
                %(company_id)s,
                %(job_id)s,
                %(role_in_interaction)s
            )
            """,
            {
                "interaction_id": interaction_id,
                "person_id": entity_id if column_name == "person_id" else None,
                "contact_id": entity_id if column_name == "contact_id" else None,
                "company_id": entity_id if column_name == "company_id" else None,
                "job_id": entity_id if column_name == "job_id" else None,
                "role_in_interaction": role_in_interaction,
            },
        )


def _make_json_safe_summary(value: Any) -> Any:
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
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
    "persist_recruitly_company_snapshot",
    "persist_recruitly_contact_snapshot",
    "persist_recruitly_job_snapshot",
    "persist_recruitly_opportunity_snapshot",
    "persist_recruitly_journal_entries",
]
