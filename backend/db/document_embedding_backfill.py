"""
Helpers for backfilling embeddings onto existing `document_chunks` rows.

This module assumes chunk rows already exist. It does not split document text
itself. Its job is:

- find chunk rows missing embeddings
- call the embedding service in batches
- write vectors into `document_chunks.embedding`
"""

from __future__ import annotations

from typing import Any

from backend.db.connection import postgres_connection
from backend.services.document_embeddings import (
    embed_texts,
    summarize_embedding_configuration,
    vector_to_pgvector_literal,
)


def list_chunks_missing_embeddings(
    *,
    document_types: tuple[str, ...] = ("resume", "job_spec"),
    linked_source_record_id_prefixes: tuple[str, ...] | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    """
    Return chunk rows whose embedding column is still null.
    """

    bounded_limit = max(1, min(int(limit), 2000))
    if not document_types:
        return []

    query = """
        select
            dc.id as chunk_id,
            dc.document_id,
            dc.chunk_index,
            dc.chunk_text,
            dc.token_count,
            d.document_type,
            d.title as document_title
        from document_chunks dc
        join documents d
          on d.id = dc.document_id
        where d.document_type = any(%(document_types)s)
          and dc.embedding is null
    """

    query_parameters: dict[str, Any] = {
        "document_types": list(document_types),
        "limit": bounded_limit,
    }

    if linked_source_record_id_prefixes:
        normalized_prefixes = [
            prefix.strip()
            for prefix in linked_source_record_id_prefixes
            if isinstance(prefix, str) and prefix.strip() != ""
        ]
        if normalized_prefixes:
            query += """
              and exists (
                    select 1
                    from source_record_links srl
                    join source_records sr
                      on sr.id = srl.source_record_id
                    where srl.document_id = d.id
                      and sr.source_record_id like any(%(source_record_id_patterns)s)
              )
            """
            query_parameters["source_record_id_patterns"] = [
                f"{prefix}%" for prefix in normalized_prefixes
            ]

    query += """
        order by d.updated_at desc nulls last, dc.document_id desc, dc.chunk_index asc
        limit %(limit)s
    """

    with postgres_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                query,
                query_parameters,
            )
            rows = cursor.fetchall()

    return [dict(row) for row in rows]


def backfill_chunk_embeddings(
    *,
    document_types: tuple[str, ...] = ("resume", "job_spec"),
    linked_source_record_id_prefixes: tuple[str, ...] | None = None,
    limit: int = 100,
    batch_size: int = 25,
    dry_run: bool = False,
) -> dict[str, Any]:
    """
    Generate and persist embeddings for existing chunk rows.
    """

    chunks = list_chunks_missing_embeddings(
        document_types=document_types,
        linked_source_record_id_prefixes=linked_source_record_id_prefixes,
        limit=limit,
    )

    if dry_run:
        return {
            "embedding_configuration": summarize_embedding_configuration(),
            "chunks_selected": len(chunks),
            "chunks_embedded": 0,
            "dry_run": True,
            "sample_chunks": [
                {
                    "chunk_id": chunk["chunk_id"],
                    "document_id": chunk["document_id"],
                    "document_type": chunk["document_type"],
                    "document_title": chunk["document_title"],
                    "chunk_index": chunk["chunk_index"],
                    "token_count": chunk["token_count"],
                }
                for chunk in chunks[:10]
            ],
        }

    normalized_batch_size = max(1, min(int(batch_size), 100))
    embedded_chunk_count = 0

    with postgres_connection() as connection:
        with connection.cursor() as cursor:
            for start in range(0, len(chunks), normalized_batch_size):
                batch = chunks[start : start + normalized_batch_size]
                texts = [chunk["chunk_text"] for chunk in batch]
                vectors = embed_texts(
                    texts,
                    workflow="document_chunk_embedding_batch",
                )
                if len(vectors) != len(batch):
                    raise RuntimeError(
                        "Embedding provider returned a mismatched vector count."
                    )

                for chunk, vector in zip(batch, vectors, strict=True):
                    cursor.execute(
                        """
                        update document_chunks
                        set embedding = %(embedding)s::vector
                        where id = %(chunk_id)s
                        """,
                        {
                            "embedding": vector_to_pgvector_literal(vector),
                            "chunk_id": chunk["chunk_id"],
                        },
                    )
                    embedded_chunk_count += 1

        connection.commit()

    return {
        "embedding_configuration": summarize_embedding_configuration(),
        "chunks_selected": len(chunks),
        "chunks_embedded": embedded_chunk_count,
        "dry_run": False,
    }


__all__ = [
    "backfill_chunk_embeddings",
    "list_chunks_missing_embeddings",
]
