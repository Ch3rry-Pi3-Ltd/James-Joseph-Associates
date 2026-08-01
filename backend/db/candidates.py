"""
Candidate read helpers for the intelligence backend.

This module contains small database query helpers for reading candidate data
from the prototype Supabase/Postgres schema.

It gives the rest of the repository a stable way to talk about:

- fetching one canonical candidate profile
- joining the candidate record to the linked person record
- joining the candidate record to the current company record
- returning a predictable dictionary-like result shape

Keeping this logic in its own module makes the project easier to grow because:

- route handlers do not need to embed raw SQL
- candidate-specific queries stay near each other
- tests can target one small read module at a time
- future repository/service code can build on top of these helpers

In plain language:

- this module answers the question:

    "How does the backend read a candidate profile from Postgres?"

- it does not define database tables
- it does not create routes
- it does not write data
- it only reads candidate-related records

Notes
-----
- This module currently targets the prototype schema.
- The query shape may evolve once we inspect real source-system payloads.
- The helper returns a simple dictionary-like object so later layers can decide
  how to serialise it for APIs or workflows.

Important boundaries
--------------------
This module should not contain:

- FastAPI route handlers
- request/response models
- write/update logic
- LLM calls
- LangGraph workflow steps
- business decisions about matching or ranking
"""

from typing import Any

from backend.db.connection import postgres_connection


def get_candidate_source_systems(
    candidate_ids: list[str] | set[str] | tuple[str, ...],
) -> dict[str, list[str]]:
    """
    Return distinct person- and candidate-linked source systems in one batch.

    Source records can be linked directly to a candidate or to the shared
    canonical person. Reading both link types is required to identify people
    enriched by Linked Helper after an earlier CV ingest.
    """

    return {
        candidate_id: [str(detail["source_system"]) for detail in source_details]
        for candidate_id, source_details in get_candidate_source_details(
            candidate_ids
        ).items()
    }


def get_candidate_source_details(
    candidate_ids: list[str] | set[str] | tuple[str, ...],
) -> dict[str, list[dict[str, Any]]]:
    """Return source systems and their latest record receipt times in one batch."""

    normalized_candidate_ids = sorted(
        {
            str(candidate_id).strip()
            for candidate_id in candidate_ids
            if str(candidate_id).strip()
        }
    )
    if not normalized_candidate_ids:
        return {}

    query = """
        with requested_candidates as (
            select id, person_id
            from candidates
            where id = any(%(candidate_ids)s::uuid[])
        ),
        linked_sources as (
            select
                requested.id as candidate_id,
                source.source_system,
                source.received_at
            from requested_candidates requested
            join source_record_links link
              on link.candidate_id = requested.id
            join source_records source
              on source.id = link.source_record_id

            union

            select
                requested.id as candidate_id,
                source.source_system,
                source.received_at
            from requested_candidates requested
            join source_record_links link
              on link.person_id = requested.person_id
            join source_records source
              on source.id = link.source_record_id
        )
        select
            candidate_id,
            source_system,
            max(received_at) as latest_record_received_at
        from linked_sources
        group by candidate_id, source_system
        order by candidate_id, source_system
    """

    with postgres_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                query,
                {"candidate_ids": normalized_candidate_ids},
            )
            rows = cursor.fetchall()

    source_details_by_candidate: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        candidate_id = str(row["candidate_id"])
        source_details_by_candidate.setdefault(candidate_id, []).append(
            {
                "source_system": str(row["source_system"]),
                "latest_record_received_at": row["latest_record_received_at"],
            }
        )
    return source_details_by_candidate


