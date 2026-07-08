"""
Bulk backfill structured candidate semantic blocks.

This is the operator-grade companion to the tiny sample script. It exists so we
can build the structured semantic retrieval layer across the current canonical
candidate corpus without reingesting source CV files.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Backfill structured candidate semantic blocks across the canonical "
            "candidate corpus."
        )
    )
    parser.add_argument(
        "--candidate-limit",
        type=int,
        default=250,
        help="Maximum candidates to process per round.",
    )
    parser.add_argument(
        "--embedding-batch-size",
        type=int,
        default=25,
        help="Maximum semantic blocks to embed per provider batch.",
    )
    parser.add_argument(
        "--candidate-id",
        action="append",
        default=[],
        help="Optional candidate UUID to target. Repeat for multiple candidates.",
    )
    parser.add_argument(
        "--include-already-indexed",
        action="store_true",
        help="Rebuild blocks even when a candidate already has semantic blocks.",
    )
    parser.add_argument(
        "--loop-until-empty",
        action="store_true",
        help="Keep running rounds until no further candidates are selected.",
    )
    parser.add_argument(
        "--max-rounds",
        type=int,
        default=1000,
        help="Hard stop for loop mode to avoid accidental infinite runs.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Inspect selection only without writing embeddings or rows.",
    )
    return parser


def main() -> None:
    from backend.db.candidate_semantic_blocks import (
        backfill_candidate_semantic_blocks,
    )

    parser = build_parser()
    args = parser.parse_args()

    candidate_ids = [candidate_id.strip() for candidate_id in args.candidate_id if candidate_id.strip()]
    loop_until_empty = bool(args.loop_until_empty) and not candidate_ids
    max_rounds = max(1, int(args.max_rounds))

    run_summaries: list[dict[str, Any]] = []

    for round_number in range(1, max_rounds + 1):
        summary = backfill_candidate_semantic_blocks(
            limit=max(1, int(args.candidate_limit)),
            candidate_ids=candidate_ids or None,
            include_already_indexed=bool(args.include_already_indexed),
            embedding_batch_size=max(1, int(args.embedding_batch_size)),
            dry_run=bool(args.dry_run),
        )
        run_summaries.append(
            {
                "round": round_number,
                **summary,
            }
        )

        if not loop_until_empty:
            break

        if int(summary["candidates_selected"]) == 0:
            break

    aggregate_summary = {
        "rounds_run": len(run_summaries),
        "candidate_limit_per_round": max(1, int(args.candidate_limit)),
        "embedding_batch_size": max(1, int(args.embedding_batch_size)),
        "include_already_indexed": bool(args.include_already_indexed),
        "dry_run": bool(args.dry_run),
        "loop_until_empty": loop_until_empty,
        "candidate_ids": candidate_ids,
        "candidates_selected_total": sum(
            int(run["candidates_selected"]) for run in run_summaries
        ),
        "candidates_processed_total": sum(
            int(run["candidates_processed"]) for run in run_summaries
        ),
        "blocks_inserted_total": sum(
            int(run["blocks_inserted"]) for run in run_summaries
        ),
        "blocks_embedded_total": sum(
            int(run["blocks_embedded"]) for run in run_summaries
        ),
        "runs": run_summaries,
    }
    print(json.dumps(aggregate_summary, indent=2, default=str))


if __name__ == "__main__":
    main()
