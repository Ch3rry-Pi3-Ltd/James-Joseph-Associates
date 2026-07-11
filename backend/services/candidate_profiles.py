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

from backend.db.candidates import (
    get_candidate_profile,
    search_candidates_by_company_name,
)
from backend.db.contacts import search_contacts_by_company_name
from backend.db.interactions import search_interactions_by_company_name
from backend.db.opportunities import search_opportunities_by_company_name
from backend.db.skills import get_candidate_skills
from backend.db.jobs import search_jobs_by_company_name
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


def discover_candidates_by_company(
    *,
    company_name: str,
    limit: int = 20,
) -> dict[str, Any]:
    """
    Return one ranked candidate list for a recruiter company-discovery query.
    """

    normalized_company_name = company_name.strip()
    results = search_candidates_by_company_name(
        company_name=normalized_company_name,
        limit=limit,
    )
    return {
        "company_name": normalized_company_name,
        "limit": limit,
        "results": [
            _normalize_candidate_company_discovery_result(result)
            for result in results
        ],
    }


def discover_jobs_by_company(
    *,
    company_name: str,
    limit: int = 20,
) -> dict[str, Any]:
    """
    Return one ranked job list for a recruiter company query.
    """

    normalized_company_name = company_name.strip()
    results = search_jobs_by_company_name(
        company_name=normalized_company_name,
        limit=limit,
    )
    return {
        "company_name": normalized_company_name,
        "limit": limit,
        "results": [
            _normalize_company_job_discovery_result(result) for result in results
        ],
    }


def discover_contacts_by_company(
    *,
    company_name: str,
    limit: int = 20,
) -> dict[str, Any]:
    """
    Return one ranked contact/hiring-manager list for a recruiter company query.
    """

    normalized_company_name = company_name.strip()
    results = search_contacts_by_company_name(
        company_name=normalized_company_name,
        limit=limit,
    )
    return {
        "company_name": normalized_company_name,
        "limit": limit,
        "results": [
            _normalize_company_contact_discovery_result(result) for result in results
        ],
    }


def discover_interactions_by_company(
    *,
    company_name: str,
    limit: int = 20,
) -> dict[str, Any]:
    """
    Return recent interaction evidence for people linked to one company.
    """

    normalized_company_name = company_name.strip()
    results = search_interactions_by_company_name(
        company_name=normalized_company_name,
        limit=limit,
    )
    return {
        "company_name": normalized_company_name,
        "limit": limit,
        "results": [
            _normalize_company_interaction_discovery_result(result)
            for result in results
        ],
    }


def discover_opportunities_by_company(
    *,
    company_name: str,
    limit: int = 20,
) -> dict[str, Any]:
    """
    Return recent opportunities for one recruiter company query.
    """

    normalized_company_name = company_name.strip()
    results = search_opportunities_by_company_name(
        company_name=normalized_company_name,
        limit=limit,
    )
    return {
        "company_name": normalized_company_name,
        "limit": limit,
        "results": [
            _normalize_company_opportunity_discovery_result(result)
            for result in results
        ],
    }


