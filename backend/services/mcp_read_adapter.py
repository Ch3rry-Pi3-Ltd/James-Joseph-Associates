"""
Read-only recruiter data adapter for MCP-style clients.

This module exposes a small, bounded service surface over the canonical
candidate/company context helpers so a chat-style client can query the data
layer without talking to raw database helpers directly.
"""

from __future__ import annotations

from typing import Any

from backend.db.candidates import get_candidate_current_resume_document
from backend.db.companies import list_canonical_company_records
from backend.services.candidate_matching import build_candidate_job_description_shortlist
from backend.services.company_name_quality import assess_company_name_quality
from backend.services.candidate_profiles import (
    build_candidate_profile,
    discover_candidates_by_company,
    discover_company_leads_for_candidate as discover_company_leads_for_candidate_service,
    discover_contacts_by_company,
    discover_interactions_by_company,
    discover_jobs_by_company,
    discover_opportunities_by_company,
    search_candidate_resumes,
)


class McpReadAdapterError(RuntimeError):
    """
    Raised when the read-only adapter cannot satisfy one requested operation.
    """

    def __init__(
        self,
        message: str,
        *,
        tool: str,
        code: str = "internal_error",
        status_code: int = 500,
        stage: str = "tool_execution",
        details: list[dict[str, Any]] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.tool = tool
        self.code = code
        self.status_code = status_code
        self.stage = stage
        self.details = details or []


def search_candidates_for_role(
    *,
    role_brief: str,
    search_limit: int = 10,
    candidate_pool_limit: int = 25,
    shortlist_limit: int = 5,
    include_shortlist: bool = True,
) -> dict[str, Any]:
    """
    Return the bounded candidate-search tool output for one role brief.
    """

    normalized_role_brief = role_brief.strip()
    if normalized_role_brief == "":
        raise McpReadAdapterError(
            "Role brief must not be blank.",
            tool="search_candidates_for_role",
            code="validation_error",
            status_code=400,
            stage="validation",
            details=[{"field": "role_brief"}],
        )

    bounded_search_limit = max(1, min(int(search_limit), 50))
    bounded_candidate_pool_limit = max(1, min(int(candidate_pool_limit), 100))
    bounded_shortlist_limit = max(1, min(int(shortlist_limit), 10))

    try:
        search_results = search_candidate_resumes(
            query=normalized_role_brief,
            limit=bounded_search_limit,
        )
    except Exception as exc:
        raise McpReadAdapterError(
            "Candidate retrieval could not complete.",
            tool="search_candidates_for_role",
            code="retrieval_error",
            status_code=503,
            stage="retrieval",
        ) from exc

    shortlist_results: list[dict[str, Any]] = []
    candidate_pool_size = len(search_results["results"])
    if include_shortlist:
        shortlist_response = build_candidate_job_description_shortlist(
            job_description=normalized_role_brief,
            retrieval_limit=bounded_candidate_pool_limit,
            shortlist_limit=bounded_shortlist_limit,
        )
        shortlist_results = shortlist_response["shortlisted_candidates"]
        candidate_pool_size = int(shortlist_response["retrieved_candidate_count"])

    return {
        "role_brief": normalized_role_brief,
        "retrieval_query": normalized_role_brief,
        "detected_target_company": None,
        "candidate_pool_size": candidate_pool_size,
        "search_limit": bounded_search_limit,
        "candidate_pool_limit": bounded_candidate_pool_limit,
        "shortlist_limit": bounded_shortlist_limit,
        "retrieval_metadata": search_results.get("retrieval_metadata", {}),
        "search_results": search_results["results"],
        "shortlist_results": shortlist_results,
    }


def get_candidate_profile(
    *,
    candidate_id: str,
    linked_context_limit: int = 5,
) -> dict[str, Any]:
    """
    Return one candidate profile plus bounded company-linked context.
    """

    profile = build_candidate_profile(candidate_id)
    if profile is None:
        raise McpReadAdapterError(
            "Candidate profile was not found.",
            tool="get_candidate_profile",
            code="not_found",
            status_code=404,
            stage="retrieval",
            details=[{"candidate_id": candidate_id}],
        )

    candidate = profile["candidate"]
    normalized_context_limit = max(1, min(int(linked_context_limit), 20))
    current_company_name = (candidate.get("current_company_name") or "").strip()

    contacts: list[dict[str, Any]] = []
    interactions: list[dict[str, Any]] = []
    jobs: list[dict[str, Any]] = []
    opportunities: list[dict[str, Any]] = []
    if current_company_name != "":
        contacts = discover_contacts_by_company(
            company_name=current_company_name,
            limit=normalized_context_limit,
        )["results"]
        interactions = discover_interactions_by_company(
            company_name=current_company_name,
            limit=normalized_context_limit,
        )["results"]
        jobs = discover_jobs_by_company(
            company_name=current_company_name,
            limit=normalized_context_limit,
        )["results"]
        opportunities = discover_opportunities_by_company(
            company_name=current_company_name,
            limit=normalized_context_limit,
        )["results"]

    return {
        "candidate_id": str(candidate["candidate_id"]),
        "person_id": str(candidate["person_id"]),
        "full_name": candidate.get("full_name"),
        "current_title": candidate.get("current_title"),
        "current_company_name": candidate.get("current_company_name"),
        "candidate_status": candidate.get("candidate_status"),
        "resume_updated_at": candidate.get("resume_updated_at"),
        "skills": list(profile["skills"]),
        "contacts": contacts,
        "interactions": interactions,
        "jobs": jobs,
        "opportunities": opportunities,
    }


def get_candidate_current_resume(
    *,
    candidate_id: str,
) -> dict[str, Any]:
    """
    Return a safe current-resume reference for one candidate.
    """

    current_resume = get_candidate_current_resume_document(candidate_id)
    if current_resume is None:
        raise McpReadAdapterError(
            "Current resume document was not found for this candidate.",
            tool="get_candidate_current_resume",
            code="not_found",
            status_code=404,
            stage="retrieval",
            details=[{"candidate_id": candidate_id}],
        )

    document_source_uri = current_resume.get("document_source_uri")
    normalized_source_uri = (
        document_source_uri.strip()
        if isinstance(document_source_uri, str)
        else None
    )

    return {
        "candidate_id": str(current_resume["candidate_id"]),
        "document_id": str(current_resume["document_id"]),
        "file_name": current_resume.get("document_title")
        or f"{current_resume['document_id']}",
        "content_type": current_resume.get("document_mime_type")
        or "application/octet-stream",
        "download_url": f"/api/v1/candidates/{candidate_id}/current-resume",
        "source_system": current_resume.get("provenance_source_system"),
        "source_uri": normalized_source_uri,
    }


def search_company_context(
    *,
    company_name: str,
    candidate_limit: int = 10,
    contact_limit: int = 10,
    interaction_limit: int = 10,
    job_limit: int = 10,
    opportunity_limit: int = 10,
) -> dict[str, Any]:
    """
    Return the bounded linked company context for one target company.
    """

    normalized_company_name = company_name.strip()
    if normalized_company_name == "":
        raise McpReadAdapterError(
            "Company name must not be blank.",
            tool="search_company_context",
            code="validation_error",
            status_code=400,
            stage="validation",
            details=[{"field": "company_name"}],
        )

    candidates = discover_candidates_by_company(
        company_name=normalized_company_name,
        limit=max(1, min(int(candidate_limit), 50)),
    )["results"]
    contacts = discover_contacts_by_company(
        company_name=normalized_company_name,
        limit=max(1, min(int(contact_limit), 50)),
    )["results"]
    interactions = discover_interactions_by_company(
        company_name=normalized_company_name,
        limit=max(1, min(int(interaction_limit), 50)),
    )["results"]
    jobs = discover_jobs_by_company(
        company_name=normalized_company_name,
        limit=max(1, min(int(job_limit), 50)),
    )["results"]
    opportunities = discover_opportunities_by_company(
        company_name=normalized_company_name,
        limit=max(1, min(int(opportunity_limit), 50)),
    )["results"]

    return {
        "company_name": normalized_company_name,
        "candidates": candidates,
        "contacts": contacts,
        "interactions": interactions,
        "jobs": jobs,
        "opportunities": opportunities,
    }


def list_company_directory(
    *,
    prefix: str | None = None,
    limit: int = 50,
) -> dict[str, Any]:
    """
    Return a bounded searchable company directory.
    """

    try:
        company_records = [
            _normalize_company_directory_record(record)
            for record in list_canonical_company_records()
        ]
    except Exception as exc:
        raise McpReadAdapterError(
            "Company directory retrieval could not complete.",
            tool="list_company_directory",
            code="database_read_error",
            status_code=503,
            stage="database",
        ) from exc
    normalized_limit = max(1, min(int(limit), 500))

    if isinstance(prefix, str) and prefix.strip() != "":
        normalized_prefix = prefix.strip().lower()
        company_records = [
            company
            for company in company_records
            if company["name"].lower().startswith(normalized_prefix)
        ]

    bounded_records = company_records[:normalized_limit]
    return {
        "count": len(bounded_records),
        "companies": [record["name"] for record in bounded_records],
        "company_records": bounded_records,
    }


def _normalize_company_directory_record(record: dict[str, Any]) -> dict[str, Any]:
    """Attach conservative review flags without rewriting canonical data."""

    name = str(record.get("name") or "").strip()
    source_systems = sorted(
        {
            str(value).strip()
            for value in record.get("source_systems") or []
            if str(value).strip()
        }
    )
    source_record_types = sorted(
        {
            str(value).strip()
            for value in record.get("source_record_types") or []
            if str(value).strip()
        }
    )

    quality = assess_company_name_quality(
        name,
        domain=record.get("domain"),
        website_url=record.get("website_url"),
        linkedin_url=record.get("linkedin_url"),
    )

    return {
        "company_id": str(record["company_id"]),
        "name": name,
        "source_systems": source_systems,
        "source_record_types": source_record_types,
        "updated_at": record.get("updated_at"),
        "quality_flags": quality["quality_flags"],
        "needs_review": quality["needs_review"],
    }


def discover_company_leads_for_candidate(
    *,
    candidate_id: str,
    company_name: str,
    limit: int = 10,
) -> dict[str, Any]:
    """
    Return candidate-first outreach context for one target company.
    """

    result = discover_company_leads_for_candidate_service(
        candidate_id=candidate_id,
        company_name=company_name,
        limit=max(1, min(int(limit), 50)),
    )
    if result is None:
        raise McpReadAdapterError(
            "Candidate was not found for company lead discovery.",
            tool="discover_company_leads_for_candidate",
            code="not_found",
            status_code=404,
            stage="retrieval",
            details=[{"candidate_id": candidate_id}],
        )
    return result


__all__ = [
    "McpReadAdapterError",
    "discover_company_leads_for_candidate",
    "get_candidate_current_resume",
    "get_candidate_profile",
    "list_company_directory",
    "search_candidates_for_role",
    "search_company_context",
]
