"""
Bounded source metadata for recruiter-facing candidate results.

This module keeps provenance classification deterministic and separate from
LLM ranking. Contact details are deliberately not included here.
"""

from __future__ import annotations

from typing import Any

from backend.db.candidates import get_candidate_source_details


def attach_candidate_source_metadata(
    candidates: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Attach source systems and one concise source category to candidates."""

    candidate_ids = {
        str(candidate.get("candidate_id") or "").strip()
        for candidate in candidates
        if str(candidate.get("candidate_id") or "").strip()
    }
    source_details_by_candidate = get_candidate_source_details(candidate_ids)

    enriched_candidates: list[dict[str, Any]] = []
    for candidate in candidates:
        enriched_candidate = dict(candidate)
        candidate_id = str(candidate.get("candidate_id") or "")
        source_details = source_details_by_candidate.get(candidate_id, [])
        source_systems = [str(detail["source_system"]) for detail in source_details]
        enriched_candidate["source_systems"] = source_systems
        enriched_candidate["source_details"] = source_details
        enriched_candidate["source_category"] = classify_candidate_source_category(
            source_systems,
            has_resume_document=bool(
                candidate.get("document_id")
                or candidate.get("has_resume_document")
            ),
        )
        enriched_candidates.append(enriched_candidate)

    return enriched_candidates


def classify_candidate_source_category(
    source_systems: list[str],
    *,
    has_resume_document: bool = False,
) -> str:
    """Return the recruiter-facing provenance category for source systems."""

    normalized_systems = {
        str(source_system).strip().casefold()
        for source_system in source_systems
        if str(source_system).strip()
    }
    has_linked_helper = "linkedin_helper" in normalized_systems

    if has_linked_helper and has_resume_document:
        return "cross_source"
    if has_resume_document:
        return "cv_backed"
    if normalized_systems:
        return "profile_only"
    return "unknown"


__all__ = [
    "attach_candidate_source_metadata",
    "classify_candidate_source_category",
]
