"""
Hybrid candidate retrieval for recruiter search and shortlist flows.

This service merges:

- existing full-text resume search
- structured semantic block search

The aim is pragmatic: keep the current FTS path working while the new semantic
layer is backfilled and validated.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from backend.db.candidate_semantic_blocks import search_candidates_by_semantic_blocks
from backend.db.candidates import search_candidates_by_resume_text

logger = logging.getLogger(__name__)


_TEXT_QUERY_STOP_WORDS = {
    "a",
    "about",
    "across",
    "also",
    "an",
    "and",
    "any",
    "are",
    "as",
    "at",
    "be",
    "been",
    "before",
    "between",
    "brief",
    "build",
    "by",
    "can",
    "current",
    "description",
    "do",
    "essential",
    "experience",
    "for",
    "from",
    "grade",
    "has",
    "have",
    "how",
    "i",
    "ideally",
    "in",
    "into",
    "is",
    "it",
    "its",
    "just",
    "key",
    "large",
    "location",
    "looking",
    "modern",
    "more",
    "most",
    "need",
    "of",
    "on",
    "or",
    "production",
    "qualification",
    "qualifications",
    "reporting",
    "requirements",
    "role",
    "salary",
    "search",
    "senior",
    "should",
    "show",
    "someone",
    "strong",
    "such",
    "systems",
    "that",
    "the",
    "their",
    "them",
    "there",
    "this",
    "title",
    "to",
    "use",
    "we",
    "week",
    "what",
    "when",
    "where",
    "who",
    "with",
    "worked",
    "workflow",
}
_TEXT_QUERY_TOKEN_PATTERN = re.compile(r"[A-Za-z0-9+#./-]+")
_TEXT_QUERY_BOOSTED_TERMS = {
    "analyst",
    "analytics",
    "aws",
    "c#",
    "c++",
    "cloud",
    "cognos",
    "data",
    "developer",
    "docker",
    "etl",
    "finance",
    "financial",
    "hft",
    "ibm",
    "java",
    "kdb",
    "kubernetes",
    "otc",
    "planning",
    "pricing",
    "python",
    "quant",
    "quantitative",
    "q/kdb+",
    "rust",
    "sql",
    "tm1",
    "trading",
    "turbointegrator",
}
_TEXT_QUERY_LOW_SIGNAL_TERMS = {
    "business",
    "company",
    "customer",
    "customers",
    "delivery",
    "global",
    "group",
    "industry",
    "information",
    "lead",
    "management",
    "manager",
    "market",
    "markets",
    "office",
    "partner",
    "project",
    "projects",
    "support",
    "team",
    "working",
}


def _score_retrieval_term(*, original_term: str, canonical_term: str) -> int:
    score = 0

    if canonical_term in _TEXT_QUERY_BOOSTED_TERMS:
        score += 8
    if canonical_term in _TEXT_QUERY_LOW_SIGNAL_TERMS:
        score -= 4
    if any(character.isdigit() for character in canonical_term):
        score += 5
    if any(character in canonical_term for character in "+#/."):
        score += 4
    if original_term.isupper() and len(original_term) >= 2:
        score += 2

    term_length = len(canonical_term)
    if term_length >= 12:
        score += 3
    elif term_length >= 8:
        score += 2
    elif term_length >= 5:
        score += 1

    return score


def derive_text_retrieval_query(
    query: str,
    *,
    max_terms: int = 9,
) -> str:
    """
    Return a tighter keyword-oriented query for the FTS side of hybrid search.
    """

    normalized_query = query.strip()
    if normalized_query == "":
        return ""

    candidate_terms: list[tuple[int, int, str]] = []
    seen_terms: set[str] = set()

    for index, original_term in enumerate(
        _TEXT_QUERY_TOKEN_PATTERN.findall(normalized_query),
    ):
        canonical_term = (
            original_term.lower().strip().strip(".,;:!?()[]{}<>\"'")
        )
        if len(canonical_term) < 2:
            continue
        if canonical_term in _TEXT_QUERY_STOP_WORDS:
            continue
        if canonical_term in seen_terms:
            continue

        seen_terms.add(canonical_term)
        candidate_terms.append(
            (
                _score_retrieval_term(
                    original_term=original_term,
                    canonical_term=canonical_term,
                ),
                index,
                canonical_term,
            ),
        )

    bounded_max_terms = max(1, min(int(max_terms), 32))
    if candidate_terms:
        ranked_terms = sorted(
            candidate_terms,
            key=lambda row: (-row[0], row[1]),
        )[:bounded_max_terms]
        selected_terms = [
            canonical_term
            for _, _, canonical_term in sorted(ranked_terms, key=lambda row: row[1])
        ]
        return " ".join(selected_terms)

    return normalized_query


def build_text_retrieval_query_variants(
    query: str,
    *,
    max_terms: int = 9,
) -> list[str]:
    """
    Return progressively broader keyword queries for the FTS side.

    The FTS query path uses `websearch_to_tsquery`, so a long keyword string can
    become too strict when many terms are implicitly AND-ed together. For pasted
    role briefs we therefore try a short, high-signal query first, then back off
    to smaller subsets before giving up.
    """

    primary_query = derive_text_retrieval_query(query, max_terms=max_terms)
    if primary_query == "":
        return []

    tokens = primary_query.split()
    candidate_lengths: list[int] = []

    for length in (len(tokens), 8, 6, 4, 3):
        bounded_length = max(1, min(length, len(tokens)))
        if bounded_length not in candidate_lengths:
            candidate_lengths.append(bounded_length)

    variants = [" ".join(tokens[:length]) for length in candidate_lengths]
    return [variant for variant in variants if variant.strip()]


def search_candidates_hybrid(
    *,
    query: str,
    limit: int = 20,
    text_limit: int | None = None,
    semantic_limit: int | None = None,
    fusion_constant: int = 60,
    include_text: bool = True,
    include_semantic: bool = True,
) -> list[dict[str, Any]]:
    """
    Return hybrid candidate retrieval results for one free-text query.
    """

    normalized_query = query.strip()
    if normalized_query == "":
        return []
    text_queries = build_text_retrieval_query_variants(normalized_query)

    bounded_limit = max(1, min(int(limit), 100))
    resolved_text_limit = max(bounded_limit, min(int(text_limit or bounded_limit * 3), 100))
    resolved_semantic_limit = max(
        bounded_limit,
        min(int(semantic_limit or bounded_limit * 3), 100),
    )

    text_results: list[dict[str, Any]] = []
    semantic_results: list[dict[str, Any]] = []

    if include_text:
        for text_query in text_queries:
            text_results = search_candidates_by_resume_text(
                query=text_query,
                limit=resolved_text_limit,
            )
            if text_results:
                break

    if include_semantic:
        try:
            semantic_results = search_candidates_by_semantic_blocks(
                query=normalized_query,
                limit=resolved_semantic_limit,
            )
        except Exception:
            logger.exception(
                "Candidate semantic retrieval failed.",
                extra={
                    "query_preview": normalized_query[:120],
                    "limit": bounded_limit,
                    "semantic_limit": resolved_semantic_limit,
                },
            )
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
        retrieval_sources: list[str] = []
        if entry["text_rank"] is not None:
            retrieval_sources.append("text")
        if entry["semantic_rank"] is not None:
            retrieval_sources.append("semantic")
        if max_fused_score > 0:
            candidate["match_score"] = round(entry["fused_score"] / max_fused_score, 6)
        else:
            candidate["match_score"] = 0.0
        candidate["retrieval_sources"] = retrieval_sources
        candidate["text_rank"] = entry["text_rank"]
        candidate["semantic_rank"] = entry["semantic_rank"]
        candidate["text_score"] = round(entry["text_score"], 6)
        candidate["semantic_score"] = round(entry["semantic_score"], 6)
        candidate["semantic_block_type"] = candidate.get("block_type")
        candidate["semantic_block_label"] = candidate.get("block_label")
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
    "build_text_retrieval_query_variants",
    "derive_text_retrieval_query",
    "fuse_candidate_rankings",
    "search_candidates_hybrid",
]
