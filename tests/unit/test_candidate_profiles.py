"""
Unit tests for candidate profile service helpers.

This module tests the service-level composition helper in
`backend.services.candidate_profiles`.

It gives the rest of the repository a stable way to check:

- the service returns `None` when the candidate does not exist
- the service does not fetch skills when the candidate is missing
- the service returns one combined structure when the candidate exists
- the service passes the same candidate ID through to both lower-level helpers
- the service can be tested without touching a real database

Keeping these tests small makes the service layer easier to trust because:

- composition logic is easier to debug when tested in isolation
- route handlers do not need to be the first place where orchestration bugs are found
- tests can validate the combined output shape without needing a live Supabase database
- the service layer can grow one small helper at a time

In plain language:

- this module answers the question:

    "Does the candidate profile service helper combine data correctly?"

- it does not connect to a real database
- it does not call Supabase over the network
- it does not test FastAPI routes
- it only tests local Python behaviour around the service helper

Mocking approach
----------------
These tests use `unittest.mock` helpers:

- `MagicMock()` creates flexible fake Python objects whose methods and return
  values can be controlled inside the test.
- `patch(...)` temporarily replaces the real dependency used by the code under
  test with one of those fake objects.

In this module, that means:

- we do not call the real DB helper functions
- we replace the helper names imported into `candidate_profiles.py`
- we control what those fake helpers return
- we inspect whether they were called correctly
"""

from datetime import UTC, datetime
from unittest.mock import patch
from uuid import UUID

from backend.services.candidate_profiles import (
    build_candidate_profile,
    discover_candidates_by_company,
    discover_company_context,
    discover_company_leads_for_candidate,
    discover_jobs_by_company,
    discover_opportunities_by_company,
    search_candidate_resumes,
)


def test_build_candidate_profile_returns_none_when_candidate_is_missing() -> None:
    """
    Verify that the service returns `None` when the candidate does not exist.

    Notes
    -----
    - The service first calls `get_candidate_profile(candidate_id)`.
    - If that returns `None`, the service should stop immediately.
    - In that case, it should not try to fetch skills.

    In plain language:

    - pretend the candidate helper found nothing
    - call the service
    - confirm the result is `None`
    - confirm the skills helper was not called
    """

    # We patch the helper names as `candidate_profiles.py` sees them.
    #   - That is why the patch targets are:
    #       `backend.services.candidate_profiles.get_candidate_profile`
    #       `backend.services.candidate_profiles.get_candidate_skills`
    #
    #   - We are not patching the original source modules directly here.
    #     `with ... as ...` is Python's context-manager form.
    #
    #   - In this case, it means:
    #
    #       - temporarily replace `get_candidate_profile` with a fake object
    #       - temporarily replace `get_candidate_skills` with another fake object
    #       - run the indented test code while those replacements are active
    #       - then automatically restore the real functions afterwards
    #
    #   - The `as mock_get_candidate_profile` part gives us a name for the fake
    #     replacement object created by `patch(...)`.
    #     That matters because we want to inspect it later and ask things like:
    #
    #       - was it called?
    #       - how many times was it called?
    #       - what arguments was it called with?
    #
    #   - So, in plain language, this block means:
    #
    #       - "while these two helper functions are temporarily faked,
    #           run `build_candidate_profile(...)` and let me inspect the fake helpers"
    #
    #   - The first patched helper is forced to return `None`, which simulates:
    #
    #       - "the candidate was not found"
    #
    #   - The second patched helper is not given a return value on purpose.
    #     We are not interested in its output here.
    #     We only want to check whether the service tried to call it at all.
    with (
        patch(
            "backend.services.candidate_profiles.get_candidate_profile",
            return_value=None,
        ) as mock_get_candidate_profile,
        patch(
            "backend.services.candidate_profiles.attach_candidate_source_metadata",
        ) as mock_attach_candidate_source_metadata,
        patch(
            "backend.services.candidate_profiles.get_candidate_skills",
        ) as mock_get_candidate_skills,
        patch(
            "backend.services.candidate_profiles.get_candidate_recent_employment",
        ) as mock_get_candidate_recent_employment,
    ):
        # Run the service while the two helper functions are still patched.
        #
        # Because the fake `get_candidate_profile(...)` returns `None`,
        # the service should behave as though the candidate does not exist.
        result = build_candidate_profile(
            "33333333-3333-3333-3333-333333333331",
        )

    assert result is None
    mock_get_candidate_profile.assert_called_once_with(
        "33333333-3333-3333-3333-333333333331",
    )
    mock_attach_candidate_source_metadata.assert_not_called()
    mock_get_candidate_skills.assert_not_called()
    mock_get_candidate_recent_employment.assert_not_called()


