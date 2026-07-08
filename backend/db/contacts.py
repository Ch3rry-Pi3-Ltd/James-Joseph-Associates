"""
Contact read helpers for company-linked recruiter discovery.
"""

from typing import Any

from backend.db.connection import postgres_connection


def search_contacts_by_company_name(
    *,
    company_name: str,
    limit: int = 20,
) -> list[dict[str, Any]]:
    """
    Return ranked contacts already linked to one company name.
    """

    normalized_company_name = company_name.strip()
    if normalized_company_name == "":
        return []

    bounded_limit = max(1, min(int(limit), 100))

    query = """
        select
            ct.id as contact_id,
            p.id as person_id,
            p.full_name,
            p.primary_email,
            p.primary_phone,
            p.linkedin_url,
            p.location,
            p.headline,
            co.id as company_id,
            co.name as company_name,
            ct.role_title,
            ct.contact_type,
            ct.seniority,
            ct.is_hiring_manager,
            pcr.is_current as role_is_current,
            pcr.start_date as role_start_date,
            pcr.end_date as role_end_date,
            case
                when lower(co.name) = lower(%(company_name)s) then 'company_exact'
                else 'company_partial'
            end as company_match_source
        from contacts ct
        join people p
          on p.id = ct.person_id
        join companies co
          on co.id = ct.company_id
        left join lateral (
            select
                pcr.is_current,
                pcr.start_date,
                pcr.end_date
            from person_company_roles pcr
            where pcr.person_id = p.id
              and pcr.company_id = co.id
            order by
                pcr.is_current desc,
                pcr.start_date desc nulls last,
                pcr.created_at desc
            limit 1
        ) pcr on true
        where lower(co.name) like ('%%' || lower(%(company_name)s) || '%%')
        order by
            case
                when lower(co.name) = lower(%(company_name)s) then 0
                else 1
            end,
            ct.is_hiring_manager desc,
            pcr.is_current desc nulls last,
            p.full_name asc,
            ct.id desc
        limit %(limit)s
    """

    with postgres_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                query,
                {
                    "company_name": normalized_company_name,
                    "limit": bounded_limit,
                },
            )
            rows = cursor.fetchall()

    return [dict(row) for row in rows]


__all__ = ["search_contacts_by_company_name"]
