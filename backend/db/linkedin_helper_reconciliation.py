"""Read-only canonical identity indexes for Linked Helper reconciliation."""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Literal

from psycopg import sql

from backend.db.connection import postgres_connection


def load_canonical_companies_for_linkedin_helper() -> dict[str, Any]:
    """Load canonical companies and existing Linked Helper links without writing."""

    with postgres_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                select
                    id::text as company_id,
                    name,
                    domain,
                    website_url,
                    linkedin_url
                from companies
                order by id
                """
            )
            company_rows = [dict(row) for row in cursor.fetchall()]

            cursor.execute(
                """
                select
                    sr.source_record_id,
                    srl.company_id::text as company_id
                from source_records sr
                join source_record_links srl on srl.source_record_id = sr.id
                where sr.source_system = 'linkedin_helper'
                  and srl.company_id is not null
                """
            )
            source_link_rows = [dict(row) for row in cursor.fetchall()]

    return {
        "companies": company_rows,
        "source_links": source_link_rows,
    }


def load_canonical_people_for_linkedin_helper() -> dict[str, Any]:
    """Load canonical people and existing Linked Helper links without writing."""

    with postgres_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                select
                    p.id::text as person_id,
                    p.full_name,
                    p.primary_email,
                    p.primary_phone,
                    p.linkedin_url,
                    c.name as company_name
                from people p
                left join candidates candidate on candidate.person_id = p.id
                left join companies c on c.id = candidate.current_company_id
                order by p.id
                """
            )
            person_rows = [dict(row) for row in cursor.fetchall()]

            cursor.execute(
                """
                select pcr.person_id::text as person_id, c.name as company_name
                from person_company_roles pcr
                join companies c on c.id = pcr.company_id
                where pcr.is_current = true
                union
                select contact.person_id::text as person_id, c.name as company_name
                from contacts contact
                join companies c on c.id = contact.company_id
                """
            )
            company_rows = [dict(row) for row in cursor.fetchall()]

            cursor.execute(
                """
                select
                    sr.source_record_id,
                    srl.person_id::text as person_id
                from source_records sr
                join source_record_links srl on srl.source_record_id = sr.id
                where sr.source_system = 'linkedin_helper'
                  and srl.person_id is not null
                """
            )
            source_link_rows = [dict(row) for row in cursor.fetchall()]

    companies_by_person: dict[str, set[str]] = defaultdict(set)
    for row in company_rows:
        company_name = row.get("company_name")
        if isinstance(company_name, str) and company_name.strip():
            companies_by_person[str(row["person_id"])].add(company_name.strip())

    for row in person_rows:
        person_id = str(row["person_id"])
        candidate_company = row.get("company_name")
        row["company_names"] = sorted(companies_by_person.get(person_id, set()))
        if isinstance(candidate_company, str) and candidate_company.strip():
            row["company_names"] = sorted(
                {*row["company_names"], candidate_company.strip()}
            )

    return {
        "people": person_rows,
        "source_links": source_link_rows,
    }


def verify_linkedin_helper_import(
    *,
    person_source_record_ids: list[str],
    company_source_record_ids: list[str],
) -> dict[str, Any]:
    """Verify imported provenance has exactly one canonical entity link."""

    with postgres_connection() as connection:
        with connection.cursor() as cursor:
            person_rows = _load_link_audit_rows(
                cursor,
                source_record_type="linkedin_helper_person_export",
                source_record_ids=person_source_record_ids,
                entity_column="person_id",
            )
            company_rows = _load_link_audit_rows(
                cursor,
                source_record_type="linkedin_helper_company_export",
                source_record_ids=company_source_record_ids,
                entity_column="company_id",
            )

    return {
        "people": _summarize_link_audit(
            rows=person_rows,
            expected_source_record_ids=person_source_record_ids,
        ),
        "companies": _summarize_link_audit(
            rows=company_rows,
            expected_source_record_ids=company_source_record_ids,
        ),
    }


def _load_link_audit_rows(
    cursor: Any,
    *,
    source_record_type: str,
    source_record_ids: list[str],
    entity_column: Literal["person_id", "company_id"],
) -> list[dict[str, Any]]:
    if not source_record_ids:
        return []
    cursor.execute(
        sql.SQL(
            """
        select
            sr.source_record_id,
            count(distinct srl.{entity_column}) as entity_links
        from source_records sr
        left join source_record_links srl on srl.source_record_id = sr.id
        where sr.source_system = 'linkedin_helper'
          and sr.source_record_type = %(source_record_type)s
          and sr.source_record_id = any(%(source_record_ids)s)
        group by sr.source_record_id
        order by sr.source_record_id
        """
        ).format(entity_column=sql.Identifier(entity_column)),
        {
            "source_record_type": source_record_type,
            "source_record_ids": source_record_ids,
        },
    )
    return [dict(row) for row in cursor.fetchall()]


def _summarize_link_audit(
    *,
    rows: list[dict[str, Any]],
    expected_source_record_ids: list[str],
) -> dict[str, Any]:
    found = {str(row["source_record_id"]): int(row["entity_links"]) for row in rows}
    missing = sorted(set(expected_source_record_ids) - set(found))
    invalid = sorted(
        source_record_id
        for source_record_id, link_count in found.items()
        if link_count != 1
    )
    return {
        "expected": len(expected_source_record_ids),
        "found": len(found),
        "missing": missing,
        "invalid_link_counts": invalid,
        "passed": not missing and not invalid,
    }


__all__ = [
    "load_canonical_companies_for_linkedin_helper",
    "load_canonical_people_for_linkedin_helper",
    "verify_linkedin_helper_import",
]
