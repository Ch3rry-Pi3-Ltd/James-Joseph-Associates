"""
Interaction read helpers for company-linked recruiter discovery.
"""

from typing import Any

from backend.db.connection import postgres_connection


def search_interactions_by_company_name(
    *,
    company_name: str,
    limit: int = 20,
) -> list[dict[str, Any]]:
    """
    Return recent interactions linked to people associated with one company.
    """

    normalized_company_name = company_name.strip()
    if normalized_company_name == "":
        return []

    bounded_limit = max(1, min(int(limit), 100))

    query = """
        with target_people as (
            select distinct on (p.id)
                p.id as person_id,
                c.id as candidate_id,
                co.id as company_id,
                co.name as company_name,
                p.full_name,
                coalesce(c.current_title, pcr.role_title, ct.role_title) as role_title,
                c.last_contacted_at as candidate_last_contacted_at
            from people p
            left join candidates c
              on c.person_id = p.id
            left join companies co
              on co.id = c.current_company_id
            left join person_company_roles pcr
              on pcr.person_id = p.id
             and pcr.company_id = co.id
             and pcr.is_current = true
            left join contacts ct
              on ct.person_id = p.id
             and ct.company_id = co.id
            where lower(coalesce(co.name, '')) like ('%%' || lower(%(company_name)s) || '%%')

            union

            select distinct on (p.id)
                p.id as person_id,
                c.id as candidate_id,
                co.id as company_id,
                co.name as company_name,
                p.full_name,
                coalesce(c.current_title, pcr.role_title, ct.role_title) as role_title,
                c.last_contacted_at as candidate_last_contacted_at
            from contacts ct
            join people p
              on p.id = ct.person_id
            join companies co
              on co.id = ct.company_id
            left join candidates c
              on c.person_id = p.id
            left join person_company_roles pcr
              on pcr.person_id = p.id
             and pcr.company_id = co.id
             and pcr.is_current = true
            where lower(co.name) like ('%%' || lower(%(company_name)s) || '%%')

            union

            select distinct on (p.id)
                p.id as person_id,
                c.id as candidate_id,
                co.id as company_id,
                co.name as company_name,
                p.full_name,
                coalesce(c.current_title, pcr.role_title, ct.role_title) as role_title,
                c.last_contacted_at as candidate_last_contacted_at
            from person_company_roles pcr
            join people p
              on p.id = pcr.person_id
            join companies co
              on co.id = pcr.company_id
            left join candidates c
              on c.person_id = p.id
            left join contacts ct
              on ct.person_id = p.id
             and ct.company_id = co.id
            where pcr.is_current = true
              and lower(co.name) like ('%%' || lower(%(company_name)s) || '%%')
        )
        select distinct
            i.id as interaction_id,
            i.interaction_type,
            i.occurred_at,
            i.subject,
            i.summary,
            i.body,
            i.source_system,
            tp.person_id,
            tp.candidate_id,
            tp.company_id,
            tp.company_name,
            tp.full_name,
            tp.role_title,
            tp.candidate_last_contacted_at,
            case
                when tp.candidate_id is not null then 'candidate'
                else 'person'
            end as matched_entity_type
        from interactions i
        join interaction_participants ip
          on ip.interaction_id = i.id
        join target_people tp
          on ip.person_id = tp.person_id
          or (
                tp.candidate_id is not null
                and ip.candidate_id = tp.candidate_id
          )
        order by
            i.occurred_at desc nulls last,
            i.created_at desc,
            i.id desc
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


__all__ = ["search_interactions_by_company_name"]
