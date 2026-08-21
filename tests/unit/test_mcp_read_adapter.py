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


def test_search_candidates_for_role_classifies_retrieval_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_search(**kwargs):
        raise TimeoutError("private role brief must not escape")

    monkeypatch.setattr(mcp_read_adapter, "search_candidate_resumes", fail_search)

    with pytest.raises(McpReadAdapterError) as exc_info:
        search_candidates_for_role(role_brief="Senior data engineer")

    assert exc_info.value.code == "retrieval_error"
    assert exc_info.value.stage == "retrieval"
    assert exc_info.value.status_code == 503
    assert "private role brief" not in exc_info.value.message


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
        "list_canonical_company_records",
        lambda: [
            {
                "company_id": "company-1",
                "name": "Acme Markets",
                "source_systems": ["recruitly"],
                "source_record_types": ["recruitly_company"],
                "updated_at": "2026-08-20T12:00:00+00:00",
            },
            {
                "company_id": "company-2",
                "name": "Goldman Sachs",
                "source_systems": [],
                "source_record_types": [],
                "updated_at": "2026-08-20T12:00:00+00:00",
            },
            {
                "company_id": "company-3",
                "name": "Micro Focus",
                "source_systems": ["dropbox"],
                "source_record_types": ["dropbox_resume_extraction"],
                "updated_at": "2026-08-20T12:00:00+00:00",
            },
            {
                "company_id": "company-4",
                "name": "Micromarket Ltd",
                "source_systems": [],
                "source_record_types": [],
                "updated_at": "2026-08-20T12:00:00+00:00",
            },
        ],
    )

    result = list_company_directory(prefix="micro", limit=10)

    assert result["count"] == 2
    assert result["companies"] == ["Micro Focus", "Micromarket Ltd"]
    assert result["company_records"][0] == {
        "company_id": "company-3",
        "name": "Micro Focus",
        "source_systems": ["dropbox"],
        "source_record_types": ["dropbox_resume_extraction"],
        "updated_at": "2026-08-20T12:00:00+00:00",
        "quality_flags": [],
        "needs_review": False,
    }


def test_list_company_directory_flags_suspicious_source_labels(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        mcp_read_adapter,
        "list_canonical_company_records",
        lambda: [
            {
                "company_id": "company-1",
                "name": "A financial services company",
                "domain": None,
                "website_url": None,
                "linkedin_url": "https://www.linkedin.com/company/2150990/",
                "source_systems": ["linkedin_helper"],
                "source_record_types": ["linkedin_helper_person_export"],
                "updated_at": "2026-08-20T12:00:00+00:00",
            },
            {
                "company_id": "company-2",
                "name": "A ID:Tech",
                "domain": None,
                "website_url": None,
                "linkedin_url": None,
                "source_systems": ["dropbox"],
                "source_record_types": ["dropbox_resume_extraction"],
                "updated_at": "2026-08-20T12:00:00+00:00",
            },
        ],
    )

    result = list_company_directory(prefix="A ", limit=10)

    assert result["companies"] == [
        "A financial services company",
        "A ID:Tech",
    ]
    assert result["company_records"][0]["quality_flags"] == [
        "possible_generic_description"
    ]
    assert result["company_records"][1]["quality_flags"] == [
        "possible_extraction_fragment"
    ]
    assert all(record["needs_review"] for record in result["company_records"])


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
