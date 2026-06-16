"""
Benchmark FTS and hybrid candidate retrieval side by side.

This is an operator script for checking whether the semantic candidate block
layer is improving real recruiter-style search quality.
"""

from __future__ import annotations

import argparse
import json
from typing import Any

from backend.db.candidates import search_candidates_by_resume_text
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
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    queries = args.query or DEFAULT_QUERIES
    bounded_limit = max(1, min(int(args.limit), 20))

    benchmark_rows: list[dict[str, Any]] = []
    for query in queries:
        benchmark_rows.append(
            {
                "query": query,
                "fts": _compact_results(
                    search_candidates_by_resume_text(query=query, limit=bounded_limit)
                ),
                "hybrid": _compact_results(
                    search_candidates_hybrid(query=query, limit=bounded_limit)
                ),
            }
        )

    print(json.dumps(benchmark_rows, indent=2, default=str))


def _compact_results(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "candidate_id": str(result["candidate_id"]),
            "full_name": result.get("full_name"),
            "current_title": result.get("current_title"),
            "current_company_name": result.get("current_company_name"),
            "match_score": result.get("match_score"),
            "match_excerpt": (result.get("match_excerpt") or "")[:260],
        }
        for result in results
    ]


if __name__ == "__main__":
    main()