def test_build_candidate_profile_returns_combined_structure_when_candidate_exists() -> (
    None
):
    """
    Verify that the service returns the expected combined structure.

    Notes
    -----
    - If the candidate helper returns a candidate dictionary,
      the service should then fetch skills.
    - The final result should combine both pieces into one dictionary with:
      - `candidate`
      - `skills`

    In plain language:

    - pretend the candidate helper returned a candidate
    - pretend the skills helper returned a list of skills
    - call the service
    - confirm the result combines both pieces exactly
    """

    candidate = {
        "candidate_id": "33333333-3333-3333-3333-333333333331",
        "full_name": "Sarah Jones",
        "current_title": "Senior Data Engineer",
        "current_company_name": "Acme Hiring Ltd",
        "candidate_status": "active",
    }

    skills = [
        {
            "candidate_id": "33333333-3333-3333-3333-333333333331",
            "skill_id": "99999999-9999-9999-9999-999999999991",
            "skill_name": "Python",
            "canonical_name": "python",
            "skill_type": "technical",
            "confidence": 0.9800,
            "evidence_text": "Python mentioned in CV and job history.",
        },
        {
            "candidate_id": "33333333-3333-3333-3333-333333333331",
            "skill_id": "99999999-9999-9999-9999-999999999992",
            "skill_name": "SQL",
            "canonical_name": "sql",
            "skill_type": "technical",
            "confidence": 0.9700,
            "evidence_text": "SQL mentioned in CV and project experience.",
        },
    ]
    recent_employment = [
        {
            "employment_role_id": "role-1",
            "company_name": "Acme Hiring Ltd",
            "role_title": "Senior Data Engineer",
            "start_date": "2024-01-01",
            "end_date": None,
            "is_current": True,
        }
    ]
    enriched_candidate = {
        **candidate,
        "has_resume_document": True,
        "source_systems": ["dropbox", "linkedin_helper"],
        "source_details": [
            {
                "source_system": "dropbox",
                "latest_record_received_at": "2026-06-10T09:00:00+00:00",
            },
            {
                "source_system": "linkedin_helper",
                "latest_record_received_at": "2026-07-20T14:30:00+00:00",
            },
        ],
        "source_category": "cross_source",
    }

    with (
        patch(
            "backend.services.candidate_profiles.get_candidate_profile",
            return_value=candidate,
        ) as mock_get_candidate_profile,
        patch(
            "backend.services.candidate_profiles.attach_candidate_source_metadata",
            return_value=[enriched_candidate],
        ) as mock_attach_candidate_source_metadata,
        patch(
            "backend.services.candidate_profiles.get_candidate_skills",
            return_value=skills,
        ) as mock_get_candidate_skills,
        patch(
            "backend.services.candidate_profiles.get_candidate_recent_employment",
            return_value=recent_employment,
        ) as mock_get_candidate_recent_employment,
    ):
        result = build_candidate_profile(
            "33333333-3333-3333-3333-333333333331",
        )

    assert result == {
        "candidate": enriched_candidate,
        "skills": skills,
        "recent_employment": recent_employment,
    }
    mock_get_candidate_profile.assert_called_once_with(
        "33333333-3333-3333-3333-333333333331",
    )
    mock_attach_candidate_source_metadata.assert_called_once_with([candidate])
    mock_get_candidate_skills.assert_called_once_with(
        "33333333-3333-3333-3333-333333333331",
    )
    mock_get_candidate_recent_employment.assert_called_once_with(
        "33333333-3333-3333-3333-333333333331",
    )


def test_build_candidate_profile_can_skip_repeated_source_lookup() -> None:
    candidate_id = "33333333-3333-3333-3333-333333333331"
    candidate = {"candidate_id": candidate_id}

    with (
        patch(
            "backend.services.candidate_profiles.get_candidate_profile",
            return_value=candidate,
        ),
        patch(
            "backend.services.candidate_profiles.attach_candidate_source_metadata",
        ) as mock_attach_candidate_source_metadata,
        patch(
            "backend.services.candidate_profiles.get_candidate_skills",
            return_value=[],
        ),
        patch(
            "backend.services.candidate_profiles.get_candidate_recent_employment",
            return_value=[],
        ),
    ):
        result = build_candidate_profile(
            candidate_id,
            include_source_metadata=False,
        )

    assert result == {
        "candidate": candidate,
        "skills": [],
        "recent_employment": [],
    }
    mock_attach_candidate_source_metadata.assert_not_called()


