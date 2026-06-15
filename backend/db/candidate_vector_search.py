"""
Vector-search helpers for candidate matching against canonical resume chunks.

This is the first semantic retrieval path in the repository. It searches
embedded resume chunks and rolls the best chunk matches back up to candidates.
"""

from __future__ import annotations

from typing import Any

from backend.db.connection import postgres_connection
from backend.services.document_embeddings import (
    embed_texts,
    vector_to_pgvector_literal,
)


def search_candidates_by_resume_vector(
    *,
    query: str,
    limit: int = 20,
) -> list[dict[str, Any]]:
    """
    Return candidates ranked by vector similarity against embedded resume chunks.
    """

    normalized_query = query.strip()
    if normalized_query == "":
        return []

    bounded_limit = max(1, min(int(limit), 100))
    query_vector = embed_texts([normalized_query])[0]
    query_vector_literal = vector_to_pgvector_literal(query_vector)

    search_sql = """
        with ranked_resume_chunks as (
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
                dc.id as chunk_id,
                dc.chunk_index,
                dc.chunk_text,
                (dc.embedding <=> %(query_vector)s::vector) as cosine_distance,
                row_number() over (
                    partition by c.id
                    order by dc.embedding <=> %(query_vector)s::vector asc,
                             dc.chunk_index asc
                ) as candidate_chunk_rank
            from document_chunks dc
            join documents d
              on d.id = dc.document_id
             and d.document_type = 'resume'
            join document_links dl
              on dl.document_id = d.id
             and dl.relationship_type = 'current_resume'
            join candidates c
              on c.id = dl.candidate_id
            join people p
              on p.id = c.person_id
            left join companies co
              on co.id = c.current_company_id
            where dc.embedding is not null
        )
        select
            candidate_id,
            person_id,
            full_name,
            current_title,
            candidate_status,
            current_company_name,
            coalesce(document_resume_updated_at, resume_updated_at) as resume_updated_at,
            document_id,
            document_title,
            document_source_uri,
            chunk_id,
            chunk_index,
            chunk_text as match_excerpt,
            round((1 - cosine_distance)::numeric, 6) as match_score
        from ranked_resume_chunks
        where candidate_chunk_rank = 1
        order by cosine_distance asc, candidate_id desc
        limit %(limit)s
    """

    with postgres_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                search_sql,
                {
                    "query_vector": query_vector_literal,
                    "limit": bounded_limit,
                },
            )
            rows = cursor.fetchall()

    return [dict(row) for row in rows]


__all__ = ["search_candidates_by_resume_vector"]
