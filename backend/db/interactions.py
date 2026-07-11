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
        with target_companies as (
            select
                co.id as company_id,
                co.name as company_name
            from companies co
            where lower(co.name) like ('%%' || lower(%(company_name)s) || '%%')
        ),
        target_people as (
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
            where co.id in (select company_id from target_companies)

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
            where co.id in (select company_id from target_companies)

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
              and co.id in (select company_id from target_companies)
        ),
        matched_interactions as (
            select
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
                null::uuid as contact_id,
                null::uuid as job_id,
                null::text as job_title,
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

            union all

            select
                i.id as interaction_id,
                i.interaction_type,
                i.occurred_at,
                i.subject,
                i.summary,
                i.body,
                i.source_system,
                p.id as person_id,
                c.id as candidate_id,
                co.id as company_id,
                co.name as company_name,
                p.full_name,
                coalesce(c.current_title, pcr.role_title, ct.role_title) as role_title,
                c.last_contacted_at as candidate_last_contacted_at,
                ct.id as contact_id,
                null::uuid as job_id,
                null::text as job_title,
                'contact' as matched_entity_type
            from interactions i
            join interaction_participants ip
              on ip.interaction_id = i.id
            join contacts ct
              on ct.id = ip.contact_id
            join companies co
              on co.id = ct.company_id
            left join people p
              on p.id = ct.person_id
            left join candidates c
              on c.person_id = p.id
            left join person_company_roles pcr
              on pcr.person_id = p.id
             and pcr.company_id = co.id
             and pcr.is_current = true
            where co.id in (select company_id from target_companies)

            union all

            select
                i.id as interaction_id,
                i.interaction_type,
                i.occurred_at,
                i.subject,
                i.summary,
                i.body,
                i.source_system,
                null::uuid as person_id,
                null::uuid as candidate_id,
                tc.company_id,
                tc.company_name,
                null::text as full_name,
                null::text as role_title,
                null::timestamptz as candidate_last_contacted_at,
                null::uuid as contact_id,
                null::uuid as job_id,
                null::text as job_title,
                'company' as matched_entity_type
            from interactions i
            join interaction_participants ip
              on ip.interaction_id = i.id
            join target_companies tc
              on tc.company_id = ip.company_id

            union all

            select
                i.id as interaction_id,
                i.interaction_type,
                i.occurred_at,
                i.subject,
                i.summary,
                i.body,
                i.source_system,
                p.id as person_id,
                c.id as candidate_id,
                co.id as company_id,
                co.name as company_name,
                p.full_name,
                coalesce(c.current_title, pcr.role_title, ct.role_title) as role_title,
                c.last_contacted_at as candidate_last_contacted_at,
                ct.id as contact_id,
                j.id as job_id,
                j.title as job_title,
                'job' as matched_entity_type
            from interactions i
            join interaction_participants ip
              on ip.interaction_id = i.id
            join jobs j
              on j.id = ip.job_id
            join companies co
              on co.id = j.company_id
            left join contacts ct
              on ct.id = j.hiring_manager_contact_id
            left join people p
              on p.id = ct.person_id
            left join candidates c
              on c.person_id = p.id
            left join person_company_roles pcr
              on pcr.person_id = p.id
             and pcr.company_id = co.id
             and pcr.is_current = true
            where co.id in (select company_id from target_companies)
        )
        select distinct
            interaction_id,
            interaction_type,
            occurred_at,
            subject,
            summary,
            body,
            source_system,
            person_id,
            candidate_id,
            company_id,
            company_name,
            full_name,
            role_title,
            candidate_last_contacted_at,
            contact_id,
            job_id,
            job_title,
            matched_entity_type
        from matched_interactions
        order by
            occurred_at desc nulls last,
            interaction_id desc
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
