"""
Opportunity read helpers for recruiter company discovery.
"""

from typing import Any

from backend.db.connection import postgres_connection


def search_opportunities_by_company_name(
    *,
    company_name: str,
    limit: int = 20,
) -> list[dict[str, Any]]:
    """
    Return recent opportunities linked to one company name.
    """

    normalized_company_name = company_name.strip()
    if normalized_company_name == "":
        return []

    bounded_limit = max(1, min(int(limit), 100))

    query = """
        select
            o.id as opportunity_id,
            o.title,
            o.smart_summary,
            o.stage,
            o.last_contact_at,
            o.next_task_at,
            o.value,
            co.id as company_id,
            co.name as company_name,
            ct.id as contact_id,
            p.id as contact_person_id,
            p.full_name as contact_name,
            p.primary_email as contact_email,
            p.primary_phone as contact_phone,
            ct.role_title as contact_role_title,
            case
                when lower(co.name) = lower(%(company_name)s) then 'company_exact'
                else 'company_partial'
            end as company_match_source
        from opportunities o
        join companies co
          on co.id = o.company_id
        left join contacts ct
          on ct.id = o.contact_id
        left join people p
          on p.id = ct.person_id
        where lower(co.name) like ('%%' || lower(%(company_name)s) || '%%')
        order by
            case
                when lower(co.name) = lower(%(company_name)s) then 0
                else 1
            end,
            coalesce(o.next_task_at, o.last_contact_at, o.updated_at, o.created_at) desc,
            o.id desc
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


__all__ = ["search_opportunities_by_company_name"]
