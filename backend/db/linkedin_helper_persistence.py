"""
Persistence helpers for Linked Helper person/contact ingestion.

This module provides one narrow canonical write path for Linked Helper sourced
people. It keeps the raw source payload in `source_records`, then upserts the
canonical rows that are already part of the platform data model.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any, Literal
from uuid import UUID

from psycopg import Cursor, sql
from psycopg.types.json import Jsonb

from backend.db.connection import postgres_connection

LinkedHelperRecordKind = Literal["candidate", "contact", "hiring_manager"]


def persist_linkedin_helper_person_snapshot(
    persistence_payload: dict[str, Any],
) -> dict[str, Any]:
    """
    Persist one Linked Helper person/contact snapshot.
    """

    persisted_at = datetime.now(timezone.utc)

    with postgres_connection() as connection:
        with connection.cursor() as cursor:
            source_record = _upsert_source_record(
                cursor,
                source_record_id=str(persistence_payload["source_record_id"]),
                source_payload=persistence_payload["source_payload"],
                source_payload_hash=str(persistence_payload["source_payload_hash"]),
                import_run_id=persistence_payload.get("import_run_id"),
                processed_at=persisted_at,
            )

            company_id = _upsert_company(
                cursor,
                company_name=persistence_payload.get("company_name"),
                domain=persistence_payload.get("company_domain"),
                website_url=persistence_payload.get("company_website_url"),
                linkedin_url=persistence_payload.get("company_linkedin_url"),
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

            candidate_id: str | None = None
            if persistence_payload["record_kind"] == "candidate":
                candidate_id = _upsert_candidate(
                    cursor,
                    source_record_id=source_record["id"],
                    person_id=person_id,
                    current_title=persistence_payload.get("role_title"),
                    current_company_id=company_id,
                    candidate_status=persistence_payload.get("candidate_status"),
                    availability_status=persistence_payload.get("availability_status"),
                    last_contacted_at=persistence_payload.get("last_contacted_at"),
                    resume_updated_at=persistence_payload.get("resume_updated_at"),
                )

            contact_id: str | None = None
            if persistence_payload["record_kind"] in {"contact", "hiring_manager"}:
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
                    is_current=bool(persistence_payload.get("is_current_company")),
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
            if candidate_id is not None:
                _ensure_source_record_link(
                    cursor,
                    source_record_id=source_record["id"],
                    candidate_id=candidate_id,
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
            "person_id": person_id,
            "company_id": company_id,
            "candidate_id": candidate_id,
            "contact_id": contact_id,
            "person_company_role_id": person_company_role_id,
            "record_kind": persistence_payload["record_kind"],
        }
    )


def _upsert_source_record(
    cursor: Cursor[Any],
    *,
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
            'linkedin_helper',
            'linkedin_helper_person_export',
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
        returning id, source_record_id
        """,
        {
            "source_record_id": source_record_id,
            "source_payload": Jsonb(source_payload),
            "source_payload_hash": source_payload_hash,
            "import_run_id": import_run_id,
            "processed_at": processed_at,
        },
    )
    row = cursor.fetchone()
    if row is None:
        raise RuntimeError("Failed to persist Linked Helper source record.")
    return dict(row)


def _upsert_company(
    cursor: Cursor[Any],
    *,
    company_name: str | None,
    domain: str | None,
    website_url: str | None,
    linkedin_url: str | None,
) -> str | None:
    if not any((company_name, domain, website_url, linkedin_url)):
        return None

    if linkedin_url is not None:
        cursor.execute(
            """
            select id
            from companies
            where linkedin_url = %(linkedin_url)s
            limit 1
            """,
            {"linkedin_url": linkedin_url},
        )
        row = cursor.fetchone()
        if row is not None:
            company_id = row["id"]
            _refresh_company(
                cursor,
                company_id=company_id,
                company_name=company_name,
                domain=domain,
                website_url=website_url,
                linkedin_url=linkedin_url,
            )
            return company_id

    if domain is not None:
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
            company_id = row["id"]
            _refresh_company(
                cursor,
                company_id=company_id,
                company_name=company_name,
                domain=domain,
                website_url=website_url,
                linkedin_url=linkedin_url,
            )
            return company_id

    if company_name is not None:
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
            company_id = row["id"]
            _refresh_company(
                cursor,
                company_id=company_id,
                company_name=company_name,
                domain=domain,
                website_url=website_url,
                linkedin_url=linkedin_url,
            )
            return company_id

    cursor.execute(
        """
        insert into companies (
            name,
            domain,
            website_url,
            linkedin_url
        )
        values (
            %(company_name)s,
            %(domain)s,
            %(website_url)s,
            %(linkedin_url)s
        )
        returning id
        """,
        {
            "company_name": company_name or domain or linkedin_url or "Unknown Company",
            "domain": domain,
            "website_url": website_url,
            "linkedin_url": linkedin_url,
        },
    )
    row = cursor.fetchone()
    if row is None:
        raise RuntimeError("Failed to create company row.")
    return row["id"]


