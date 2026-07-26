"""Read-only canonical identity indexes for Linked Helper reconciliation."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

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


__all__ = [
    "load_canonical_companies_for_linkedin_helper",
    "load_canonical_people_for_linkedin_helper",
]