def test_build_candidate_profile_passes_candidate_id_to_both_helpers() -> None:
    """
    Verify that the same candidate ID is passed through to both helper calls.

    Notes
    -----
    - This test focuses on the call contract between the service layer and the
      lower-level DB helpers.
    - It helps catch mistakes where the service ignores or alters the supplied
      candidate ID.

    In plain language:

    - call the service with a known candidate ID
    - confirm both helper calls used that same ID
    """

    candidate_id = "33333333-3333-3333-3333-333333333331"

    with (
        patch(
            "backend.services.candidate_profiles.get_candidate_profile",
            return_value={"candidate_id": candidate_id},
        ) as mock_get_candidate_profile,
        patch(
            "backend.services.candidate_profiles.attach_candidate_source_metadata",
            return_value=[
                {
                    "candidate_id": candidate_id,
                    "source_systems": [],
                    "source_details": [],
                    "source_category": "unknown",
                }
            ],
        ) as mock_attach_candidate_source_metadata,
        patch(
            "backend.services.candidate_profiles.get_candidate_skills",
            return_value=[],
        ) as mock_get_candidate_skills,
        patch(
            "backend.services.candidate_profiles.get_candidate_recent_employment",
            return_value=[],
        ) as mock_get_candidate_recent_employment,
    ):
        build_candidate_profile(candidate_id)

    mock_get_candidate_profile.assert_called_once_with(candidate_id)
    mock_attach_candidate_source_metadata.assert_called_once_with(
        [{"candidate_id": candidate_id}]
    )
    mock_get_candidate_skills.assert_called_once_with(candidate_id)
    mock_get_candidate_recent_employment.assert_called_once_with(candidate_id)


def test_search_candidate_resumes_normalizes_raw_hybrid_rows() -> None:
    """
    Verify that resume-search results are normalized into the public API shape.
    """

    raw_result = {
        "candidate_id": UUID("33333333-3333-3333-3333-333333333331"),
        "person_id": UUID("22222222-2222-2222-2222-222222222221"),
        "full_name": "Sarah Jones",
        "current_title": "Senior Data Engineer",
        "candidate_status": "active",
        "current_company_name": "Acme Hiring Ltd",
        "resume_updated_at": datetime(2026, 4, 20, 12, 0, tzinfo=UTC),
        "document_id": UUID("11111111-1111-1111-1111-111111111111"),
        "document_title": "Sarah-Jones-CV.pdf",
        "document_source_uri": "dropbox:///cv/Sarah-Jones-CV.pdf",
        "match_score": 0.812345,
        "retrieval_sources": ["text", "semantic"],
        "text_rank": 2,
        "semantic_rank": 1,
        "text_score": 0.712345,
        "semantic_score": 0.9321,
        "match_excerpt": "<mark>python</mark> data engineer",
        "block_id": UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
        "block_type": "skills",
        "block_label": "Core skills",
    }

    with (
        patch(
            "backend.services.candidate_profiles.search_candidates_hybrid",
            return_value=[raw_result],
        ) as mock_search_candidates_hybrid,
        patch(
            "backend.services.candidate_profiles.attach_candidate_source_metadata",
            return_value=[
                {
                    **raw_result,
                    "source_systems": ["dropbox", "linkedin_helper"],
                    "source_details": [
                        {
                            "source_system": "dropbox",
                            "latest_record_received_at": datetime(
                                2026, 6, 10, 9, 0, tzinfo=UTC
                            ),
                        },
                        {
                            "source_system": "linkedin_helper",
                            "latest_record_received_at": datetime(
                                2026, 7, 20, 14, 30, tzinfo=UTC
                            ),
                        },
                    ],
                    "source_category": "cross_source",
                }
            ],
        ),
    ):
        result = search_candidate_resumes(
            query=" python data engineer ",
            limit=5,
        )

    assert result == {
        "query": "python data engineer",
        "limit": 5,
        "results": [
            {
                "candidate_id": "33333333-3333-3333-3333-333333333331",
                "person_id": "22222222-2222-2222-2222-222222222221",
                "full_name": "Sarah Jones",
                "current_title": "Senior Data Engineer",
                "candidate_status": "active",
                "current_company_name": "Acme Hiring Ltd",
                "resume_updated_at": "2026-04-20T12:00:00+00:00",
                "document_id": "11111111-1111-1111-1111-111111111111",
                "document_title": "Sarah-Jones-CV.pdf",
                "document_source_uri": "dropbox:///cv/Sarah-Jones-CV.pdf",
                "match_score": 0.812345,
                "retrieval_sources": ["text", "semantic"],
                "text_rank": 2,
                "semantic_rank": 1,
                "text_score": 0.712345,
                "semantic_score": 0.9321,
                "semantic_block_type": "skills",
                "semantic_block_label": "Core skills",
                "source_systems": ["dropbox", "linkedin_helper"],
                "source_details": [
                    {
                        "source_system": "dropbox",
                        "latest_record_received_at": "2026-06-10T09:00:00+00:00",
                    },
                    {
                        "source_system": "linkedin_helper",
                        "latest_record_received_at": "2026-07-20T14:30:00+00:00",
                    },
                ],
                "source_category": "cross_source",
                "match_excerpt": "<mark>python</mark> data engineer",
            }
        ],
    }
    mock_search_candidates_hybrid.assert_called_once_with(
        query="python data engineer",
        limit=5,
        include_text=True,
        include_semantic=True,
    )


