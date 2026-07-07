"""
Candidate profile service helpers for the intelligence backend.

This module combines small database read helpers into a higher-level candidate
profile shape that later API routes, workflow steps, or service logic can use.

It gives the rest of the repository a stable way to talk about:

- reading one candidate profile
- reading the candidate's linked skills
- returning one combined backend-facing structure
- keeping composition logic out of route handlers

Keeping this logic in a service module makes the project easier to grow because:

- database query helpers stay focused on one table/query concern at a time
- route handlers do not need to coordinate multiple DB calls directly
- future workflow code can reuse one stable service function
- later enrichment logic can be added here without rewriting the DB helpers

In plain language:

- this module answers the question:

    "How does the backend assemble a candidate profile view?"

- it does not define SQL tables
- it does not create routes
- it does not write data
- it only coordinates existing read helpers
"""

from datetime import date, datetime
from typing import Any

from backend.db.candidates import get_candidate_profile
from backend.db.skills import get_candidate_skills
from backend.services.candidate_retrieval import search_candidates_hybrid


def build_candidate_profile(candidate_id: str) -> dict[str, Any] | None:
    """
    Return one combined profile structure.

    Parameters
    ----------
    candidate_id : str
        Canonical candidate UUID to look up.

    Returns
    -------
    dict[str, Any] | None
        Combined candidate profile structure.

        Returns `None` if the candidate does not exist.

    Notes
    -----
    - This function composes lower-level DB read helpers.
    - If the candidate profile does not exist, the function returns `None`
      immediately.
    - If the candidate exists, the returned structure includes:

        - the candidate profile data
        - the list of linked skills

    Returned shape
    --------------
    The returned dictionary currently looks like:

        {
            "candidate": {...},
            "skills": [...],
        }

    In plain language:

    - fetch the candidate profile
    - stop if the candidate does not exist
    - fetch the candidate skills
    - return one combined object

    Example
    -------
    Build one backend-facing candidate profile object:

        from backend.services.candidate_profiles import build_candidate_profile

        profile = build_candidate_profile(
            "33333333-3333-3333-3333-333333333331",
        )

        if profile is not None:
            print(profile["candidate"]["full_name"])
            print(profile["skills"])
    """

    candidate = get_candidate_profile(candidate_id)

    # If the candidate does not exist, do not continue to the skill query
    #   - Returning early keeps the control flow explicit and avoids pointless
    #     extra database work.
    if candidate is None:
        return None

    skills = get_candidate_skills(candidate_id)

    return {
        "candidate": candidate,
        "skills": skills,
    }


def search_candidate_resumes(
    *,
    query: str,
    limit: int = 20,
) -> dict[str, Any]:
    """
    Return one ranked resume-search result set for the canonical candidate corpus.

    Notes
    -----
    This service now uses a hybrid first pass:

    - current resume full-text search
    - structured semantic block search
    - fused ranking in one result list
    """

    normalized_query = query.strip()
    results = search_candidates_hybrid(
        query=normalized_query,
        limit=limit,
        include_text=True,
        include_semantic=True,
    )
    return {
        "query": normalized_query,
        "limit": limit,
        "results": [
            _normalize_candidate_resume_search_result(result) for result in results
        ],
    }


def _normalize_candidate_resume_search_result(
    result: dict[str, Any],
) -> dict[str, Any]:
    """
    Return one public API-safe resume-search row.
    """

    return {
        "candidate_id": _normalize_string_value(result.get("candidate_id")),
        "person_id": _normalize_string_value(result.get("person_id")),
        "full_name": _normalize_optional_string_value(result.get("full_name")),
        "current_title": _normalize_optional_string_value(
            result.get("current_title")
        ),
        "candidate_status": _normalize_optional_string_value(
            result.get("candidate_status")
        ),
        "current_company_name": _normalize_optional_string_value(
            result.get("current_company_name")
        ),
        "resume_updated_at": _normalize_optional_datetime_value(
            result.get("resume_updated_at")
        ),
        "document_id": _normalize_string_value(result.get("document_id")),
        "document_title": _normalize_optional_string_value(
            result.get("document_title")
        ),
        "document_source_uri": _normalize_optional_string_value(
            result.get("document_source_uri")
        ),
        "match_score": float(result.get("match_score") or 0.0),
        "retrieval_sources": _normalize_string_list_value(
            result.get("retrieval_sources")
        ),
        "text_rank": _normalize_optional_int_value(result.get("text_rank")),
        "semantic_rank": _normalize_optional_int_value(result.get("semantic_rank")),
        "text_score": _normalize_optional_float_value(result.get("text_score")),
        "semantic_score": _normalize_optional_float_value(
            result.get("semantic_score")
        ),
        "semantic_block_type": _normalize_optional_string_value(
            result.get("semantic_block_type") or result.get("block_type")
        ),
        "semantic_block_label": _normalize_optional_string_value(
            result.get("semantic_block_label") or result.get("block_label")
        ),
        "match_excerpt": _normalize_optional_string_value(
            result.get("match_excerpt")
        ),
    }


def _normalize_string_value(value: Any) -> str:
    return "" if value is None else str(value)


def _normalize_optional_string_value(value: Any) -> str | None:
    if value is None:
        return None
    return str(value)


def _normalize_string_list_value(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item) for item in value if item is not None]
    return [str(value)]


def _normalize_optional_int_value(value: Any) -> int | None:
    if value is None:
        return None
    return int(value)


def _normalize_optional_float_value(value: Any) -> float | None:
    if value is None:
        return None
    return float(value)


def _normalize_optional_datetime_value(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return str(value)


__all__ = [
    "build_candidate_profile",
    "search_candidate_resumes",
]