def get_candidate_profile(candidate_id: str) -> dict[str, Any] | None:
    """
    Return one candidate profile joined to person and company details.

    Parameters
    ----------
    candidate_id : str
        Canonical candidate UUID to look up.

    Returns
    -------
    dict[str, Any] | None
        Dictionary-like row containing the joined candidate profile fields.

        Returns `None` if no candidate exists for the supplied ID.

    Notes
    -----
    - This reads from the prototype canonical schema, not directly from JobAdder.
    - The query joins:
      - `candidates`
      - `people`
      - `companies`
    - A left join is used for the current company because the candidate may not
      always have a linked company record.

    Returned fields
    ---------------
    The row currently includes:

    - `candidate_id`
    - `person_id`
    - `full_name`
    - `first_name`
    - `last_name`
    - `primary_email`
    - `primary_phone`
    - `linkedin_url`
    - `location`
    - `headline`
    - `summary`
    - `current_title`
    - `candidate_status`
    - `availability_status`
    - `salary_expectation`
    - `notice_period`
    - `last_contacted_at`
    - `resume_updated_at`
    - `current_company_id`
    - `current_company_name`

    In plain language:

    - find one candidate by canonical ID
    - include the linked person details
    - include the linked current company name if present
    - return one row or nothing

    Example
    -------
    Read one candidate profile by canonical candidate ID:

        from backend.db.candidates import get_candidate_profile

        profile = get_candidate_profile(
            "33333333-3333-3333-3333-333333333331",
        )

        if profile is not None:
            print(profile["full_name"])
            print(profile["current_company_name"])
    """

    query = """
        SELECT
            c.id AS candidate_id,
            p.id AS person_id,
            p.full_name,
            p.first_name,
            p.last_name,
            p.primary_email,
            p.primary_phone,
            p.linkedin_url,
            p.location,
            p.headline,
            p.summary,
            c.current_title,
            c.candidate_status,
            c.availability_status,
            c.salary_expectation,
            c.notice_period,
            c.last_contacted_at,
            c.resume_updated_at,
            co.id AS current_company_id,
            co.name AS current_company_name,
            exists (
                select 1
                from document_links dl
                join documents d
                  on d.id = dl.document_id
                 and d.document_type = 'resume'
                where dl.candidate_id = c.id
                  and dl.relationship_type = 'current_resume'
            ) as has_resume_document
        FROM candidates c
        JOIN people p
            ON p.id = c.person_id
        LEFT JOIN companies co
            ON co.id = c.current_company_id
        WHERE c.id = %(candidate_id)s
        LIMIT 1
    """

    with postgres_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                query,
                {"candidate_id": candidate_id},
            )
            row = cursor.fetchone()

    # `fetchone()` returns `None` when no row matches the candidate ID.
    #   - Returning `None` keeps the calling code simple and explicit.
    if row is None:
        return None

    return dict(row)


def get_candidate_recent_employment(
    candidate_id: str,
    *,
    limit: int = 5,
) -> list[dict[str, Any]]:
    """Return the candidate's most recent canonical employment roles."""

    bounded_limit = max(1, min(int(limit), 10))
    query = """
        select
            pcr.id as employment_role_id,
            pcr.company_id,
            co.name as company_name,
            pcr.role_title,
            pcr.start_date,
            pcr.end_date,
            pcr.is_current
        from candidates c
        join person_company_roles pcr
          on pcr.person_id = c.person_id
        join companies co
          on co.id = pcr.company_id
        where c.id = %(candidate_id)s
        order by
            pcr.is_current desc,
            coalesce(pcr.end_date, pcr.start_date) desc nulls last,
            pcr.start_date desc nulls last,
            pcr.created_at desc,
            pcr.id desc
        limit %(limit)s
    """

    with postgres_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                query,
                {
                    "candidate_id": candidate_id,
                    "limit": bounded_limit,
                },
            )
            rows = cursor.fetchall()

    return [dict(row) for row in rows]


def get_candidate_current_resume_document(
    candidate_id: str,
) -> dict[str, Any] | None:
    """
    Return the linked current-resume document metadata for one candidate.

    Notes
    -----
    - This helper reads the canonical `document_links` relationship rather than
      guessing from candidate fields.
    - Only `relationship_type = 'current_resume'` rows are considered.
    """

    query = """
        select
            c.id as candidate_id,
            d.id as document_id,
            d.title as document_title,
            d.source_uri as document_source_uri,
            d.mime_type as document_mime_type,
            provenance.source_system as provenance_source_system,
            provenance.source_record_type as provenance_source_record_type,
            provenance.source_record_id as provenance_source_record_id,
            provenance.source_payload as provenance_source_payload
        from candidates c
        join document_links dl
          on dl.candidate_id = c.id
         and dl.relationship_type = 'current_resume'
        join documents d
          on d.id = dl.document_id
         and d.document_type = 'resume'
        left join lateral (
            select
                sr.source_system,
                sr.source_record_type,
                sr.source_record_id,
                sr.source_payload
            from source_record_links srl
            join source_records sr
              on sr.id = srl.source_record_id
            where srl.document_id = d.id
            order by
                case
                    when sr.source_record_type in (
                        'dropbox_resume_attachment',
                        'recruiterflow_resume_attachment',
                        'outlook_message_attachment'
                    ) then 0
                    when sr.source_record_type like '%%resume_attachment' then 1
                    when sr.source_record_type like '%%resume_extraction' then 2
                    else 3
                end,
                sr.processed_at desc nulls last,
                sr.created_at desc nulls last,
                sr.id desc
            limit 1
        ) provenance on true
        where c.id = %(candidate_id)s
        order by dl.created_at desc nulls last, d.updated_at desc nulls last
        limit 1
    """

    with postgres_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                query,
                {"candidate_id": candidate_id},
            )
            row = cursor.fetchone()

    if row is None:
        return None

    return dict(row)