def test_search_candidate_resumes_keeps_profile_only_results() -> None:
    """
    Verify Linked Helper profiles can surface without a linked CV document.
    """

    profile_only_result = {
        "candidate_id": "candidate-1",
        "person_id": "person-1",
        "full_name": "Profile Only",
        "document_id": None,
        "match_score": 0.91,
        "retrieval_sources": ["semantic"],
        "semantic_rank": 1,
        "semantic_score": 0.91,
        "block_type": "profile",
        "block_label": "Candidate profile",
        "match_excerpt": "Rust low latency engineer",
    }

    with (
        patch(
            "backend.services.candidate_profiles.search_candidates_hybrid",
            return_value=[profile_only_result],
        ),
        patch(
            "backend.services.candidate_profiles.attach_candidate_source_metadata",
            return_value=[
                {
                    **profile_only_result,
                    "source_systems": ["linkedin_helper"],
                    "source_details": [
                        {
                            "source_system": "linkedin_helper",
                            "latest_record_received_at": "2026-07-21T14:30:00+00:00",
                        }
                    ],
                    "source_category": "linkedin_helper_only",
                }
            ],
        ),
    ):
        result = search_candidate_resumes(
            query="rust low latency engineer",
            limit=5,
        )

    assert result["results"][0]["document_id"] is None
    assert result["results"][0]["document_title"] is None
    assert result["results"][0]["retrieval_sources"] == ["semantic"]
    assert result["results"][0]["source_details"][0]["source_system"] == (
        "linkedin_helper"
    )
    assert result["results"][0]["source_category"] == "linkedin_helper_only"


def test_discover_candidates_by_company_normalizes_raw_rows() -> None:
    """
    Verify that company-discovery results are normalized into the public API shape.
    """

    raw_result = {
        "candidate_id": UUID("33333333-3333-3333-3333-333333333331"),
        "person_id": UUID("22222222-2222-2222-2222-222222222221"),
        "full_name": "Sarah Jones",
        "current_title": "Senior Data Engineer",
        "candidate_status": "active",
        "current_company_name": "Acme Hiring Ltd",
        "resume_updated_at": datetime(2026, 4, 20, 12, 0, tzinfo=UTC),
        "document_id": UUID("11111111-1111-1111-1111-111111111111"),
        "document_title": "Sarah-Jones-CV.pdf",
        "document_source_uri": "dropbox:///cv/Sarah-Jones-CV.pdf",
        "company_match_source": "current_company_exact",
        "company_match_score": 1.0,
        "match_excerpt": "Current company exactly matches Acme Hiring Ltd",
    }

    with patch(
        "backend.services.candidate_profiles.search_candidates_by_company_name",
        return_value=[raw_result],
    ) as mock_search_candidates_by_company_name:
        result = discover_candidates_by_company(
            company_name=" Acme Hiring Ltd ",
            limit=5,
        )

    assert result == {
        "company_name": "Acme Hiring Ltd",
        "limit": 5,
        "results": [
            {
                "candidate_id": "33333333-3333-3333-3333-333333333331",
                "person_id": "22222222-2222-2222-2222-222222222221",
                "full_name": "Sarah Jones",
                "current_title": "Senior Data Engineer",
                "candidate_status": "active",
                "current_company_name": "Acme Hiring Ltd",
                "resume_updated_at": "2026-04-20T12:00:00+00:00",
                "document_id": "11111111-1111-1111-1111-111111111111",
                "document_title": "Sarah-Jones-CV.pdf",
                "document_source_uri": "dropbox:///cv/Sarah-Jones-CV.pdf",
                "company_match_source": "current_company_exact",
                "company_match_score": 1.0,
                "match_excerpt": "Current company exactly matches Acme Hiring Ltd",
            }
        ],
    }
    mock_search_candidates_by_company_name.assert_called_once_with(
        company_name="Acme Hiring Ltd",
        limit=5,
    )