def discover_company_leads_for_candidate(
    *,
    candidate_id: str,
    company_name: str,
    limit: int = 10,
) -> dict[str, Any] | None:
    """
    Return a candidate-first company outreach view for one target company.

    This supports the recruiter workflow:

    - "I have a candidate"
    - "I want to pitch them to company X"
    - "show me who we know there, what jobs we already have there, and any
      prior interaction evidence tied to that company"
    """

    profile = build_candidate_profile(candidate_id)
    if profile is None:
        return None

    normalized_company_name = company_name.strip()

    contacts_result = discover_contacts_by_company(
        company_name=normalized_company_name,
        limit=limit,
    )
    interactions_result = discover_interactions_by_company(
        company_name=normalized_company_name,
        limit=limit,
    )
    jobs_result = discover_jobs_by_company(
        company_name=normalized_company_name,
        limit=limit,
    )
    opportunities_result = discover_opportunities_by_company(
        company_name=normalized_company_name,
        limit=limit,
    )
    peer_candidates_result = discover_candidates_by_company(
        company_name=normalized_company_name,
        limit=limit,
    )

    candidate = profile["candidate"]
    peer_candidates = [
        result
        for result in peer_candidates_result["results"]
        if result.get("candidate_id") != candidate_id
    ][:limit]

    skill_names: list[str] = []
    seen_skill_names: set[str] = set()
    for skill in profile["skills"]:
        skill_name = (
            skill.get("canonical_name")
            or skill.get("skill_name")
            or ""
        ).strip()
        if skill_name == "":
            continue
        normalized_skill_name = skill_name.lower()
        if normalized_skill_name in seen_skill_names:
            continue
        seen_skill_names.add(normalized_skill_name)
        skill_names.append(skill_name)

    current_company_name = (candidate.get("current_company_name") or "").strip()

    return {
        "candidate": candidate,
        "skills": profile["skills"],
        "skill_names": skill_names,
        "company_name": normalized_company_name,
        "candidate_already_at_company": (
            current_company_name != ""
            and current_company_name.lower() == normalized_company_name.lower()
        ),
        "peer_candidates": peer_candidates,
        "contacts": contacts_result["results"],
        "interactions": interactions_result["results"],
        "jobs": jobs_result["results"],
        "opportunities": opportunities_result["results"],
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


def _normalize_candidate_company_discovery_result(
    result: dict[str, Any],
) -> dict[str, Any]:
    """
    Return one public API-safe company-discovery row.
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
        "company_match_source": _normalize_string_value(
            result.get("company_match_source")
        ),
        "company_match_score": float(result.get("company_match_score") or 0.0),
        "match_excerpt": _normalize_optional_string_value(
            result.get("match_excerpt")
        ),
    }


def _normalize_company_job_discovery_result(
    result: dict[str, Any],
) -> dict[str, Any]:
    """
    Return one public API-safe company-job discovery row.
    """

    return {
        "job_id": _normalize_string_value(result.get("job_id")),
        "title": _normalize_optional_string_value(result.get("title")),
        "status": _normalize_optional_string_value(result.get("status")),
        "source": _normalize_optional_string_value(result.get("source")),
        "owner_name": _normalize_optional_string_value(result.get("owner_name")),
        "location": _normalize_optional_string_value(result.get("location")),
        "workplace_type": _normalize_optional_string_value(
            result.get("workplace_type")
        ),
        "employment_type": _normalize_optional_string_value(
            result.get("employment_type")
        ),
        "updated_from_source_at": _normalize_optional_datetime_value(
            result.get("updated_from_source_at")
        ),
        "company_id": _normalize_optional_string_value(result.get("company_id")),
        "company_name": _normalize_optional_string_value(result.get("company_name")),
        "hiring_manager_contact_id": _normalize_optional_string_value(
            result.get("hiring_manager_contact_id")
        ),
        "hiring_manager_person_id": _normalize_optional_string_value(
            result.get("hiring_manager_person_id")
        ),
        "hiring_manager_name": _normalize_optional_string_value(
            result.get("hiring_manager_name")
        ),
        "hiring_manager_email": _normalize_optional_string_value(
            result.get("hiring_manager_email")
        ),
        "hiring_manager_phone": _normalize_optional_string_value(
            result.get("hiring_manager_phone")
        ),
        "hiring_manager_role_title": _normalize_optional_string_value(
            result.get("hiring_manager_role_title")
        ),
        "company_match_source": _normalize_string_value(
            result.get("company_match_source")
        ),
    }


def _normalize_company_contact_discovery_result(
    result: dict[str, Any],
) -> dict[str, Any]:
    """
    Return one public API-safe company-contact discovery row.
    """

    return {
        "contact_id": _normalize_string_value(result.get("contact_id")),
        "person_id": _normalize_string_value(result.get("person_id")),
        "full_name": _normalize_optional_string_value(result.get("full_name")),
        "primary_email": _normalize_optional_string_value(
            result.get("primary_email")
        ),
        "primary_phone": _normalize_optional_string_value(
            result.get("primary_phone")
        ),
        "linkedin_url": _normalize_optional_string_value(
            result.get("linkedin_url")
        ),
        "location": _normalize_optional_string_value(result.get("location")),
        "headline": _normalize_optional_string_value(result.get("headline")),
        "company_id": _normalize_optional_string_value(result.get("company_id")),
        "company_name": _normalize_optional_string_value(result.get("company_name")),
        "role_title": _normalize_optional_string_value(result.get("role_title")),
        "contact_type": _normalize_optional_string_value(result.get("contact_type")),
        "seniority": _normalize_optional_string_value(result.get("seniority")),
        "is_hiring_manager": bool(result.get("is_hiring_manager")),
        "role_is_current": (
            None
            if result.get("role_is_current") is None
            else bool(result.get("role_is_current"))
        ),
        "role_start_date": _normalize_optional_datetime_value(
            result.get("role_start_date")
        ),
        "role_end_date": _normalize_optional_datetime_value(
            result.get("role_end_date")
        ),
        "company_match_source": _normalize_string_value(
            result.get("company_match_source")
        ),
    }


def _normalize_company_interaction_discovery_result(
    result: dict[str, Any],
) -> dict[str, Any]:
    """
    Return one public API-safe company-interaction discovery row.
    """

    return {
        "interaction_id": _normalize_string_value(result.get("interaction_id")),
        "interaction_type": _normalize_optional_string_value(
            result.get("interaction_type")
        ),
        "occurred_at": _normalize_optional_datetime_value(result.get("occurred_at")),
        "subject": _normalize_optional_string_value(result.get("subject")),
        "summary": _normalize_optional_string_value(result.get("summary")),
        "body": _normalize_optional_string_value(result.get("body")),
        "source_system": _normalize_optional_string_value(result.get("source_system")),
        "person_id": _normalize_optional_string_value(result.get("person_id")),
        "candidate_id": _normalize_optional_string_value(result.get("candidate_id")),
        "company_id": _normalize_optional_string_value(result.get("company_id")),
        "company_name": _normalize_optional_string_value(result.get("company_name")),
        "full_name": _normalize_optional_string_value(result.get("full_name")),
        "role_title": _normalize_optional_string_value(result.get("role_title")),
        "contact_id": _normalize_optional_string_value(result.get("contact_id")),
        "job_id": _normalize_optional_string_value(result.get("job_id")),
        "job_title": _normalize_optional_string_value(result.get("job_title")),
        "candidate_last_contacted_at": _normalize_optional_datetime_value(
            result.get("candidate_last_contacted_at")
        ),
        "matched_entity_type": _normalize_string_value(
            result.get("matched_entity_type")
        ),
    }


def _normalize_company_opportunity_discovery_result(
    result: dict[str, Any],
) -> dict[str, Any]:
    """
    Return one public API-safe company-opportunity discovery row.
    """

    return {
        "opportunity_id": _normalize_string_value(result.get("opportunity_id")),
        "title": _normalize_optional_string_value(result.get("title")),
        "smart_summary": _normalize_optional_string_value(
            result.get("smart_summary")
        ),
        "stage": _normalize_optional_string_value(result.get("stage")),
        "last_contact_at": _normalize_optional_datetime_value(
            result.get("last_contact_at")
        ),
        "next_task_at": _normalize_optional_datetime_value(
            result.get("next_task_at")
        ),
        "value": _normalize_optional_float_value(result.get("value")),
        "company_id": _normalize_optional_string_value(result.get("company_id")),
        "company_name": _normalize_optional_string_value(result.get("company_name")),
        "contact_id": _normalize_optional_string_value(result.get("contact_id")),
        "contact_person_id": _normalize_optional_string_value(
            result.get("contact_person_id")
        ),
        "contact_name": _normalize_optional_string_value(result.get("contact_name")),
        "contact_email": _normalize_optional_string_value(
            result.get("contact_email")
        ),
        "contact_phone": _normalize_optional_string_value(
            result.get("contact_phone")
        ),
        "contact_role_title": _normalize_optional_string_value(
            result.get("contact_role_title")
        ),
        "company_match_source": _normalize_string_value(
            result.get("company_match_source")
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
    "discover_candidates_by_company",
    "discover_company_leads_for_candidate",
    "discover_contacts_by_company",
    "discover_interactions_by_company",
    "discover_jobs_by_company",
    "discover_opportunities_by_company",
    "search_candidate_resumes",
]
