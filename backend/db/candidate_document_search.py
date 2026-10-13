"""Deterministic, exhaustive full-text search over canonical current CVs."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime
from decimal import Decimal
from typing import Any

from backend.db.connection import postgres_connection


_SEARCH_INPUT_CTE = """
    search_input as (
        select websearch_to_tsquery('simple', %(query)s) as search_query
    ),
    matched_documents as materialized (
        select distinct
            link.candidate_id,
            d.id as document_id
        from documents d
        join document_links link
          on link.document_id = d.id
         and link.relationship_type = 'current_resume'
        cross join search_input search
        where d.document_type = 'resume'
          and d.resume_search_vector @@ search.search_query
    ),
    ranked_matches as (
        select
            candidate.id as candidate_id,
            person.id as person_id,
            person.full_name,
            candidate.current_title,
            candidate.candidate_status,
            company.name as current_company_name,
            coalesce(
                document.resume_updated_at,
                candidate.resume_updated_at
            ) as resume_updated_at,
            coalesce(
                document.resume_updated_at,
                candidate.resume_updated_at,
                '1900-01-01 00:00:00+00'::timestamptz
            ) as sort_resume_updated_at,
            matched.document_id,
            document.title as document_title,
            document.source_uri as document_source_uri,
            round(
                ts_rank_cd(document.resume_search_vector, search.search_query)::numeric,
                6
            ) as match_score,
            ts_headline(
                'simple',
                coalesce(document.extracted_text, ''),
                search.search_query,
                'MaxFragments=3, MinWords=6, MaxWords=24, StartSel=<mark>, StopSel=</mark>'
            ) as match_excerpt
        from matched_documents matched
        join documents document on document.id = matched.document_id
        join candidates candidate on candidate.id = matched.candidate_id
        join people person on person.id = candidate.person_id
        left join companies company on company.id = candidate.current_company_id
        cross join search_input search
    )
"""


_RESULT_COLUMNS = """
    candidate_id,
    person_id,
    full_name,
    current_title,
    candidate_status,
    current_company_name,
    resume_updated_at,
    sort_resume_updated_at,
    document_id,
    document_title,
    document_source_uri,
    match_score,
    match_excerpt
"""


def search_current_resume_documents(
    *,
    query: str,
    limit: int = 50,
    after_score: Decimal | None = None,
    after_updated_at: datetime | None = None,
    after_candidate_id: str | None = None,
    after_document_id: str | None = None,
) -> dict[str, Any]:
    """Return one keyset-paginated page plus complete current-CV coverage."""

    normalized_query = query.strip()
    if not normalized_query:
        return {"coverage": _empty_coverage(), "results": []}

    bounded_limit = max(1, min(int(limit), 101))
    coverage_sql = """
        select
            (select count(*) from candidates)::integer as total_candidates,
            (
                select count(distinct (link.candidate_id, document.id))
                from documents document
                join document_links link
                  on link.document_id = document.id
                 and link.relationship_type = 'current_resume'
                where document.document_type = 'resume'
            )::integer as eligible_document_count,
            (
                select count(distinct (link.candidate_id, document.id))
                from documents document
                join document_links link
                  on link.document_id = document.id
                 and link.relationship_type = 'current_resume'
                where document.document_type = 'resume'
                  and document.extracted_text is not null
                  and octet_length(document.extracted_text) > 0
            )::integer as searchable_document_count,
            (
                select count(distinct (link.candidate_id, document.id))
                from documents document
                join document_links link
                  on link.document_id = document.id
                 and link.relationship_type = 'current_resume'
                where document.document_type = 'resume'
                  and (
                      document.extracted_text is null
                      or octet_length(document.extracted_text) = 0
                  )
            )::integer as excluded_missing_text_count,
            (
                (select count(*) from candidates)
                - (
                    select count(distinct link.candidate_id)
                    from documents document
                    join document_links link
                      on link.document_id = document.id
                     and link.relationship_type = 'current_resume'
                    where document.document_type = 'resume'
                )
            )::integer as candidates_without_current_resume_count,
            (
                select count(distinct (link.candidate_id, document.id))
                from documents document
                join document_links link
                  on link.document_id = document.id
                 and link.relationship_type = 'current_resume'
                where document.document_type = 'resume'
                  and document.resume_search_vector
                      @@ websearch_to_tsquery('simple', %(query)s)
            )::integer as matched_document_count,
            (
                select count(distinct link.candidate_id)
                from documents document
                join document_links link
                  on link.document_id = document.id
                 and link.relationship_type = 'current_resume'
                where document.document_type = 'resume'
                  and document.resume_search_vector
                      @@ websearch_to_tsquery('simple', %(query)s)
            )::integer as matched_candidate_count
    """
    results_sql = f"""
        with
        {_SEARCH_INPUT_CTE}
        select {_RESULT_COLUMNS}
        from ranked_matches
        where (
            %(after_score)s::numeric is null
            or match_score < %(after_score)s::numeric
            or (
                match_score = %(after_score)s::numeric
                and sort_resume_updated_at < %(after_updated_at)s::timestamptz
            )
            or (
                match_score = %(after_score)s::numeric
                and sort_resume_updated_at = %(after_updated_at)s::timestamptz
                and candidate_id < %(after_candidate_id)s::uuid
            )
            or (
                match_score = %(after_score)s::numeric
                and sort_resume_updated_at = %(after_updated_at)s::timestamptz
                and candidate_id = %(after_candidate_id)s::uuid
                and document_id < %(after_document_id)s::uuid
            )
        )
        order by
            match_score desc,
            sort_resume_updated_at desc,
            candidate_id desc,
            document_id desc
        limit %(limit)s
    """
    parameters = {
        "query": normalized_query,
        "limit": bounded_limit,
        "after_score": after_score,
        "after_updated_at": after_updated_at,
        "after_candidate_id": after_candidate_id,
        "after_document_id": after_document_id,
    }

    with postgres_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(coverage_sql, parameters)
            coverage_row = cursor.fetchone()
            cursor.execute(results_sql, parameters)
            rows = cursor.fetchall()

    return {
        "coverage": dict(coverage_row) if coverage_row is not None else _empty_coverage(),
        "results": [dict(row) for row in rows],
    }


def iter_current_resume_document_matches(
    *,
    query: str,
    batch_size: int = 500,
) -> Iterator[list[dict[str, Any]]]:
    """Yield every current-CV match in deterministic batches for CSV export."""

    normalized_query = query.strip()
    if not normalized_query:
        return

    bounded_batch_size = max(1, min(int(batch_size), 1000))
    export_sql = f"""
        with
        {_SEARCH_INPUT_CTE}
        select {_RESULT_COLUMNS}
        from ranked_matches
        order by
            match_score desc,
            sort_resume_updated_at desc,
            candidate_id desc,
            document_id desc
    """
    with postgres_connection() as connection:
        with connection.cursor(name="candidate_document_export") as cursor:
            cursor.execute(export_sql, {"query": normalized_query})
            while True:
                rows = cursor.fetchmany(bounded_batch_size)
                if not rows:
                    break
                yield [dict(row) for row in rows]


def _empty_coverage() -> dict[str, int]:
    return {
        "total_candidates": 0,
        "eligible_document_count": 0,
        "searchable_document_count": 0,
        "excluded_missing_text_count": 0,
        "candidates_without_current_resume_count": 0,
        "matched_document_count": 0,
        "matched_candidate_count": 0,
    }


__all__ = [
    "iter_current_resume_document_matches",
    "search_current_resume_documents",
]