def test_discover_jobs_by_company_normalizes_raw_rows() -> None:
    """
    Verify that company-job discovery results are normalized into the public API shape.
    """

    raw_result = {
        "job_id": UUID("55555555-5555-5555-5555-555555555551"),
        "title": "Senior Data Engineer",
        "status": "Open",
        "source": "jobadder",
        "owner_name": "Tom Owens",
        "location": "London, UK",
        "workplace_type": "hybrid",
        "employment_type": "permanent",
        "updated_from_source_at": datetime(2026, 4, 22, 12, 0, tzinfo=UTC),
        "company_id": UUID("11111111-1111-1111-1111-111111111111"),
        "company_name": "Acme Hiring Ltd",
        "hiring_manager_contact_id": None,
        "hiring_manager_person_id": None,
        "hiring_manager_name": None,
        "hiring_manager_email": None,
        "hiring_manager_phone": None,
        "hiring_manager_role_title": None,
        "company_match_source": "company_exact",
    }

    with patch(
        "backend.services.candidate_profiles.search_jobs_by_company_name",
        return_value=[raw_result],
    ) as mock_search_jobs_by_company_name:
        result = discover_jobs_by_company(
            company_name=" Acme Hiring Ltd ",
            limit=5,
        )

    assert result == {
        "company_name": "Acme Hiring Ltd",
        "limit": 5,
        "results": [
            {
                "job_id": "55555555-5555-5555-5555-555555555551",
                "title": "Senior Data Engineer",
                "status": "Open",
                "source": "jobadder",
                "owner_name": "Tom Owens",
                "location": "London, UK",
                "workplace_type": "hybrid",
                "employment_type": "permanent",
                "updated_from_source_at": "2026-04-22T12:00:00+00:00",
                "company_id": "11111111-1111-1111-1111-111111111111",
                "company_name": "Acme Hiring Ltd",
                "hiring_manager_contact_id": None,
                "hiring_manager_person_id": None,
                "hiring_manager_name": None,
                "hiring_manager_email": None,
                "hiring_manager_phone": None,
                "hiring_manager_role_title": None,
                "company_match_source": "company_exact",
            }
        ],
    }
    mock_search_jobs_by_company_name.assert_called_once_with(
        company_name="Acme Hiring Ltd",
        limit=5,
    )


def test_discover_opportunities_by_company_normalizes_raw_rows() -> None:
    """
    Verify that company-opportunity discovery results are normalized into the public API shape.
    """

    raw_result = {
        "opportunity_id": UUID("66666666-6666-6666-6666-666666666661"),
        "title": "Acme data platform follow-up",
        "smart_summary": "Warm opportunity with active hiring discussion.",
        "stage": "qualified",
        "last_contact_at": datetime(2026, 4, 24, 12, 0, tzinfo=UTC),
        "next_task_at": datetime(2026, 4, 27, 9, 0, tzinfo=UTC),
        "value": 35000,
        "company_id": UUID("11111111-1111-1111-1111-111111111111"),
        "company_name": "Acme Hiring Ltd",
        "contact_id": UUID("77777777-7777-7777-7777-777777777771"),
        "contact_person_id": UUID("88888888-8888-8888-8888-888888888881"),
        "contact_name": "Tom Richards",
        "contact_email": "tom.richards@acme.test",
        "contact_phone": "+447700900222",
        "contact_role_title": "Head of Talent",
        "company_match_source": "company_exact",
    }

    with patch(
        "backend.services.candidate_profiles.search_opportunities_by_company_name",
        return_value=[raw_result],
    ) as mock_search_opportunities_by_company_name:
        result = discover_opportunities_by_company(
            company_name=" Acme Hiring Ltd ",
            limit=5,
        )

    assert result == {
        "company_name": "Acme Hiring Ltd",
        "limit": 5,
        "results": [
            {
                "opportunity_id": "66666666-6666-6666-6666-666666666661",
                "title": "Acme data platform follow-up",
                "smart_summary": "Warm opportunity with active hiring discussion.",
                "stage": "qualified",
                "last_contact_at": "2026-04-24T12:00:00+00:00",
                "next_task_at": "2026-04-27T09:00:00+00:00",
                "value": 35000.0,
                "company_id": "11111111-1111-1111-1111-111111111111",
                "company_name": "Acme Hiring Ltd",
                "contact_id": "77777777-7777-7777-7777-777777777771",
                "contact_person_id": "88888888-8888-8888-8888-888888888881",
                "contact_name": "Tom Richards",
                "contact_email": "tom.richards@acme.test",
                "contact_phone": "+447700900222",
                "contact_role_title": "Head of Talent",
                "company_match_source": "company_exact",
            }
        ],
    }
    mock_search_opportunities_by_company_name.assert_called_once_with(
        company_name="Acme Hiring Ltd",
        limit=5,
    )


