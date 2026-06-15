"""
Run the structured candidate semantic retrieval path on a small real sample.

This script is intentionally narrow. It is for proving the new structured
semantic block layer before any broad backfill.
"""

from __future__ import annotations

import argparse
import json
from typing import Any

from backend.db.candidate_semantic_blocks import (
    backfill_candidate_semantic_blocks,
    search_candidates_by_semantic_blocks,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Build and query structured candidate semantic blocks for a small "
            "live sample."
        )
    )
    parser.add_argument(
        "--candidate-limit",
        type=int,
        default=5,
        help="Maximum number of candidates to index in this sample run.",
    )
    parser.add_argument(
        "--embedding-batch-size",
        type=int,
        default=10,
        help="Maximum number of semantic blocks to embed per API batch.",
    )
    parser.add_argument(
        "--query",
        type=str,
        default="",
        help="Optional semantic query to run after indexing the sample.",
    )
    parser.add_argument(
        "--query-limit",
        type=int,
        default=5,
        help="Maximum number of semantic matches to print.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Inspect the candidate/block selection without writing anything.",
    )
    parser.add_argument(
        "--include-already-indexed",
        action="store_true",
        help="Rebuild blocks even if the candidate already has semantic blocks.",
    )
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    backfill_summary = backfill_candidate_semantic_blocks(
        limit=args.candidate_limit,
        include_already_indexed=args.include_already_indexed,
        embedding_batch_size=args.embedding_batch_size,
        dry_run=args.dry_run,
    )

    semantic_matches: list[dict[str, Any]] = []
    normalized_query = args.query.strip()
    if normalized_query != "" and not args.dry_run:
        semantic_matches = search_candidates_by_semantic_blocks(
            query=normalized_query,
            limit=args.query_limit,
        )

    summary = {
        "backfill_summary": backfill_summary,
        "semantic_matches": semantic_matches,
    }
    print(json.dumps(summary, indent=2, default=str))


if __name__ == "__main__":
    main()
