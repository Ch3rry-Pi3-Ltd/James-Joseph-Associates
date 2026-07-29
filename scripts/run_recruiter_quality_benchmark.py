"""
Run a repeatable retrieval and shortlist benchmark over real recruiter briefs.

The script deliberately stores only compact candidate identity, ranking, and
provenance information. It does not write resume text or contact details to
the benchmark artifact.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from backend.db.connection import postgres_connection
from backend.services.candidate_matching import (
    build_candidate_job_description_shortlist,
)
from backend.services.candidate_retrieval import search_candidates_hybrid


DEFAULT_FIXTURE = Path("docs/evaluation/recruiter_role_briefs.json")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the versioned recruiter retrieval-quality benchmark."
    )
    parser.add_argument(
        "--fixture",
        type=Path,
        default=DEFAULT_FIXTURE,
        help="JSON fixture containing role briefs and previous shortlists.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Optional path for the JSON benchmark artifact.",
    )
    parser.add_argument(
        "--retrieval-limit",
        type=int,
        default=25,
        help="Candidate pool size for hybrid retrieval and reranking.",
    )
    parser.add_argument(
        "--shortlist-limit",
        type=int,
        default=5,
        help="Final LLM shortlist size.",
    )
    parser.add_argument(
        "--skip-shortlist",
        action="store_true",
        help="Run retrieval only without sending candidate evidence to the LLM.",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    roles = json.loads(args.fixture.read_text(encoding="utf-8"))
    results = [
        _benchmark_role(
            role=role,
            retrieval_limit=args.retrieval_limit,
            shortlist_limit=args.shortlist_limit,
            include_shortlist=not args.skip_shortlist,
        )
        for role in roles
    ]
    artifact = {
        "fixture": str(args.fixture),
        "retrieval_limit": max(1, min(int(args.retrieval_limit), 100)),
        "shortlist_limit": max(1, min(int(args.shortlist_limit), 10)),
        "roles": results,
        "summary": _summarize_results(results),
    }
    serialized = json.dumps(artifact, indent=2, default=str, ensure_ascii=True)

    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(f"{serialized}\n", encoding="utf-8")

    print(serialized)


def _benchmark_role(
    *,
    role: dict[str, Any],
    retrieval_limit: int,
    shortlist_limit: int,
    include_shortlist: bool,
) -> dict[str, Any]:
    brief = str(role["brief"])
    retrieved = search_candidates_hybrid(
        query=brief,
        limit=retrieval_limit,
        include_text=True,
        include_semantic=True,
    )
    shortlist_response = (
        build_candidate_job_description_shortlist(
            job_description=brief,
            retrieval_limit=retrieval_limit,
            shortlist_limit=shortlist_limit,
        )
        if include_shortlist
        else {
            "retrieved_candidate_count": len(retrieved),
            "shortlisted_candidates": [],
        }
    )

    candidate_ids = {
        str(row["candidate_id"])
        for row in [
            *retrieved,
            *shortlist_response["shortlisted_candidates"],
        ]
    }
    source_systems = _load_candidate_source_systems(candidate_ids)
    previous_names = {
        _normalize_name(name) for name in role.get("previous_shortlist", [])
    }
    compact_retrieval = [
        _compact_candidate(
            row,
            rank=rank,
            source_systems=source_systems,
        )
        for rank, row in enumerate(retrieved, start=1)
    ]
    compact_shortlist = [
        _compact_candidate(
            row,
            rank=rank,
            source_systems=source_systems,
        )
        for rank, row in enumerate(
            shortlist_response["shortlisted_candidates"],
            start=1,
        )
    ]
    current_names = {
        _normalize_name(row.get("full_name"))
        for row in shortlist_response["shortlisted_candidates"]
        if row.get("full_name")
    }
    retrieval_names_by_rank = {
        _normalize_name(row.get("full_name")): rank
        for rank, row in enumerate(retrieved, start=1)
        if row.get("full_name")
    }
    previous_retrieval_hits = [
        {
            "full_name": name,
            "rank": retrieval_names_by_rank[_normalize_name(name)],
        }
        for name in role.get("previous_shortlist", [])
        if _normalize_name(name) in retrieval_names_by_rank
    ]

    return {
        "id": role["id"],
        "company": role["company"],
        "title": role["title"],
        "source_file": role["source_file"],
        "brief": brief,
        "previous_shortlist": role.get("previous_shortlist", []),
        "retrieved_candidate_count": len(retrieved),
        "retrieval": compact_retrieval,
        "shortlist": compact_shortlist,
        "previous_shortlist_retrieval_hits": previous_retrieval_hits,
        "previous_shortlist_retrieval_count": len(previous_retrieval_hits),
        "previous_shortlist_overlap": sorted(previous_names & current_names),
        "previous_shortlist_overlap_count": len(previous_names & current_names),
        "linkedin_helper_only_retrieval_count": _count_category(
            compact_retrieval,
            "linkedin_helper_only",
        ),
        "linkedin_helper_only_shortlist_count": _count_category(
            compact_shortlist,
            "linkedin_helper_only",
        ),
        "cross_source_retrieval_count": _count_category(
            compact_retrieval,
            "cross_source",
        ),
        "cross_source_shortlist_count": _count_category(
            compact_shortlist,
            "cross_source",
        ),
    }


def _load_candidate_source_systems(
    candidate_ids: set[str],
) -> dict[str, list[str]]:
    if not candidate_ids:
        return {}

    with postgres_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                with requested_candidates as (
                    select id, person_id
                    from candidates
                    where id = any(%(candidate_ids)s::uuid[])
                ),
                linked_sources as (
                    select
                        requested.id as candidate_id,
                        source.source_system
                    from requested_candidates requested
                    join source_record_links link
                      on link.candidate_id = requested.id
                    join source_records source
                      on source.id = link.source_record_id

                    union

                    select
                        requested.id as candidate_id,
                        source.source_system
                    from requested_candidates requested
                    join source_record_links link
                      on link.person_id = requested.person_id
                    join source_records source
                      on source.id = link.source_record_id
                )
                select
                    candidate_id,
                    array_agg(distinct source_system order by source_system)
                        as source_systems
                from linked_sources
                group by candidate_id
                """,
                {"candidate_ids": sorted(candidate_ids)},
            )
            rows = cursor.fetchall()

    return {
        str(row["candidate_id"]): list(row["source_systems"] or [])
        for row in rows
    }