def search_candidates_by_resume_text(
    *,
    query: str,
    limit: int = 20,
) -> list[dict[str, Any]]:
    """
    Return ranked candidates whose current resume matches one free-text query.

    Parameters
    ----------
    query : str
        User-supplied free-text query used to search canonical current resumes.

    limit : int, default=20
        Maximum number of ranked candidate matches to return.

    Returns
    -------
    list[dict[str, Any]]
        Ranked candidate matches with the linked current resume metadata and a
        highlighted resume-text excerpt.

    Notes
    -----
    - This helper searches the canonical `documents.extracted_text` field that
      the ingestion pipeline already persists for resume documents.
    - Only documents linked as `relationship_type = 'current_resume'` are
      searched so the endpoint reflects the latest preferred CV per candidate.
    - Postgres full-text search is used directly because it is already
      available in Supabase and gives a clean MVP without introducing a new
      retrieval stack yet.
    """

    normalized_query = query.strip()
    if normalized_query == "":
        return []

    bounded_limit = max(1, min(int(limit), 100))

    search_sql = """
        with search_input as (
            select websearch_to_tsquery('simple', %(query)s) as search_query
        ),
        candidate_resume_search as (
            select
                c.id as candidate_id,
                p.id as person_id,
                p.full_name,
                c.current_title,
                c.candidate_status,
                c.resume_updated_at,
                co.name as current_company_name,
                d.id as document_id,
                d.title as document_title,
                d.source_uri as document_source_uri,
                d.resume_updated_at as document_resume_updated_at,
                d.extracted_text,
                setweight(to_tsvector('simple', coalesce(p.full_name, '')), 'A')
                || setweight(to_tsvector('simple', coalesce(c.current_title, '')), 'B')
                || setweight(
                    to_tsvector('simple', coalesce(co.name, '')),
                    'C'
                )
                || setweight(
                    to_tsvector('simple', coalesce(d.title, '')),
                    'C'
                )
                || setweight(
                    to_tsvector('simple', coalesce(d.extracted_text, '')),
                    'D'
                ) as search_vector
            from candidates c
            join people p
              on p.id = c.person_id
            left join companies co
              on co.id = c.current_company_id
            join document_links dl
              on dl.candidate_id = c.id
             and dl.relationship_type = 'current_resume'
            join documents d
              on d.id = dl.document_id
             and d.document_type = 'resume'
        )
        select
            crs.candidate_id,
            crs.person_id,
            crs.full_name,
            crs.current_title,
            crs.candidate_status,
            crs.current_company_name,
            coalesce(
                crs.document_resume_updated_at,
                crs.resume_updated_at
            ) as resume_updated_at,
            crs.document_id,
            crs.document_title,
            crs.document_source_uri,
            round(
                ts_rank_cd(crs.search_vector, si.search_query)::numeric,
                6
            ) as match_score,
            ts_headline(
                'simple',
                coalesce(crs.extracted_text, ''),
                si.search_query,
                'MaxFragments=2, MinWords=5, MaxWords=18, StartSel=<mark>, StopSel=</mark>'
            ) as match_excerpt
        from candidate_resume_search crs
        cross join search_input si
        where crs.search_vector @@ si.search_query
        order by
            ts_rank_cd(crs.search_vector, si.search_query) desc,
            coalesce(crs.document_resume_updated_at, crs.resume_updated_at) desc nulls last,
            crs.candidate_id desc
        limit %(limit)s
    """

    with postgres_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                search_sql,
                {
                    "query": normalized_query,
                    "limit": bounded_limit,
                },
            )
            rows = cursor.fetchall()

    return [dict(row) for row in rows]


