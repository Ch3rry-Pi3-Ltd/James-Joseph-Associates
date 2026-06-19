"""
Candidate-level semantic block persistence and retrieval helpers.

This module builds the first structured semantic index for candidate matching.
It works from canonical candidate/profile/skill fields already stored in
Supabase, rather than re-reading source systems.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from backend.db.connection import postgres_connection
from backend.services.candidate_semantic_blocks import build_candidate_semantic_blocks
from backend.services.document_embeddings import (
    embed_texts,
    summarize_embedding_configuration,
    vector_to_pgvector_literal,
)


def list_candidates_for_semantic_block_backfill(
    *,
    limit: int = 100,
    candidate_ids: list[str] | None = None,
    include_already_indexed: bool = False,
) -> list[dict[str, Any]]:
    """
    Return canonical candidates eligible for structured semantic indexing.
    """

    # Allow large controlled backfills in one run.
    # The caller still has to opt into the requested size explicitly.
    bounded_limit = max(1, int(limit))
    normalized_candidate_ids = [candidate_id.strip() for candidate_id in (candidate_ids or []) if candidate_id.strip()]

    query = """
        select
            c.id as candidate_id,
            p.id as person_id,
            p.full_name,
            p.location,
            p.headline,
            p.summary,
            c.current_title,
            c.candidate_status,
            c.availability_status,
            c.notice_period,
            co.name as current_company_name,
            d.id as document_id,
            d.title as document_title,
            d.source_uri as document_source_uri,
            coalesce(d.resume_updated_at, c.resume_updated_at) as resume_updated_at,
            count(csb.id) as existing_block_count
        from candidates c
        join people p
          on p.id = c.person_id
        left join companies co
          on co.id = c.current_company_id
        join lateral (
            select
                d.id,
                d.title,
                d.source_uri,
                d.resume_updated_at
            from document_links dl
            join documents d
              on d.id = dl.document_id
             and d.document_type = 'resume'
            where dl.candidate_id = c.id
              and dl.relationship_type = 'current_resume'
            order by
                coalesce(d.resume_updated_at, d.updated_at) desc nulls last,
                d.id desc
            limit 1
        ) d on true
        left join candidate_semantic_blocks csb
          on csb.candidate_id = c.id
        where (%(candidate_ids)s::text[] is null or c.id::text = any(%(candidate_ids)s))
        group by
            c.id,
            p.id,
            p.full_name,
            p.location,
            p.headline,
            p.summary,
            c.current_title,
            c.candidate_status,
            c.availability_status,
            c.notice_period,
            co.name,
            d.id,
            d.title,
            d.source_uri,
            coalesce(d.resume_updated_at, c.resume_updated_at)
    """

    if not include_already_indexed:
        query += """
        having count(csb.id) = 0
        """

    query += """
        order by
            coalesce(d.resume_updated_at, c.resume_updated_at) desc nulls last,
            c.id desc
        limit %(limit)s
    """

    with postgres_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                query,
                {
                    "candidate_ids": normalized_candidate_ids or None,
                    "limit": bounded_limit,
                },
            )
            rows = cursor.fetchall()

    return [dict(row) for row in rows]


def backfill_candidate_semantic_blocks(
    *,
    limit: int = 100,
    candidate_ids: list[str] | None = None,
    include_already_indexed: bool = False,
    embedding_batch_size: int = 25,
    dry_run: bool = False,
) -> dict[str, Any]:
    """
    Build, embed, and persist structured semantic blocks for candidates.
    """

    candidates = list_candidates_for_semantic_block_backfill(
        limit=limit,
        candidate_ids=candidate_ids,
        include_already_indexed=include_already_indexed,
    )
    candidate_ids_in_scope = [str(candidate["candidate_id"]) for candidate in candidates]
    skills_by_candidate_id = _get_skills_by_candidate_ids(candidate_ids_in_scope)

    candidate_summaries: list[dict[str, Any]] = []
    pending_rows: list[dict[str, Any]] = []

    for candidate in candidates:
        candidate_id = str(candidate["candidate_id"])
        blocks = build_candidate_semantic_blocks(
            candidate=candidate,
            skills=skills_by_candidate_id.get(candidate_id, []),
        )
        candidate_summaries.append(
            {
                "candidate_id": candidate_id,
                "full_name": candidate.get("full_name"),
                "document_id": candidate.get("document_id"),
                "existing_block_count": int(candidate["existing_block_count"]),
                "block_count": len(blocks),
                "block_types": [block.block_type for block in blocks],
            }
        )
        for block in blocks:
            pending_rows.append(
                {
                    "candidate_id": candidate_id,
                    "person_id": candidate["person_id"],
                    "document_id": candidate["document_id"],
                    "block_type": block.block_type,
                    "block_index": block.block_index,
                    "block_label": block.block_label,
                    "block_text": block.block_text,
                    "token_count": block.token_count,
                }
            )

    if dry_run:
        return {
            "candidates_selected": len(candidates),
            "candidates_processed": 0,
            "blocks_inserted": 0,
            "blocks_embedded": 0,
            "dry_run": True,
            "embedding_configuration": summarize_embedding_configuration(),
            "candidates": candidate_summaries,
        }

    if pending_rows:
        _embed_pending_rows(
            pending_rows,
            embedding_batch_size=max(1, min(int(embedding_batch_size), 100)),
        )

    with postgres_connection() as connection:
        with connection.cursor() as cursor:
            for candidate_id in candidate_ids_in_scope:
                cursor.execute(
                    """
                    delete from candidate_semantic_blocks
                    where candidate_id = %(candidate_id)s
                    """,
                    {"candidate_id": candidate_id},
                )

            for row in pending_rows:
                cursor.execute(
                    """
                    insert into candidate_semantic_blocks (
                        candidate_id,
                        person_id,
                        document_id,
                        block_type,
                        block_index,
                        block_label,
                        block_text,
                        embedding,
                        token_count
                    )
                    values (
                        %(candidate_id)s,
                        %(person_id)s,
                        %(document_id)s,
                        %(block_type)s,
                        %(block_index)s,
                        %(block_label)s,
                        %(block_text)s,
                        %(embedding)s::vector,
                        %(token_count)s
                    )
                    """,
                    {
                        **row,
                        "embedding": row["embedding"],
                    },
                )

        connection.commit()

    return {
        "candidates_selected": len(candidates),
        "candidates_processed": len(candidate_ids_in_scope),
        "blocks_inserted": len(pending_rows),
        "blocks_embedded": len(pending_rows),
        "dry_run": False,
        "embedding_configuration": summarize_embedding_configuration(),
        "candidates": candidate_summaries,
    }


def search_candidates_by_semantic_blocks(
    *,
    query: str,
    limit: int = 20,
) -> list[dict[str, Any]]:
    """
    Return candidates ranked by vector similarity over structured semantic blocks.
    """

    normalized_query = query.strip()
    if normalized_query == "":
        return []

    bounded_limit = max(1, min(int(limit), 100))
    query_vector = embed_texts([normalized_query])[0]
    query_vector_literal = vector_to_pgvector_literal(query_vector)

    search_sql = """
        with scored_blocks as (
            select
                csb.id,
                csb.candidate_id,
                csb.person_id,
                csb.document_id,
                csb.block_type,
                csb.block_label,
                csb.block_text,
                case
                    when csb.block_type = 'focus' then 1
                    when csb.block_type = 'summary' then 2
                    when csb.block_type = 'skills' then 3
                    when csb.block_type = 'profile' then 4
                    else 5
                end as block_priority,
                case
                    when csb.block_type = 'focus' then (csb.embedding <=> %(query_vector)s::vector) * 0.94
                    when csb.block_type = 'summary' then (csb.embedding <=> %(query_vector)s::vector) * 0.97
                    when csb.block_type = 'skills' then (csb.embedding <=> %(query_vector)s::vector) * 0.995
                    when csb.block_type = 'profile' then (csb.embedding <=> %(query_vector)s::vector) * 1.02
                    else (csb.embedding <=> %(query_vector)s::vector) * 1.03
                end as adjusted_distance
            from candidate_semantic_blocks csb
            where csb.embedding is not null
        ),
        ranked_blocks as (
            select
                c.id as candidate_id,
                p.id as person_id,
                p.full_name,
                c.current_title,
                c.candidate_status,
                co.name as current_company_name,
                coalesce(d.resume_updated_at, c.resume_updated_at) as resume_updated_at,
                d.id as document_id,
                d.title as document_title,
                d.source_uri as document_source_uri,
                sb.id as block_id,
                sb.block_type,
                sb.block_label,
                sb.block_text,
                sb.adjusted_distance as cosine_distance,
                row_number() over (
                    partition by c.id
                    order by
                        sb.adjusted_distance asc,
                        sb.block_priority asc,
                        sb.id asc
                ) as candidate_block_rank
            from scored_blocks sb
            join candidates c
              on c.id = sb.candidate_id
            join people p
              on p.id = sb.person_id
            left join companies co
              on co.id = c.current_company_id
            join documents d
              on d.id = sb.document_id
        )
        select
            candidate_id,
            person_id,
            full_name,
            current_title,
            candidate_status,
            current_company_name,
            resume_updated_at,
            document_id,
            document_title,
            document_source_uri,
            block_id,
            block_type,
            block_label,
            left(block_text, 600) as match_excerpt,
            round((1 - cosine_distance)::numeric, 6) as match_score
        from ranked_blocks
        where candidate_block_rank = 1
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


