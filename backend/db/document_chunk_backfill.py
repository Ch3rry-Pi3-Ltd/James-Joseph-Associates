"""
Helpers for backfilling `document_chunks` from canonical document text.

This module is the first operational step toward semantic retrieval:

- read existing canonical document text already stored in Supabase
- split it into retrieval chunks
- persist those chunks into `document_chunks`

It does not generate embeddings yet. That comes after chunk rows exist.
"""

from __future__ import annotations

from typing import Any

from backend.db.connection import postgres_connection
from backend.services.document_chunking import (
    chunk_document_text,
    estimate_token_count,
)


def list_documents_for_chunk_backfill(
    *,
    document_types: tuple[str, ...] = ("resume", "job_spec"),
    include_already_chunked: bool = False,
    limit: int = 100,
) -> list[dict[str, Any]]:
    """
    Return canonical documents eligible for chunk backfill.
    """

    bounded_limit = max(1, min(int(limit), 1000))
    if not document_types:
        return []

    query = """
        select
            d.id as document_id,
            d.document_type,
            d.title,
            d.source_uri,
            d.extracted_text,
            count(dc.id) as existing_chunk_count
        from documents d
        left join document_chunks dc
          on dc.document_id = d.id
        where d.document_type = any(%(document_types)s)
          and coalesce(nullif(trim(d.extracted_text), ''), '') <> ''
        group by
            d.id,
            d.document_type,
            d.title,
            d.source_uri,
            d.extracted_text
    """

    if not include_already_chunked:
        query += """
        having count(dc.id) = 0
        """

    query += """
        order by d.updated_at desc nulls last, d.id desc
        limit %(limit)s
    """

    with postgres_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                query,
                {
                    "document_types": list(document_types),
                    "limit": bounded_limit,
                },
            )
            rows = cursor.fetchall()

    return [dict(row) for row in rows]


def backfill_document_chunks(
    *,
    document_types: tuple[str, ...] = ("resume", "job_spec"),
    include_already_chunked: bool = False,
    limit: int = 100,
    max_chars: int = 1200,
    overlap_chars: int = 150,
    dry_run: bool = False,
) -> dict[str, Any]:
    """
    Backfill chunk rows for canonical documents with extracted text.
    """

    documents = list_documents_for_chunk_backfill(
        document_types=document_types,
        include_already_chunked=include_already_chunked,
        limit=limit,
    )

    processed_documents = 0
    inserted_chunks = 0
    document_summaries: list[dict[str, Any]] = []

    if dry_run:
        for document in documents:
            chunks = chunk_document_text(
                document["extracted_text"],
                max_chars=max_chars,
                overlap_chars=overlap_chars,
            )
            document_summaries.append(
                {
                    "document_id": document["document_id"],
                    "document_type": document["document_type"],
                    "title": document.get("title"),
                    "existing_chunk_count": int(document["existing_chunk_count"]),
                    "chunk_count": len(chunks),
                }
            )

        return {
            "documents_selected": len(documents),
            "documents_processed": 0,
            "chunks_inserted": 0,
            "dry_run": True,
            "documents": document_summaries,
        }

    with postgres_connection() as connection:
        with connection.cursor() as cursor:
            for document in documents:
                chunks = chunk_document_text(
                    document["extracted_text"],
                    max_chars=max_chars,
                    overlap_chars=overlap_chars,
                )
                if not chunks:
                    document_summaries.append(
                        {
                            "document_id": document["document_id"],
                            "document_type": document["document_type"],
                            "title": document.get("title"),
                            "existing_chunk_count": int(document["existing_chunk_count"]),
                            "chunk_count": 0,
                        }
                    )
                    continue

                if include_already_chunked and int(document["existing_chunk_count"]) > 0:
                    cursor.execute(
                        """
                        delete from document_chunks
                        where document_id = %(document_id)s
                        """,
                        {"document_id": document["document_id"]},
                    )

                for chunk_index, chunk_text in enumerate(chunks):
                    cursor.execute(
                        """
                        insert into document_chunks (
                            document_id,
                            chunk_index,
                            chunk_text,
                            token_count
                        )
                        values (
                            %(document_id)s,
                            %(chunk_index)s,
                            %(chunk_text)s,
                            %(token_count)s
                        )
                        on conflict (document_id, chunk_index)
                        do update set
                            chunk_text = excluded.chunk_text,
                            token_count = excluded.token_count
                        """,
                        {
                            "document_id": document["document_id"],
                            "chunk_index": chunk_index,
                            "chunk_text": chunk_text,
                            "token_count": estimate_token_count(chunk_text),
                        },
                    )

                processed_documents += 1
                inserted_chunks += len(chunks)
                document_summaries.append(
                    {
                        "document_id": document["document_id"],
                        "document_type": document["document_type"],
                        "title": document.get("title"),
                        "existing_chunk_count": int(document["existing_chunk_count"]),
                        "chunk_count": len(chunks),
                    }
                )

        connection.commit()

    return {
        "documents_selected": len(documents),
        "documents_processed": processed_documents,
        "chunks_inserted": inserted_chunks,
        "dry_run": False,
        "documents": document_summaries,
    }


__all__ = [
    "backfill_document_chunks",
    "list_documents_for_chunk_backfill",
]