def search_candidates_by_company_name(
    *,
    company_name: str,
    limit: int = 20,
) -> list[dict[str, Any]]:
    """
    Return ranked candidates connected to one company name.

    Notes
    -----
    This helper is intentionally evidence-first for recruiter workflows:

    - exact current-company matches rank highest
    - partial current-company matches rank next
    - current-resume text mentions are included as a fallback signal
    """

    normalized_company_name = company_name.strip()
    if normalized_company_name == "":
        return []

    bounded_limit = max(1, min(int(limit), 100))

    search_sql = """
        with search_input as (
            select
                lower(%(company_name)s) as normalized_company_name,
                websearch_to_tsquery('simple', %(company_name)s) as search_query
        ),
        candidate_resume_search as (
            select
                c.id as candidate_id,
                p.id as person_id,
                p.full_name,
                c.current_title,
                c.candidate_status,
                c.resume_updated_at,
                co.name as current_company_name,
                d.id as document_id,
                d.title as document_title,
                d.source_uri as document_source_uri,
                d.resume_updated_at as document_resume_updated_at,
                d.extracted_text,
                setweight(
                    to_tsvector('simple', coalesce(d.extracted_text, '')),
                    'A'
                ) as resume_search_vector
            from candidates c
            join people p
              on p.id = c.person_id
            left join companies co
              on co.id = c.current_company_id
            join document_links dl
              on dl.candidate_id = c.id
             and dl.relationship_type = 'current_resume'
            join documents d
              on d.id = dl.document_id
             and d.document_type = 'resume'
        )
        select
            crs.candidate_id,
            crs.person_id,
            crs.full_name,
            crs.current_title,
            crs.candidate_status,
            crs.current_company_name,
            coalesce(
                crs.document_resume_updated_at,
                crs.resume_updated_at
            ) as resume_updated_at,
            crs.document_id,
            crs.document_title,
            crs.document_source_uri,
            case
                when lower(coalesce(crs.current_company_name, '')) = si.normalized_company_name
                    then 'current_company_exact'
                when lower(coalesce(crs.current_company_name, '')) like
                    ('%%' || si.normalized_company_name || '%%')
                    then 'current_company_partial'
                else 'resume_text'
            end as company_match_source,
            round(
                case
                    when lower(coalesce(crs.current_company_name, '')) = si.normalized_company_name
                        then 1.0
                    when lower(coalesce(crs.current_company_name, '')) like
                        ('%%' || si.normalized_company_name || '%%')
                        then 0.85
                    else least(
                        0.8,
                        greatest(
                            0.2,
                            ts_rank_cd(
                                crs.resume_search_vector,
                                si.search_query
                            )
                        )
                    )
                end::numeric,
                6
            ) as company_match_score,
            case
                when lower(coalesce(crs.current_company_name, '')) = si.normalized_company_name
                    then 'Current company exactly matches ' || crs.current_company_name
                when lower(coalesce(crs.current_company_name, '')) like
                    ('%%' || si.normalized_company_name || '%%')
                    then 'Current company matches ' || crs.current_company_name
                else ts_headline(
                    'simple',
                    coalesce(crs.extracted_text, ''),
                    si.search_query,
                    'MaxFragments=2, MinWords=5, MaxWords=18, StartSel=<mark>, StopSel=</mark>'
                )
            end as match_excerpt
        from candidate_resume_search crs
        cross join search_input si
        where
            lower(coalesce(crs.current_company_name, '')) like
                ('%%' || si.normalized_company_name || '%%')
            or crs.resume_search_vector @@ si.search_query
        order by
            case
                when lower(coalesce(crs.current_company_name, '')) = si.normalized_company_name
                    then 0
                when lower(coalesce(crs.current_company_name, '')) like
                    ('%%' || si.normalized_company_name || '%%')
                    then 1
                else 2
            end,
            company_match_score desc,
            coalesce(
                crs.document_resume_updated_at,
                crs.resume_updated_at
            ) desc nulls last,
            crs.candidate_id desc
        limit %(limit)s
    """

    with postgres_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                search_sql,
                {
                    "company_name": normalized_company_name,
                    "limit": bounded_limit,
                },
            )
            rows = cursor.fetchall()

    return [dict(row) for row in rows]


__all__ = [
    "get_candidate_current_resume_document",
    "get_candidate_profile",
    "get_candidate_recent_employment",
    "get_candidate_source_details",
    "get_candidate_source_systems",
    "search_candidates_by_company_name",
    "search_candidates_by_resume_text",
]