def _get_skills_by_candidate_ids(
    candidate_ids: list[str],
) -> dict[str, list[dict[str, Any]]]:
    if not candidate_ids:
        return {}

    query = """
        select
            cs.candidate_id::text as candidate_id,
            s.id as skill_id,
            s.name as skill_name,
            s.canonical_name,
            s.skill_type,
            cs.confidence,
            cs.evidence_text
        from candidate_skills cs
        join skills s
          on s.id = cs.skill_id
        where cs.candidate_id::text = any(%(candidate_ids)s)
        order by
            cs.candidate_id,
            s.canonical_name nulls last,
            s.name
    """

    with postgres_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(query, {"candidate_ids": candidate_ids})
            rows = cursor.fetchall()

    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[str(row["candidate_id"])].append(dict(row))
    return dict(grouped)


def _embed_pending_rows(
    pending_rows: list[dict[str, Any]],
    *,
    embedding_batch_size: int,
) -> None:
    for start in range(0, len(pending_rows), embedding_batch_size):
        batch = pending_rows[start : start + embedding_batch_size]
        vectors = embed_texts([row["block_text"] for row in batch])
        if len(vectors) != len(batch):
            raise RuntimeError("Embedding provider returned a mismatched vector count.")
        for row, vector in zip(batch, vectors, strict=True):
            row["embedding"] = vector_to_pgvector_literal(vector)


__all__ = [
    "backfill_candidate_semantic_blocks",
    "list_candidates_for_semantic_block_backfill",
    "search_candidates_by_semantic_blocks",
]