def _compact_candidate(
    candidate: dict[str, Any],
    *,
    rank: int,
    source_systems: dict[str, list[str]],
) -> dict[str, Any]:
    candidate_id = str(candidate["candidate_id"])
    systems = source_systems.get(candidate_id, [])
    return {
        "rank": rank,
        "candidate_id": candidate_id,
        "full_name": candidate.get("full_name"),
        "current_title": candidate.get("current_title"),
        "current_company_name": candidate.get("current_company_name"),
        "retrieval_score": candidate.get(
            "retrieval_score",
            candidate.get("match_score"),
        ),
        "fit_score": candidate.get("fit_score"),
        "retrieval_sources": candidate.get("retrieval_sources", []),
        "source_systems": systems,
        "source_category": _source_category(systems),
        "fit_summary": candidate.get("fit_summary"),
        "strengths": candidate.get("strengths", []),
        "gaps": candidate.get("gaps", []),
    }


def _source_category(source_systems: list[str]) -> str:
    systems = set(source_systems)
    if systems == {"linkedin_helper"}:
        return "linkedin_helper_only"
    if "linkedin_helper" in systems:
        return "cross_source"
    if systems:
        return "other_source"
    return "unknown"


def _normalize_name(value: Any) -> str:
    return " ".join(str(value or "").casefold().split())


def _count_category(rows: list[dict[str, Any]], category: str) -> int:
    return sum(row["source_category"] == category for row in rows)


def _summarize_results(results: list[dict[str, Any]]) -> dict[str, int]:
    return {
        "roles": len(results),
        "retrieved_candidates": sum(
            len(result["retrieval"]) for result in results
        ),
        "shortlisted_candidates": sum(
            len(result["shortlist"]) for result in results
        ),
        "linkedin_helper_only_retrieval": sum(
            result["linkedin_helper_only_retrieval_count"] for result in results
        ),
        "linkedin_helper_only_shortlist": sum(
            result["linkedin_helper_only_shortlist_count"] for result in results
        ),
        "cross_source_retrieval": sum(
            result["cross_source_retrieval_count"] for result in results
        ),
        "cross_source_shortlist": sum(
            result["cross_source_shortlist_count"] for result in results
        ),
        "previous_shortlist_overlap": sum(
            result["previous_shortlist_overlap_count"] for result in results
        ),
        "previous_shortlist_retrieval_hits": sum(
            result["previous_shortlist_retrieval_count"] for result in results
        ),
    }


if __name__ == "__main__":
    main()