def test_discover_company_context_composes_requested_sections_once() -> None:
    section_payloads = {
        "candidates": [{"candidate_id": "candidate-1"}],
        "contacts": [{"contact_id": "contact-1"}],
        "interactions": [{"interaction_id": "interaction-1"}],
        "jobs": [{"job_id": "job-1"}],
    }

    with (
        patch(
            "backend.services.candidate_profiles.discover_candidates_by_company",
            return_value={"results": section_payloads["candidates"]},
        ) as mock_candidates,
        patch(
            "backend.services.candidate_profiles.discover_contacts_by_company",
            return_value={"results": section_payloads["contacts"]},
        ) as mock_contacts,
        patch(
            "backend.services.candidate_profiles.discover_interactions_by_company",
            return_value={"results": section_payloads["interactions"]},
        ) as mock_interactions,
        patch(
            "backend.services.candidate_profiles.discover_jobs_by_company",
            return_value={"results": section_payloads["jobs"]},
        ) as mock_jobs,
        patch(
            "backend.services.candidate_profiles.discover_opportunities_by_company",
        ) as mock_opportunities,
    ):
        result = discover_company_context(
            company_name=" Shared Employer ",
            limit=5,
            include_opportunities=False,
        )

    assert result == {
        "company_name": "Shared Employer",
        "limit": 5,
        **section_payloads,
        "opportunities": [],
    }
    for mock_section in (
        mock_candidates,
        mock_contacts,
        mock_interactions,
        mock_jobs,
    ):
        mock_section.assert_called_once_with(company_name="Shared Employer", limit=5)
    mock_opportunities.assert_not_called()


def test_discover_company_context_skips_candidate_query_for_graph_evidence() -> None:
    with patch(
        "backend.services.candidate_profiles.discover_candidates_by_company",
    ) as mock_candidates, patch(
        "backend.services.candidate_profiles.discover_contacts_by_company",
        return_value={"results": []},
    ), patch(
        "backend.services.candidate_profiles.discover_interactions_by_company",
        return_value={"results": []},
    ), patch(
        "backend.services.candidate_profiles.discover_jobs_by_company",
        return_value={"results": []},
    ), patch(
        "backend.services.candidate_profiles.discover_opportunities_by_company",
        return_value={"results": []},
    ):
        result = discover_company_context(
            company_name="Shared Employer",
            limit=3,
            include_candidates=False,
        )

    assert result["candidates"] == []
    mock_candidates.assert_not_called()


def test_discover_company_leads_for_candidate_returns_none_when_candidate_is_missing() -> (
    None
):
    """
    Verify that candidate-first lead discovery stops when the candidate is missing.
    """

    with patch(
        "backend.services.candidate_profiles.build_candidate_profile",
        return_value=None,
    ) as mock_build_candidate_profile:
        result = discover_company_leads_for_candidate(
            candidate_id="candidate-1",
            company_name="Acme Hiring Ltd",
            limit=5,
        )

    assert result is None
    mock_build_candidate_profile.assert_called_once_with("candidate-1")


