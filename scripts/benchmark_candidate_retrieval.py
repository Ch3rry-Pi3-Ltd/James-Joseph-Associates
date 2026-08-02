"""
Benchmark FTS and hybrid candidate retrieval side by side.

This is an operator script for checking whether the semantic candidate block
layer is improving real recruiter-style search quality.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from time import perf_counter
from typing import Any

from backend.db.candidates import search_candidates_by_resume_text
from backend.evaluation.quality_checks import stable_payload_fingerprint
from backend.services.candidate_matching import (
    retrieve_candidates_with_graph_context,
)
from backend.services.candidate_retrieval import search_candidates_hybrid


DEFAULT_QUERIES = [
    "Senior data engineer with strong Python, SQL, cloud platform, and ETL experience. Large datasets and production analytics systems.",
    "Low latency Java or kdb+ quant developer for trading systems, market data, and high performance engineering.",
    "Senior SRE with Kubernetes, AWS, Terraform, observability, and production platform reliability experience.",
    "Blockchain engineer with Solidity, TypeScript, React, and Web3 infrastructure experience.",
]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Benchmark FTS and hybrid candidate retrieval side by side."
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=5,
        help="Maximum number of results to show per retrieval mode.",
    )
    parser.add_argument(
        "--query",
        action="append",
        default=[],
        help="Optional custom role brief. Can be supplied multiple times.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Optional path for the compact JSON benchmark artifact.",
    )
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    queries = args.query or DEFAULT_QUERIES
    bounded_limit = max(1, min(int(args.limit), 20))

    benchmark_rows: list[dict[str, Any]] = []
    for query in queries:
        benchmark_rows.append(_benchmark_query(query=query, limit=bounded_limit))

    serialized = json.dumps(benchmark_rows, indent=2, default=str)
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(f"{serialized}\n", encoding="utf-8")
    print(serialized)


def _benchmark_query(*, query: str, limit: int) -> dict[str, Any]:
    """Measure each retrieval layer independently for one role query."""

    stages = {
        "full_text": _measure_stage(
            lambda: search_candidates_by_resume_text(query=query, limit=limit)
        ),
        "semantic": _measure_stage(
            lambda: search_candidates_hybrid(
                query=query,
                limit=limit,
                include_text=False,
                include_semantic=True,
            )
        ),
        "hybrid": _measure_stage(
            lambda: search_candidates_hybrid(
                query=query,
                limit=limit,
                include_text=True,
                include_semantic=True,
            )
        ),
        "graph_assisted": _measure_stage(
            lambda: retrieve_candidates_with_graph_context(
                query=query,
                limit=limit,
            )
        ),
    }
    return {
        "query_id": sha256_query(query),
        "limit": limit,
        "stages": stages,
    }


def _measure_stage(operation) -> dict[str, Any]:
    started_at = perf_counter()
    compact_results = _compact_results(operation())
    duration_ms = max(0.0, (perf_counter() - started_at) * 1000)
    return {
        "duration_ms": round(duration_ms, 2),
        "result_count": len(compact_results),
        "result_fingerprint": stable_payload_fingerprint(compact_results),
        "results": compact_results,
    }


def sha256_query(query: str) -> str:
    """Identify a query without writing its role brief into the artifact."""

    return stable_payload_fingerprint({"query": " ".join(query.split())})[:16]


def _compact_results(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "candidate_id": str(result["candidate_id"]),
            "full_name": result.get("full_name"),
            "current_title": result.get("current_title"),
            "current_company_name": result.get("current_company_name"),
            "match_score": result.get("match_score"),
            "retrieval_sources": result.get("retrieval_sources", []),
        }
        for result in results
    ]


if __name__ == "__main__":
    main()