def _refresh_company(
    cursor: Cursor[Any],
    *,
    company_id: str,
    company_name: str | None,
    domain: str | None,
    website_url: str | None,
    linkedin_url: str | None,
) -> None:
    cursor.execute(
        """
        update companies
        set
            name = coalesce(%(company_name)s, name),
            domain = coalesce(%(domain)s, domain),
            website_url = coalesce(%(website_url)s, website_url),
            linkedin_url = coalesce(%(linkedin_url)s, linkedin_url)
        where id = %(company_id)s
        """,
        {
            "company_id": company_id,
            "company_name": company_name,
            "domain": domain,
            "website_url": website_url,
            "linkedin_url": linkedin_url,
        },
    )


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


def _upsert_candidate(
    cursor: Cursor[Any],
    *,
    source_record_id: str,
    person_id: str,
    current_title: str | None,
    current_company_id: str | None,
    candidate_status: str | None,
    availability_status: str | None,
    last_contacted_at: datetime | None,
    resume_updated_at: datetime | None,
) -> str:
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
        row = cursor.fetchone()
        if row is None:
            raise RuntimeError("Failed to create candidate row.")
        return row["id"]

    cursor.execute(
        """
        update candidates
        set
            current_title = coalesce(%(current_title)s, current_title),
            current_company_id = coalesce(%(current_company_id)s, current_company_id),
            candidate_status = coalesce(%(candidate_status)s, candidate_status),
            availability_status = coalesce(%(availability_status)s, availability_status),
            last_contacted_at = coalesce(%(last_contacted_at)s, last_contacted_at),
            resume_updated_at = coalesce(%(resume_updated_at)s, resume_updated_at)
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
    entity_column: Literal["person_id", "candidate_id", "company_id", "contact_id"],
) -> str | None:
    cursor.execute(
        sql.SQL(
            """
            select {entity_column}
            from source_record_links
            where source_record_id = %(source_record_id)s
              and {entity_column} is not null
            limit 1
            """
        ).format(entity_column=sql.Identifier(entity_column)),
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
    contact_id: str | None = None,
) -> None:
    column_name, entity_id = _pick_single_entity_target(
        person_id=person_id,
        candidate_id=candidate_id,
        company_id=company_id,
        contact_id=contact_id,
    )
    cursor.execute(
        sql.SQL(
            """
            select id
            from source_record_links
            where source_record_id = %(source_record_id)s
              and {column_name} = %(entity_id)s
            limit 1
            """
        ).format(column_name=sql.Identifier(column_name)),
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
            contact_id
        )
        values (
            %(source_record_id)s,
            %(person_id)s,
            %(candidate_id)s,
            %(company_id)s,
            %(contact_id)s
        )
        """,
        {
            "source_record_id": source_record_id,
            "person_id": person_id,
            "candidate_id": candidate_id,
            "company_id": company_id,
            "contact_id": contact_id,
        },
    )


def _pick_single_entity_target(
    *,
    person_id: str | None,
    candidate_id: str | None,
    company_id: str | None,
    contact_id: str | None,
) -> tuple[str, str]:
    populated_targets = [
        ("person_id", person_id),
        ("candidate_id", candidate_id),
        ("company_id", company_id),
        ("contact_id", contact_id),
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


__all__ = ["persist_linkedin_helper_person_snapshot"]
