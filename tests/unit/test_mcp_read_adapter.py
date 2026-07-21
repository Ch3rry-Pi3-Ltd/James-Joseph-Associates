from __future__ import annotations

import pytest

from backend.services import mcp_read_adapter
from backend.services.mcp_read_adapter import (
    McpReadAdapterError,
    get_candidate_current_resume,
    get_candidate_profile,
    list_company_directory,
    search_candidates_for_role,
    search_company_context,
)


def test_search_candidates_for_role_combines_search_and_shortlist(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        mcp_read_adapter,
        "search_candidate_resumes",
        lambda **kwargs: {
            "query": kwargs["query"],
            "limit": kwargs["limit"],
            "results": [{"candidate_id": "cand-1"}],
        },
    )
    monkeypatch.setattr(
        mcp_read_adapter,
        "build_candidate_job_description_shortlist",
        lambda **kwargs: {
            "retrieved_candidate_count": 12,
            "shortlisted_candidates": [{"candidate_id": "cand-1", "fit_score": 91}],
        },
    )

    result = search_candidates_for_role(
        role_brief="Rust quantitative developer",
        search_limit=10,
        candidate_pool_limit=25,
        shortlist_limit=5,
        include_shortlist=True,
    )

    assert result["retrieval_query"] == "Rust quantitative developer"
    assert result["candidate_pool_size"] == 12
    assert result["search_results"] == [{"candidate_id": "cand-1"}]
    assert result["shortlist_results"] == [{"candidate_id": "cand-1", "fit_score": 91}]


def test_get_candidate_profile_returns_bounded_company_context(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        mcp_read_adapter,
        "build_candidate_profile",
        lambda candidate_id: {
            "candidate": {
                "candidate_id": candidate_id,
                "person_id": "person-1",
                "full_name": "Alice Example",
                "current_title": "Quant Developer",
                "current_company_name": "Acme Markets",
                "candidate_status": "active",
                "resume_updated_at": "2026-07-21T10:00:00+00:00",
            },
            "skills": [{"canonical_name": "Rust"}],
        },
    )
    monkeypatch.setattr(
        mcp_read_adapter,
        "discover_contacts_by_company",
        lambda **kwargs: {"results": [{"contact_id": "contact-1"}]},
    )
    monkeypatch.setattr(
        mcp_read_adapter,
        "discover_interactions_by_company",
        lambda **kwargs: {"results": [{"interaction_id": "interaction-1"}]},
    )
    monkeypatch.setattr(
        mcp_read_adapter,
        "discover_jobs_by_company",
        lambda **kwargs: {"results": [{"job_id": "job-1"}]},
    )
    monkeypatch.setattr(
        mcp_read_adapter,
        "discover_opportunities_by_company",
        lambda **kwargs: {"results": [{"opportunity_id": "opp-1"}]},
    )

    result = get_candidate_profile(candidate_id="cand-1")

    assert result["candidate_id"] == "cand-1"
    assert result["skills"] == [{"canonical_name": "Rust"}]
    assert result["contacts"] == [{"contact_id": "contact-1"}]
    assert result["interactions"] == [{"interaction_id": "interaction-1"}]
    assert result["jobs"] == [{"job_id": "job-1"}]
    assert result["opportunities"] == [{"opportunity_id": "opp-1"}]


def test_get_candidate_profile_raises_when_missing() -> None:
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(
        mcp_read_adapter,
        "build_candidate_profile",
        lambda candidate_id: None,
    )

    with pytest.raises(McpReadAdapterError) as exc_info:
        get_candidate_profile(candidate_id="missing-candidate")

    assert exc_info.value.tool == "get_candidate_profile"
    monkeypatch.undo()


def test_get_candidate_current_resume_returns_safe_reference(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        mcp_read_adapter,
        "get_candidate_current_resume_document",
        lambda candidate_id: {
            "candidate_id": candidate_id,
            "document_id": "doc-1",
            "document_title": "Alice-CV.pdf",
            "document_mime_type": "application/pdf",
            "document_source_uri": "dropbox:///cv/Alice-CV.pdf",
            "provenance_source_system": "dropbox",
        },
    )

    result = get_candidate_current_resume(candidate_id="cand-1")

    assert result["download_url"] == "/api/v1/candidates/cand-1/current-resume"
    assert result["source_system"] == "dropbox"
    assert result["source_uri"] == "dropbox:///cv/Alice-CV.pdf"


def test_list_company_directory_filters_case_insensitively(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        mcp_read_adapter,
        "list_company_directory_service",
        lambda: {
            "count": 3,
            "companies": ["Acme Markets", "Goldman Sachs", "Micro Focus"],
        },
    )

    result = list_company_directory(prefix="micro", limit=10)

    assert result == {
        "count": 1,
        "companies": ["Micro Focus"],
    }


def test_search_company_context_assembles_all_linked_views(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        mcp_read_adapter,
        "discover_candidates_by_company",
        lambda **kwargs: {"results": [{"candidate_id": "cand-1"}]},
    )
    monkeypatch.setattr(
        mcp_read_adapter,
        "discover_contacts_by_company",
        lambda **kwargs: {"results": [{"contact_id": "contact-1"}]},
    )
    monkeypatch.setattr(
        mcp_read_adapter,
        "discover_interactions_by_company",
        lambda **kwargs: {"results": [{"interaction_id": "interaction-1"}]},
    )
    monkeypatch.setattr(
        mcp_read_adapter,
        "discover_jobs_by_company",
        lambda **kwargs: {"results": [{"job_id": "job-1"}]},
    )
    monkeypatch.setattr(
        mcp_read_adapter,
        "discover_opportunities_by_company",
        lambda **kwargs: {"results": [{"opportunity_id": "opp-1"}]},
    )

    result = search_company_context(company_name="Acme Markets")

    assert result["company_name"] == "Acme Markets"
    assert result["candidates"] == [{"candidate_id": "cand-1"}]
    assert result["contacts"] == [{"contact_id": "contact-1"}]
    assert result["interactions"] == [{"interaction_id": "interaction-1"}]
    assert result["jobs"] == [{"job_id": "job-1"}]
    assert result["opportunities"] == [{"opportunity_id": "opp-1"}]
