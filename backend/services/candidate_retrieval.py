"""
Hybrid candidate retrieval for recruiter search and shortlist flows.

This service merges:

- existing full-text resume search
- structured semantic block search

The aim is pragmatic: keep the current FTS path working while the new semantic
layer is backfilled and validated.
"""

from __future__ import annotations

from typing import Any

from backend.db.candidate_semantic_blocks import search_candidates_by_semantic_blocks
from backend.db.candidates import search_candidates_by_resume_text


def search_candidates_hybrid(
    *,
    query: str,
    limit: int = 20,
    text_limit: int | None = None,
    semantic_limit: int | None = None,
    fusion_constant: int = 60,
) -> list[dict[str, Any]]:
    """
    Return hybrid candidate retrieval results for one free-text query.
    """

    normalized_query = query.strip()
    if normalized_query == "":
        return []

    bounded_limit = max(1, min(int(limit), 100))
    resolved_text_limit = max(bounded_limit, min(int(text_limit or bounded_limit * 3), 100))
    resolved_semantic_limit = max(
        bounded_limit,
        min(int(semantic_limit or bounded_limit * 3), 100),
    )

    text_results = search_candidates_by_resume_text(
        query=normalized_query,
        limit=resolved_text_limit,
    )

    try:
        semantic_results = search_candidates_by_semantic_blocks(
            query=normalized_query,
            limit=resolved_semantic_limit,
        )
    except Exception:
        semantic_results = []

    return fuse_candidate_rankings(
        text_results=text_results,
        semantic_results=semantic_results,
        limit=bounded_limit,
        fusion_constant=fusion_constant,
    )


def fuse_candidate_rankings(
    *,
    text_results: list[dict[str, Any]],
    semantic_results: list[dict[str, Any]],
    limit: int,
    fusion_constant: int = 60,
) -> list[dict[str, Any]]:
    """
    Merge candidate rankings with reciprocal-rank-style scoring.
    """

    by_candidate_id: dict[str, dict[str, Any]] = {}

    for source_name, results in (
        ("text", text_results),
        ("semantic", semantic_results),
    ):
        for rank, result in enumerate(results, start=1):
            candidate_id = str(result["candidate_id"])
            entry = by_candidate_id.setdefault(
                candidate_id,
                {
                    "candidate": dict(result),
                    "fused_score": 0.0,
                    "text_rank": None,
                    "semantic_rank": None,
                    "text_score": 0.0,
                    "semantic_score": 0.0,
                },
            )

            entry["fused_score"] += 1.0 / (fusion_constant + rank)
            entry[f"{source_name}_rank"] = rank
            entry[f"{source_name}_score"] = float(result.get("match_score") or 0.0)
            _merge_candidate_payload(
                entry["candidate"],
                result,
                prefer_source=source_name,
            )

    ranked_entries = sorted(
        by_candidate_id.values(),
        key=lambda entry: (
            entry["fused_score"],
            entry["semantic_score"],
            entry["text_score"],
        ),
        reverse=True,
    )
    max_fused_score = ranked_entries[0]["fused_score"] if ranked_entries else 0.0

    fused_results: list[dict[str, Any]] = []
    for entry in ranked_entries[: max(1, min(int(limit), 100))]:
        candidate = dict(entry["candidate"])
        if max_fused_score > 0:
            candidate["match_score"] = round(entry["fused_score"] / max_fused_score, 6)
        else:
            candidate["match_score"] = 0.0
        fused_results.append(candidate)

    return fused_results


def _merge_candidate_payload(
    base: dict[str, Any],
    incoming: dict[str, Any],
    *,
    prefer_source: str,
) -> None:
    for key, value in incoming.items():
        if key == "match_score":
            continue
        if key not in base or base.get(key) in (None, ""):
            base[key] = value

    incoming_excerpt = incoming.get("match_excerpt")
    if not incoming_excerpt:
        return

    if prefer_source == "semantic":
        base["match_excerpt"] = incoming_excerpt
        return

    if not base.get("match_excerpt"):
        base["match_excerpt"] = incoming_excerpt


__all__ = [
    "fuse_candidate_rankings",
    "search_candidates_hybrid",
]
