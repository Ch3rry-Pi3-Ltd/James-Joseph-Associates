"""
Run the first small-sample semantic retrieval flow against canonical documents.

This script is intentionally conservative. It is meant to prove the end-to-end
semantic path on a handful of existing records before any broader backfill:

1. select a small sample of canonical resume/job-spec documents
2. backfill document chunks
3. backfill embeddings for those chunks
4. optionally run one vector-search query and print the top matches
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from backend.db.candidate_vector_search import search_candidates_by_resume_vector
from backend.db.document_chunk_backfill import backfill_document_chunks
from backend.db.document_embedding_backfill import backfill_chunk_embeddings


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Test semantic resume retrieval on a small sample of canonical documents."
        )
    )
    parser.add_argument(
        "--document-types",
        nargs="+",
        default=["resume"],
        help="Canonical document types to include. Default: resume",
    )
    parser.add_argument(
        "--document-limit",
        type=int,
        default=5,
        help="Maximum number of documents to chunk in the sample run.",
    )
    parser.add_argument(
        "--chunk-max-chars",
        type=int,
        default=1200,
        help="Maximum chunk character length for chunk backfill.",
    )
    parser.add_argument(
        "--chunk-overlap-chars",
        type=int,
        default=150,
        help="Overlap size between neighboring chunks.",
    )
    parser.add_argument(
        "--embedding-limit",
        type=int,
        default=50,
        help="Maximum number of chunk rows to embed in the sample run.",
    )
    parser.add_argument(
        "--embedding-batch-size",
        type=int,
        default=10,
        help="Embedding batch size for the sample run.",
    )
    parser.add_argument(
        "--query",
        type=str,
        default="python sql etl data engineer",
        help="Optional semantic retrieval query to run after backfill.",
    )
    parser.add_argument(
        "--query-limit",
        type=int,
        default=5,
        help="Maximum number of vector-search matches to print.",
    )
    parser.add_argument(
        "--skip-query",
        action="store_true",
        help="Skip the final vector-search query step.",
    )
    parser.add_argument(
        "--output-json",
        type=Path,
        default=None,
        help="Optional path to write the summary JSON.",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()

    document_types = tuple(args.document_types)

    chunk_summary = backfill_document_chunks(
        document_types=document_types,
        include_already_chunked=False,
        limit=args.document_limit,
        max_chars=args.chunk_max_chars,
        overlap_chars=args.chunk_overlap_chars,
        dry_run=False,
    )

    embedding_summary = backfill_chunk_embeddings(
        document_types=document_types,
        limit=args.embedding_limit,
        batch_size=args.embedding_batch_size,
        dry_run=False,
    )

    vector_matches: list[dict[str, Any]] = []
    if not args.skip_query:
        vector_matches = search_candidates_by_resume_vector(
            query=args.query,
            limit=args.query_limit,
        )

    summary = {
        "document_types": list(document_types),
        "chunk_summary": chunk_summary,
        "embedding_summary": embedding_summary,
        "query": None if args.skip_query else args.query,
        "vector_matches": vector_matches,
    }

    print(json.dumps(summary, indent=2, default=str))

    if args.output_json is not None:
        args.output_json.write_text(
            json.dumps(summary, indent=2, default=str),
            encoding="utf-8",
        )


if __name__ == "__main__":
    main()