def test_discover_company_leads_for_candidate_composes_company_views() -> None:
    """
    Verify that candidate-first lead discovery combines candidate, skills, and company evidence.
    """

    with (
        patch(
            "backend.services.candidate_profiles.build_candidate_profile",
            return_value={
                "candidate": {
                    "candidate_id": "candidate-1",
                    "person_id": "person-1",
                    "full_name": "Sarah Jones",
                    "current_company_name": "Other Employer",
                },
                "skills": [
                    {
                        "candidate_id": "candidate-1",
                        "skill_id": "skill-1",
                        "skill_name": "Python",
                        "canonical_name": "python",
                    },
                    {
                        "candidate_id": "candidate-1",
                        "skill_id": "skill-2",
                        "skill_name": "Python",
                        "canonical_name": "python",
                    },
                    {
                        "candidate_id": "candidate-1",
                        "skill_id": "skill-3",
                        "skill_name": "SQL",
                        "canonical_name": "sql",
                    },
                ],
            },
        ) as mock_build_candidate_profile,
        patch(
            "backend.services.candidate_profiles.discover_contacts_by_company",
            return_value={
                "company_name": "Acme Hiring Ltd",
                "limit": 5,
                "results": [{"contact_id": "contact-1"}],
            },
        ) as mock_discover_contacts_by_company,
        patch(
            "backend.services.candidate_profiles.discover_interactions_by_company",
            return_value={
                "company_name": "Acme Hiring Ltd",
                "limit": 5,
                "results": [{"interaction_id": "interaction-1"}],
            },
        ) as mock_discover_interactions_by_company,
        patch(
            "backend.services.candidate_profiles.discover_jobs_by_company",
            return_value={
                "company_name": "Acme Hiring Ltd",
                "limit": 5,
                "results": [{"job_id": "job-1"}],
            },
        ) as mock_discover_jobs_by_company,
        patch(
            "backend.services.candidate_profiles.discover_opportunities_by_company",
            return_value={
                "company_name": "Acme Hiring Ltd",
                "limit": 5,
                "results": [{"opportunity_id": "opp-1"}],
            },
        ) as mock_discover_opportunities_by_company,
        patch(
            "backend.services.candidate_profiles.discover_candidates_by_company",
            return_value={
                "company_name": "Acme Hiring Ltd",
                "limit": 6,
                "results": [
                    {"candidate_id": "candidate-1"},
                    {"candidate_id": "candidate-2"},
                ],
            },
        ) as mock_discover_candidates_by_company,
    ):
        result = discover_company_leads_for_candidate(
            candidate_id="candidate-1",
            company_name=" Acme Hiring Ltd ",
            limit=5,
        )

    assert result == {
        "candidate": {
            "candidate_id": "candidate-1",
            "person_id": "person-1",
            "full_name": "Sarah Jones",
            "current_company_name": "Other Employer",
        },
        "skills": [
            {
                "candidate_id": "candidate-1",
                "skill_id": "skill-1",
                "skill_name": "Python",
                "canonical_name": "python",
            },
            {
                "candidate_id": "candidate-1",
                "skill_id": "skill-2",
                "skill_name": "Python",
                "canonical_name": "python",
            },
            {
                "candidate_id": "candidate-1",
                "skill_id": "skill-3",
                "skill_name": "SQL",
                "canonical_name": "sql",
            },
        ],
        "skill_names": ["python", "sql"],
        "company_name": "Acme Hiring Ltd",
        "candidate_already_at_company": False,
        "peer_candidates": [{"candidate_id": "candidate-2"}],
        "contacts": [{"contact_id": "contact-1"}],
        "interactions": [{"interaction_id": "interaction-1"}],
        "jobs": [{"job_id": "job-1"}],
        "opportunities": [{"opportunity_id": "opp-1"}],
    }
    mock_build_candidate_profile.assert_called_once_with("candidate-1")
    mock_discover_contacts_by_company.assert_called_once_with(
        company_name="Acme Hiring Ltd",
        limit=5,
    )
    mock_discover_interactions_by_company.assert_called_once_with(
        company_name="Acme Hiring Ltd",
        limit=5,
    )
    mock_discover_jobs_by_company.assert_called_once_with(
        company_name="Acme Hiring Ltd",
        limit=5,
    )
    mock_discover_opportunities_by_company.assert_called_once_with(
        company_name="Acme Hiring Ltd",
        limit=5,
    )
    mock_discover_candidates_by_company.assert_called_once_with(
        company_name="Acme Hiring Ltd",
        limit=5,
    )
