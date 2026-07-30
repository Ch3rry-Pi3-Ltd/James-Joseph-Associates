"""
Integration tests for candidate API routes.

These tests call the real FastAPI app defined in `backend.main`, while patching
the candidate profile service helper so the route can be tested without a real
database.

The important question is:

    "When the application is assembled for real, does the public candidate
    profile route behave correctly?"

The expected route is:

    GET /api/v1/candidates/{candidate_id}/profile
"""

from unittest.mock import patch
import base64

from fastapi import status
from fastapi.testclient import TestClient

from backend.main import app
from backend.services.candidate_resume_files import CandidateResumeFileAccessError
from backend.services.uploaded_resume_matching import UploadedResumeSearchError
from backend.services.uploaded_job_description import UploadedJobDescriptionError


def make_client() -> TestClient:
    """
    Create a test client for the real FastAPI application.

    Notes
    -----
    - `TestClient` lets the test send HTTP requests to the real FastAPI app
      without starting a real server.
    - This means the test still exercises:

        - route registration
        - request handling
        - response serialisation
        - response models

      while staying fast and local.

    In plain language:

    - build a fake API client
    - point it at the real app
    - use it to call the candidate route

    Returns
    -------
    TestClient
        In-memory HTTP client connected to `backend.main.app`.

    Example
    -------
    A test can use the returned client like this:

        client = make_client()
        response = client.get("/api/v1/health")
    """

    return TestClient(app)


def test_candidate_profile_route_returns_combined_profile() -> None:
    """
    Verify that the route returns the combined profile payload when found.

    Notes
    -----
    - This is an integration test for the real assembled FastAPI app.
    - It patches the service helper so the route can be tested without a real
      database.
    - The important thing being checked is:

        route -> service call -> HTTP response

    - A passing result proves that:

        - the candidate route is registered
        - the route calls the expected service helper
        - the route returns the expected JSON payload

    In plain language:

    - pretend the service found a candidate profile
    - call the public API route
    - confirm the route returns that profile correctly
    """

    candidate_id = "33333333-3333-3333-3333-333333333331"

    service_result = {
        "candidate": {
            "candidate_id": candidate_id,
            "full_name": "Sarah Jones",
            "current_title": "Senior Data Engineer",
            "current_company_name": "Acme Hiring Ltd",
            "candidate_status": "active",
        },
        "skills": [
            {
                "candidate_id": candidate_id,
                "skill_id": "99999999-9999-9999-9999-999999999991",
                "skill_name": "Python",
                "canonical_name": "python",
                "skill_type": "technical",
                "confidence": 0.9800,
                "evidence_text": "Python mentioned in CV and job history.",
            }
        ],
    }

    # Patch the helper name as `backend.api.v1.candidates` sees it
    #   - The route module imports `build_candidate_profile` into its own module
    #     namespace.
    #   - So we patch the name in that route module, not the original service
    #     module path.
    with patch(
        "backend.api.v1.candidates.build_candidate_profile",
        return_value=service_result,
    ) as mock_build_candidate_profile:
        # Create a client for the real FastAPI app and call the public route
        #   - Even though the service helper is patched, the request still moves
        #     through the real application routing layer.
        client = make_client()
        response = client.get(f"/api/v1/candidates/{candidate_id}/profile")

    # The route should return HTTP 200 because the patched service returned a
    # candidate profile instead of `None`
    assert response.status_code == status.HTTP_200_OK

    # The route should return exactly the payload produced by the service layer
    #   - This proves the route did not lose or reshape the data unexpectedly.
    assert response.json() == service_result

    # This proves the route called the expected service helper and passed
    # through the same candidate ID that appeared in the URL
    mock_build_candidate_profile.assert_called_once_with(candidate_id)


def test_candidate_profile_route_returns_not_found_error_when_missing() -> None:
    """
    Verify that the route returns the standard error shape when missing.

    Notes
    -----
    - In this test, the patched service helper returns `None`.
    - The route interprets that as:

        "candidate profile not found"

    - The expected API behaviour is then:

        - return HTTP 404
        - return the project's standard `{"error": ...}` shape

    In plain language:

    - pretend the service did not find the candidate
    - call the public API route
    - confirm the route returns a proper not-found error
    """

    candidate_id = "33333333-3333-3333-3333-333333333331"

    with patch(
        "backend.api.v1.candidates.build_candidate_profile",
        return_value=None,
    ) as mock_build_candidate_profile:
        # Call the real public route while the service helper is temporarily
        # patched to behave as "candidate missing"
        client = make_client()
        response = client.get(f"/api/v1/candidates/{candidate_id}/profile")

    # The route should return HTTP 404 because the service reported that no
    # candidate profile exists for this ID
    assert response.status_code == status.HTTP_404_NOT_FOUND

    # The body should use the project's standard API error contract
    #   - This matters because clients should be able to rely on one consistent
    #     error shape instead of parsing special-case route responses.
    assert response.json() == {
        "error": {
            "code": "not_found",
            "message": "Candidate profile was not found.",
            "details": [{"candidate_id": candidate_id}],
        }
    }

    # This proves the route still passed the candidate ID from the URL into the
    # service layer, even in the not-found case
    mock_build_candidate_profile.assert_called_once_with(candidate_id)


def test_candidate_current_resume_route_streams_file_bytes() -> None:
    """
    Verify that the current-resume route streams the fetched file payload.
    """

    candidate_id = "33333333-3333-3333-3333-333333333331"

    with patch(
        "backend.api.v1.candidates.fetch_candidate_current_resume_file",
        return_value={
            "candidate_id": candidate_id,
            "document_id": "11111111-1111-1111-1111-111111111111",
            "document_title": "Sarah-Jones-CV.pdf",
            "document_source_uri": "dropbox:///cv/Sarah-Jones-CV.pdf",
            "document_mime_type": "application/pdf",
            "file_name": "Sarah-Jones-CV.pdf",
            "content_type": "application/pdf",
            "content_bytes": b"%PDF-test%",
        },
    ) as mock_fetch_candidate_current_resume_file:
        client = make_client()
        response = client.get(f"/api/v1/candidates/{candidate_id}/current-resume")

    assert response.status_code == status.HTTP_200_OK
    assert response.content == b"%PDF-test%"
    assert response.headers["content-type"] == "application/pdf"
    assert (
        response.headers["content-disposition"]
        == 'inline; filename="Sarah-Jones-CV.pdf"'
    )
    assert (
        response.headers["x-document-id"]
        == "11111111-1111-1111-1111-111111111111"
    )
    mock_fetch_candidate_current_resume_file.assert_called_once_with(candidate_id)


def test_candidate_current_resume_route_sanitizes_download_filename() -> None:
    """Verify that stored document names cannot inject response headers."""

    candidate_id = "33333333-3333-3333-3333-333333333331"
    with patch(
        "backend.api.v1.candidates.fetch_candidate_current_resume_file",
        return_value={
            "candidate_id": candidate_id,
            "document_id": "11111111-1111-1111-1111-111111111111",
            "document_title": "candidate.pdf",
            "document_source_uri": "dropbox:///cv/candidate.pdf",
            "document_mime_type": "application/pdf",
            "file_name": 'candidate\r\nX-Injected: yes.pdf',
            "content_type": "application/pdf",
            "content_bytes": b"%PDF-test%",
        },
    ):
        client = make_client()
        response = client.get(f"/api/v1/candidates/{candidate_id}/current-resume")

    assert response.status_code == status.HTTP_200_OK
    assert "\r" not in response.headers["content-disposition"]
    assert "\n" not in response.headers["content-disposition"]
    assert "x-injected" not in response.headers
    assert response.headers["x-content-type-options"] == "nosniff"


def test_candidate_current_resume_route_returns_standard_error_shape() -> None:
    """
    Verify that the current-resume route returns standard API errors.
    """

    candidate_id = "33333333-3333-3333-3333-333333333331"

    with patch(
        "backend.api.v1.candidates.fetch_candidate_current_resume_file",
        side_effect=CandidateResumeFileAccessError(
            "Current resume was not found for this candidate.",
            code="not_found",
            status_code=404,
            details=[{"candidate_id": candidate_id}],
        ),
    ) as mock_fetch_candidate_current_resume_file:
        client = make_client()
        response = client.get(f"/api/v1/candidates/{candidate_id}/current-resume")

    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert response.json() == {
        "error": {
            "code": "not_found",
            "message": "Current resume was not found for this candidate.",
            "details": [{"candidate_id": candidate_id}],
        }
    }
    mock_fetch_candidate_current_resume_file.assert_called_once_with(candidate_id)


def test_candidate_current_resume_route_returns_non_legacy_resume_error_code() -> None:
    """
    Verify that newer resume-download error codes serialize through the standard API shape.
    """

    candidate_id = "33333333-3333-3333-3333-333333333331"

    with patch(
        "backend.api.v1.candidates.fetch_candidate_current_resume_file",
        side_effect=CandidateResumeFileAccessError(
            "Current resume does not have a downloadable source reference.",
            code="resume_source_unavailable",
            status_code=501,
            details=[
                {"candidate_id": candidate_id},
                {"document_id": "11111111-1111-1111-1111-111111111111"},
            ],
        ),
    ) as mock_fetch_candidate_current_resume_file:
        client = make_client()
        response = client.get(f"/api/v1/candidates/{candidate_id}/current-resume")

    assert response.status_code == status.HTTP_501_NOT_IMPLEMENTED
    assert response.json() == {
        "error": {
            "code": "resume_source_unavailable",
            "message": "Current resume does not have a downloadable source reference.",
            "details": [
                {"candidate_id": candidate_id},
                {"document_id": "11111111-1111-1111-1111-111111111111"},
            ],
        }
    }
    mock_fetch_candidate_current_resume_file.assert_called_once_with(candidate_id)


def test_candidate_resume_search_route_returns_ranked_results() -> None:
    """
    Verify that the resume-search route returns the service payload unchanged.
    """

    service_result = {
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
                "source_category": "cross_source",
                "match_excerpt": "<mark>python</mark> data engineer",
            }
        ],
    }

    with patch(
        "backend.api.v1.candidates.search_candidate_resumes",
        return_value=service_result,
    ) as mock_search_candidate_resumes:
        client = make_client()
        response = client.get(
            "/api/v1/candidates/search-resumes?query=python%20data%20engineer&limit=5"
        )

    assert response.status_code == status.HTTP_200_OK
    assert response.json() == service_result
    mock_search_candidate_resumes.assert_called_once_with(
        query="python data engineer",
        limit=5,
    )


def test_candidate_company_discovery_route_returns_ranked_results() -> None:
    """
    Verify that the company-discovery route returns the service payload unchanged.
    """

    service_result = {
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

    with patch(
        "backend.api.v1.candidates.discover_candidates_by_company",
        return_value=service_result,
    ) as mock_discover_candidates_by_company:
        client = make_client()
        response = client.get(
            "/api/v1/candidates/discover-by-company?company_name=Acme%20Hiring%20Ltd&limit=5"
        )

    assert response.status_code == status.HTTP_200_OK
    assert response.json() == service_result
    mock_discover_candidates_by_company.assert_called_once_with(
        company_name="Acme Hiring Ltd",
        limit=5,
    )


def test_company_directory_route_returns_alphabetical_company_names() -> None:
    """
    Verify that the company directory route returns canonical company suggestions.
    """

    service_result = {
        "count": 3,
        "companies": [
            "Acme Hiring Ltd",
            "Capgemini UK Plc",
            "Monzo Bank",
        ],
    }

    with patch(
        "backend.api.v1.candidates.list_company_directory",
        return_value=service_result,
    ) as mock_list_company_directory:
        client = make_client()
        response = client.get("/api/v1/candidates/company-directory")

    assert response.status_code == status.HTTP_200_OK
    assert response.json() == service_result
    mock_list_company_directory.assert_called_once_with()


def test_candidate_company_discovery_route_rejects_blank_company_name() -> None:
    """
    Verify that the company-discovery route rejects blank queries cleanly.
    """

    with patch(
        "backend.api.v1.candidates.discover_candidates_by_company",
    ) as mock_discover_candidates_by_company:
        client = make_client()
        response = client.get(
            "/api/v1/candidates/discover-by-company?company_name=%20%20%20"
        )

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert response.json() == {
        "error": {
            "code": "validation_error",
            "message": "Company discovery query must not be blank.",
            "details": [{"company_name": "   "}],
        }
    }
    mock_discover_candidates_by_company.assert_not_called()


def test_company_job_discovery_route_returns_ranked_results() -> None:
    """
    Verify that the company-job discovery route returns the service payload unchanged.
    """

    service_result = {
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

    with patch(
        "backend.api.v1.candidates.discover_jobs_by_company",
        return_value=service_result,
    ) as mock_discover_jobs_by_company:
        client = make_client()
        response = client.get(
            "/api/v1/candidates/discover-jobs-by-company?company_name=Acme%20Hiring%20Ltd&limit=5"
        )

    assert response.status_code == status.HTTP_200_OK
    assert response.json() == service_result
    mock_discover_jobs_by_company.assert_called_once_with(
        company_name="Acme Hiring Ltd",
        limit=5,
    )


def test_company_job_discovery_route_rejects_blank_company_name() -> None:
    """
    Verify that the company-job discovery route rejects blank queries cleanly.
    """

    with patch(
        "backend.api.v1.candidates.discover_jobs_by_company",
    ) as mock_discover_jobs_by_company:
        client = make_client()
        response = client.get(
            "/api/v1/candidates/discover-jobs-by-company?company_name=%20%20%20"
        )

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert response.json() == {
        "error": {
            "code": "validation_error",
            "message": "Company job discovery query must not be blank.",
            "details": [{"company_name": "   "}],
        }
    }
    mock_discover_jobs_by_company.assert_not_called()


def test_company_contact_discovery_route_returns_ranked_results() -> None:
    """
    Verify that the company-contact discovery route returns the service payload unchanged.
    """

    service_result = {
        "company_name": "Acme Hiring Ltd",
        "limit": 5,
        "results": [
            {
                "contact_id": "contact-1",
                "person_id": "person-1",
                "full_name": "Tom Richards",
                "primary_email": "tom.richards@acme.test",
                "primary_phone": "+447700900222",
                "linkedin_url": "https://www.linkedin.com/in/tom-richards/",
                "location": "London",
                "headline": "Head of Talent",
                "company_id": "company-1",
                "company_name": "Acme Hiring Ltd",
                "role_title": "Head of Talent",
                "contact_type": "hiring_manager",
                "seniority": "head",
                "is_hiring_manager": True,
                "role_is_current": True,
                "role_start_date": "2026-01-01",
                "role_end_date": None,
                "company_match_source": "company_exact",
            }
        ],
    }

    with patch(
        "backend.api.v1.candidates.discover_contacts_by_company",
        return_value=service_result,
    ) as mock_discover_contacts_by_company:
        client = make_client()
        response = client.get(
            "/api/v1/candidates/discover-contacts-by-company?company_name=Acme%20Hiring%20Ltd&limit=5"
        )

    assert response.status_code == status.HTTP_200_OK
    assert response.json() == service_result
    mock_discover_contacts_by_company.assert_called_once_with(
        company_name="Acme Hiring Ltd",
        limit=5,
    )


def test_company_contact_discovery_route_rejects_blank_company_name() -> None:
    """
    Verify that the company-contact discovery route rejects blank queries cleanly.
    """

    with patch(
        "backend.api.v1.candidates.discover_contacts_by_company",
    ) as mock_discover_contacts_by_company:
        client = make_client()
        response = client.get(
            "/api/v1/candidates/discover-contacts-by-company?company_name=%20%20%20"
        )

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert response.json() == {
        "error": {
            "code": "validation_error",
            "message": "Company contact discovery query must not be blank.",
            "details": [{"company_name": "   "}],
        }
    }
    mock_discover_contacts_by_company.assert_not_called()


def test_company_interaction_discovery_route_returns_ranked_results() -> None:
    """
    Verify that the company-interaction discovery route returns the service payload unchanged.
    """

    service_result = {
        "company_name": "Acme Hiring Ltd",
        "limit": 5,
        "results": [
            {
                "interaction_id": "interaction-1",
                "interaction_type": "jobadder_candidate_note",
                "occurred_at": "2026-04-20T12:00:00+00:00",
                "subject": "Candidate note",
                "summary": "Spoke about the Acme data platform role.",
                "body": "Spoke about the Acme data platform role.",
                "source_system": "jobadder",
                "person_id": "person-1",
                "candidate_id": "candidate-1",
                "company_id": "company-1",
                "company_name": "Acme Hiring Ltd",
                "full_name": "Sarah Jones",
                "role_title": "Senior Data Engineer",
                "contact_id": None,
                "job_id": None,
                "job_title": None,
                "candidate_last_contacted_at": "2026-04-20T12:00:00+00:00",
                "matched_entity_type": "candidate",
            }
        ],
    }

    with patch(
        "backend.api.v1.candidates.discover_interactions_by_company",
        return_value=service_result,
    ) as mock_discover_interactions_by_company:
        client = make_client()
        response = client.get(
            "/api/v1/candidates/discover-interactions-by-company?company_name=Acme%20Hiring%20Ltd&limit=5"
        )

    assert response.status_code == status.HTTP_200_OK
    assert response.json() == service_result
    mock_discover_interactions_by_company.assert_called_once_with(
        company_name="Acme Hiring Ltd",
        limit=5,
    )


def test_company_opportunity_discovery_route_returns_ranked_results() -> None:
    """
    Verify that the company-opportunity discovery route returns the service payload unchanged.
    """

    service_result = {
        "company_name": "Acme Hiring Ltd",
        "limit": 5,
        "results": [
            {
                "opportunity_id": "opp-1",
                "title": "Acme data platform follow-up",
                "smart_summary": "Warm opportunity with active hiring discussion.",
                "stage": "qualified",
                "last_contact_at": "2026-04-24T12:00:00+00:00",
                "next_task_at": "2026-04-27T09:00:00+00:00",
                "value": 35000.0,
                "company_id": "company-1",
                "company_name": "Acme Hiring Ltd",
                "contact_id": "contact-1",
                "contact_person_id": "person-3",
                "contact_name": "Tom Richards",
                "contact_email": "tom.richards@acme.test",
                "contact_phone": "+447700900222",
                "contact_role_title": "Head of Talent",
                "company_match_source": "company_exact",
            }
        ],
    }

    with patch(
        "backend.api.v1.candidates.discover_opportunities_by_company",
        return_value=service_result,
    ) as mock_discover_opportunities_by_company:
        client = make_client()
        response = client.get(
            "/api/v1/candidates/discover-opportunities-by-company?company_name=Acme%20Hiring%20Ltd&limit=5"
        )

    assert response.status_code == status.HTTP_200_OK
    assert response.json() == service_result
    mock_discover_opportunities_by_company.assert_called_once_with(
        company_name="Acme Hiring Ltd",
        limit=5,
    )


def test_company_opportunity_discovery_route_rejects_blank_company_name() -> None:
    """
    Verify that the company-opportunity discovery route rejects blank queries cleanly.
    """

    with patch(
        "backend.api.v1.candidates.discover_opportunities_by_company",
    ) as mock_discover_opportunities_by_company:
        client = make_client()
        response = client.get(
            "/api/v1/candidates/discover-opportunities-by-company?company_name=%20%20%20"
        )

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert response.json() == {
        "error": {
            "code": "validation_error",
            "message": "Company opportunity discovery query must not be blank.",
            "details": [{"company_name": "   "}],
        }
    }
    mock_discover_opportunities_by_company.assert_not_called()


def test_company_interaction_discovery_route_rejects_blank_company_name() -> None:
    """
    Verify that the company-interaction discovery route rejects blank queries cleanly.
    """

    with patch(
        "backend.api.v1.candidates.discover_interactions_by_company",
    ) as mock_discover_interactions_by_company:
        client = make_client()
        response = client.get(
            "/api/v1/candidates/discover-interactions-by-company?company_name=%20%20%20"
        )

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert response.json() == {
        "error": {
            "code": "validation_error",
            "message": "Company interaction discovery query must not be blank.",
            "details": [{"company_name": "   "}],
        }
    }
    mock_discover_interactions_by_company.assert_not_called()


def test_candidate_company_lead_discovery_route_returns_composed_results() -> None:
    """
    Verify that the candidate-first company-lead route returns the service payload unchanged.
    """

    candidate_id = "candidate-1"
    service_result = {
        "candidate": {
            "candidate_id": candidate_id,
            "person_id": "person-1",
            "full_name": "Sarah Jones",
            "current_title": "Senior Data Engineer",
            "current_company_name": "Example Current Employer",
        },
        "skills": [
            {
                "candidate_id": candidate_id,
                "skill_id": "skill-1",
                "skill_name": "Python",
                "canonical_name": "python",
                "skill_type": "technical",
                "confidence": 0.98,
                "evidence_text": "Python delivery",
            }
        ],
        "skill_names": ["python"],
        "company_name": "Acme Hiring Ltd",
        "candidate_already_at_company": False,
        "peer_candidates": [
            {
                "candidate_id": "candidate-2",
                "person_id": "person-2",
                "full_name": "Alex Brown",
                "current_title": "Platform Engineer",
                "candidate_status": "active",
                "current_company_name": "Acme Hiring Ltd",
                "resume_updated_at": "2026-04-20T12:00:00+00:00",
                "document_id": "document-2",
                "document_title": "Alex-Brown-CV.pdf",
                "document_source_uri": "dropbox:///cv/Alex-Brown-CV.pdf",
                "company_match_source": "current_company_exact",
                "company_match_score": 1.0,
                "match_excerpt": "Current company exactly matches Acme Hiring Ltd",
            }
        ],
        "contacts": [
            {
                "contact_id": "contact-1",
                "person_id": "person-3",
                "full_name": "Tom Richards",
                "primary_email": "tom.richards@acme.test",
                "primary_phone": "+447700900222",
                "linkedin_url": "https://www.linkedin.com/in/tom-richards/",
                "location": "London",
                "headline": "Head of Talent",
                "company_id": "company-1",
                "company_name": "Acme Hiring Ltd",
                "role_title": "Head of Talent",
                "contact_type": "hiring_manager",
                "seniority": "head",
                "is_hiring_manager": True,
                "role_is_current": True,
                "role_start_date": "2026-01-01",
                "role_end_date": None,
                "company_match_source": "company_exact",
            }
        ],
        "interactions": [
            {
                "interaction_id": "interaction-1",
                "interaction_type": "email",
                "occurred_at": "2026-04-20T12:00:00+00:00",
                "subject": "Intro call",
                "summary": "Spoke about hiring plans.",
                "body": "Spoke about hiring plans.",
                "source_system": "outlook",
                "person_id": "person-3",
                "candidate_id": None,
                "company_id": "company-1",
                "company_name": "Acme Hiring Ltd",
                "full_name": "Tom Richards",
                "role_title": "Head of Talent",
                "contact_id": "contact-1",
                "job_id": None,
                "job_title": None,
                "candidate_last_contacted_at": None,
                "matched_entity_type": "contact",
            }
        ],
        "jobs": [
            {
                "job_id": "job-1",
                "title": "Senior Data Engineer",
                "status": "Open",
                "source": "jobadder",
                "owner_name": "Tom Owens",
                "location": "London, UK",
                "workplace_type": "hybrid",
                "employment_type": "permanent",
                "updated_from_source_at": "2026-04-22T12:00:00+00:00",
                "company_id": "company-1",
                "company_name": "Acme Hiring Ltd",
                "hiring_manager_contact_id": "contact-1",
                "hiring_manager_person_id": "person-3",
                "hiring_manager_name": "Tom Richards",
                "hiring_manager_email": "tom.richards@acme.test",
                "hiring_manager_phone": "+447700900222",
                "hiring_manager_role_title": "Head of Talent",
                "company_match_source": "company_exact",
            }
        ],
        "opportunities": [
            {
                "opportunity_id": "opp-1",
                "title": "Acme data platform follow-up",
                "smart_summary": "Warm opportunity with active hiring discussion.",
                "stage": "qualified",
                "last_contact_at": "2026-04-24T12:00:00+00:00",
                "next_task_at": "2026-04-27T09:00:00+00:00",
                "value": 35000.0,
                "company_id": "company-1",
                "company_name": "Acme Hiring Ltd",
                "contact_id": "contact-1",
                "contact_person_id": "person-3",
                "contact_name": "Tom Richards",
                "contact_email": "tom.richards@acme.test",
                "contact_phone": "+447700900222",
                "contact_role_title": "Head of Talent",
                "company_match_source": "company_exact",
            }
        ],
    }

    with patch(
        "backend.api.v1.candidates.discover_company_leads_for_candidate",
        return_value=service_result,
    ) as mock_discover_company_leads_for_candidate:
        client = make_client()
        response = client.get(
            f"/api/v1/candidates/{candidate_id}/discover-company-leads?company_name=Acme%20Hiring%20Ltd&limit=5"
        )

    assert response.status_code == status.HTTP_200_OK
    assert response.json() == service_result
    mock_discover_company_leads_for_candidate.assert_called_once_with(
        candidate_id=candidate_id,
        company_name="Acme Hiring Ltd",
        limit=5,
    )


def test_candidate_company_lead_discovery_route_rejects_blank_company_name() -> None:
    """
    Verify that the candidate-first company-lead route rejects blank queries cleanly.
    """

    with patch(
        "backend.api.v1.candidates.discover_company_leads_for_candidate",
    ) as mock_discover_company_leads_for_candidate:
        client = make_client()
        response = client.get(
            "/api/v1/candidates/candidate-1/discover-company-leads?company_name=%20%20%20"
        )

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert response.json() == {
        "error": {
            "code": "validation_error",
            "message": "Candidate company-lead query must not be blank.",
            "details": [{"company_name": "   "}],
        }
    }
    mock_discover_company_leads_for_candidate.assert_not_called()


def test_candidate_company_lead_discovery_route_returns_not_found_when_candidate_missing() -> None:
    """
    Verify that the candidate-first company-lead route returns 404 when the candidate is missing.
    """

    candidate_id = "candidate-1"

    with patch(
        "backend.api.v1.candidates.discover_company_leads_for_candidate",
        return_value=None,
    ) as mock_discover_company_leads_for_candidate:
        client = make_client()
        response = client.get(
            f"/api/v1/candidates/{candidate_id}/discover-company-leads?company_name=Acme%20Hiring%20Ltd"
        )

    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert response.json() == {
        "error": {
            "code": "not_found",
            "message": "Candidate profile was not found.",
            "details": [{"candidate_id": candidate_id}],
        }
    }
    mock_discover_company_leads_for_candidate.assert_called_once_with(
        candidate_id=candidate_id,
        company_name="Acme Hiring Ltd",
        limit=10,
    )


def test_uploaded_resume_search_route_returns_ranked_results() -> None:
    """
    Verify that the uploaded-resume search route returns the service payload unchanged.
    """

    service_result = {
        "file_name": "sample-cv.pdf",
        "content_type": "application/pdf",
        "extractor": "pypdf",
        "page_count": 2,
        "character_count": 4123,
        "cleaned_text_preview": "Sarah Jones Senior data engineer Python SQL AWS",
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
                "retrieval_sources": ["semantic"],
                "text_rank": None,
                "semantic_rank": 1,
                "text_score": None,
                "semantic_score": 0.9123,
                "semantic_block_type": "resume_context",
                "semantic_block_label": "Resume context",
                "source_systems": [],
                "source_category": "unknown",
                "match_excerpt": "Python, SQL, AWS, and ETL delivery.",
            }
        ],
    }

    with patch(
        "backend.api.v1.candidates.search_candidates_by_uploaded_resume",
        return_value=service_result,
    ) as mock_search_candidates_by_uploaded_resume:
        client = make_client()
        response = client.post(
            "/api/v1/candidates/search-uploaded-resume",
            json={
                "file_name": "sample-cv.pdf",
                "content_type": "application/pdf",
                "content_base64": base64.b64encode(b"%PDF-test%").decode("ascii"),
                "limit": 5,
            },
        )

    assert response.status_code == status.HTTP_200_OK
    assert response.json() == service_result
    mock_search_candidates_by_uploaded_resume.assert_called_once_with(
        content_bytes=b"%PDF-test%",
        file_name="sample-cv.pdf",
        content_type="application/pdf",
        limit=5,
    )


def test_uploaded_resume_search_route_returns_standard_error_shape() -> None:
    """
    Verify that uploaded-resume processing failures use the standard API error shape.
    """

    with patch(
        "backend.api.v1.candidates.search_candidates_by_uploaded_resume",
        side_effect=UploadedResumeSearchError(
            "The resume file format is not supported for text extraction.",
            stage="input_validation",
            details=[
                {"file_name": "sample.txt"},
                {"content_type": "text/plain"},
            ],
        ),
    ) as mock_search_candidates_by_uploaded_resume:
        client = make_client()
        response = client.post(
            "/api/v1/candidates/search-uploaded-resume",
            json={
                "file_name": "sample.txt",
                "content_type": "text/plain",
                "content_base64": base64.b64encode(b"plain text").decode("ascii"),
                "limit": 5,
            },
        )

    assert response.status_code == status.HTTP_415_UNSUPPORTED_MEDIA_TYPE
    assert response.json() == {
        "error": {
            "code": "resume_source_not_supported",
            "message": "The resume file format is not supported for text extraction.",
            "details": [
                {"stage": "input_validation"},
                {"file_name": "sample.txt"},
                {"content_type": "text/plain"},
            ],
        }
    }
    mock_search_candidates_by_uploaded_resume.assert_called_once_with(
        content_bytes=b"plain text",
        file_name="sample.txt",
        content_type="text/plain",
        limit=5,
    )


def test_uploaded_resume_search_route_rejects_invalid_base64() -> None:
    """
    Verify that invalid base64 payloads fail cleanly before service execution.
    """

    with patch(
        "backend.api.v1.candidates.search_candidates_by_uploaded_resume",
    ) as mock_search_candidates_by_uploaded_resume:
        client = make_client()
        response = client.post(
            "/api/v1/candidates/search-uploaded-resume",
            json={
                "file_name": "sample.pdf",
                "content_type": "application/pdf",
                "content_base64": "!!!not-base64!!!",
                "limit": 5,
            },
        )

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert response.json() == {
        "error": {
            "code": "validation_error",
            "message": "Uploaded CV payload must contain valid base64 content.",
            "details": [{"field": "content_base64"}],
        }
    }
    mock_search_candidates_by_uploaded_resume.assert_not_called()


def test_uploaded_resume_search_route_rejects_oversized_file() -> None:
    """Verify that decoded uploads are bounded before document processing."""

    with (
        patch("backend.api.v1.candidates.MAX_UPLOAD_BYTES", 4),
        patch(
            "backend.api.v1.candidates.search_candidates_by_uploaded_resume",
        ) as mock_search_candidates_by_uploaded_resume,
    ):
        client = make_client()
        response = client.post(
            "/api/v1/candidates/search-uploaded-resume",
            json={
                "file_name": "sample.pdf",
                "content_type": "application/pdf",
                "content_base64": base64.b64encode(b"12345").decode("ascii"),
                "limit": 5,
            },
        )

    assert response.status_code == status.HTTP_413_CONTENT_TOO_LARGE
    assert response.json()["error"]["code"] == "upload_too_large"
    mock_search_candidates_by_uploaded_resume.assert_not_called()


def test_extract_uploaded_job_description_route_returns_extracted_text() -> None:
    """
    Verify that the uploaded-job-description route returns the service payload unchanged.
    """

    service_result = {
        "file_name": "role-brief.pdf",
        "content_type": "application/pdf",
        "extractor": "pypdf",
        "page_count": 2,
        "character_count": 1875,
        "cleaned_text_preview": "Senior data engineer Python SQL cloud ETL",
        "job_description_text": "Senior data engineer Python SQL cloud ETL",
    }

    with patch(
        "backend.api.v1.candidates.extract_uploaded_job_description",
        return_value=service_result,
    ) as mock_extract_uploaded_job_description:
        client = make_client()
        response = client.post(
            "/api/v1/candidates/extract-uploaded-job-description",
            json={
                "file_name": "role-brief.pdf",
                "content_type": "application/pdf",
                "content_base64": base64.b64encode(b"%PDF-job-brief%").decode(
                    "ascii"
                ),
            },
        )

    assert response.status_code == status.HTTP_200_OK
    assert response.json() == service_result
    mock_extract_uploaded_job_description.assert_called_once_with(
        content_bytes=b"%PDF-job-brief%",
        file_name="role-brief.pdf",
        content_type="application/pdf",
    )


def test_extract_uploaded_job_description_route_returns_standard_error_shape() -> None:
    """
    Verify that uploaded job-description failures use the standard API error shape.
    """

    with patch(
        "backend.api.v1.candidates.extract_uploaded_job_description",
        side_effect=UploadedJobDescriptionError(
            "The resume file format is not supported for text extraction.",
            stage="input_validation",
            details=[
                {"file_name": "role-brief.txt"},
                {"content_type": "text/plain"},
            ],
        ),
    ) as mock_extract_uploaded_job_description:
        client = make_client()
        response = client.post(
            "/api/v1/candidates/extract-uploaded-job-description",
            json={
                "file_name": "role-brief.txt",
                "content_type": "text/plain",
                "content_base64": base64.b64encode(b"plain text").decode("ascii"),
            },
        )

    assert response.status_code == status.HTTP_415_UNSUPPORTED_MEDIA_TYPE
    assert response.json() == {
        "error": {
            "code": "resume_source_not_supported",
            "message": "The resume file format is not supported for text extraction.",
            "details": [
                {"stage": "input_validation"},
                {"file_name": "role-brief.txt"},
                {"content_type": "text/plain"},
            ],
        }
    }
    mock_extract_uploaded_job_description.assert_called_once_with(
        content_bytes=b"plain text",
        file_name="role-brief.txt",
        content_type="text/plain",
    )


def test_extract_uploaded_job_description_route_rejects_invalid_base64() -> None:
    """
    Verify that invalid base64 job-description payloads fail cleanly.
    """

    with patch(
        "backend.api.v1.candidates.extract_uploaded_job_description",
    ) as mock_extract_uploaded_job_description:
        client = make_client()
        response = client.post(
            "/api/v1/candidates/extract-uploaded-job-description",
            json={
                "file_name": "role-brief.pdf",
                "content_type": "application/pdf",
                "content_base64": "!!!not-base64!!!",
            },
        )

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert response.json() == {
        "error": {
            "code": "validation_error",
            "message": "Uploaded job description payload must contain valid base64 content.",
            "details": [{"field": "content_base64"}],
        }
    }
    mock_extract_uploaded_job_description.assert_not_called()


def test_candidate_resume_search_route_rejects_blank_query() -> None:
    """
    Verify that the resume-search route rejects blank queries cleanly.
    """

    with patch(
        "backend.api.v1.candidates.search_candidate_resumes",
    ) as mock_search_candidate_resumes:
        client = make_client()
        response = client.get("/api/v1/candidates/search-resumes?query=%20%20%20")

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert response.json() == {
        "error": {
            "code": "validation_error",
            "message": "Resume search query must not be blank.",
            "details": [{"query": "   "}],
        }
    }
    mock_search_candidate_resumes.assert_not_called()


def test_match_job_description_route_returns_shortlist() -> None:
    """
    Verify that the match route returns the shortlist payload unchanged.
    """

    service_result = {
        "job_description": "python data engineer",
        "retrieval_limit": 25,
        "shortlist_limit": 3,
        "retrieved_candidate_count": 2,
        "shortlisted_candidates": [
            {
                "candidate_id": "cand-1",
                "person_id": "person-1",
                "full_name": "Sarah Jones",
                "current_title": "Senior Data Engineer",
                "candidate_status": "active",
                "current_company_name": "Acme Hiring Ltd",
                "resume_updated_at": "2026-04-20T12:00:00+00:00",
                "document_id": "doc-1",
                "document_title": "Sarah-Jones-CV.pdf",
                "document_source_uri": "dropbox:///cv/Sarah-Jones-CV.pdf",
                "retrieval_score": 0.812345,
                "retrieval_sources": ["text", "semantic"],
                "text_rank": 2,
                "semantic_rank": 1,
                    "text_score": 0.712345,
                    "semantic_score": 0.9321,
                    "semantic_block_type": "skills",
                    "semantic_block_label": "Core skills",
                    "source_systems": ["dropbox", "linkedin_helper"],
                    "source_category": "cross_source",
                    "graph_context_score": 0.42,
                    "ranking_input_score": 0.753493,
                    "fit_score": 92,
                    "fit_summary": "Excellent match for the role.",
                    "strengths": ["Python", "Cloud data pipelines"],
                "gaps": ["Leadership scope not explicit"],
                "match_excerpt": "<mark>python</mark> pipelines cloud",
                "graph_evidence": None,
            }
        ],
    }

    with patch(
        "backend.api.v1.candidates.build_candidate_job_description_shortlist",
        return_value=service_result,
    ) as mock_build_candidate_job_description_shortlist:
        client = make_client()
        response = client.post(
            "/api/v1/candidates/match-job-description",
            json={
                "job_description": "python data engineer",
                "retrieval_limit": 25,
                "shortlist_limit": 3,
            },
        )

    assert response.status_code == status.HTTP_200_OK
    assert response.json() == service_result
    mock_build_candidate_job_description_shortlist.assert_called_once_with(
        job_description="python data engineer",
        retrieval_limit=25,
        shortlist_limit=3,
    )


def test_match_job_description_route_rejects_blank_description() -> None:
    """
    Verify that the match route rejects blank job descriptions cleanly.
    """

    with patch(
        "backend.api.v1.candidates.build_candidate_job_description_shortlist",
    ) as mock_build_candidate_job_description_shortlist:
        client = make_client()
        response = client.post(
            "/api/v1/candidates/match-job-description",
            json={
                "job_description": "   ",
                "retrieval_limit": 25,
                "shortlist_limit": 3,
            },
        )

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert response.json() == {
        "error": {
            "code": "validation_error",
            "message": "Job description must not be blank.",
            "details": [{"field": "job_description"}],
        }
    }
    mock_build_candidate_job_description_shortlist.assert_not_called()


def test_match_job_description_route_handles_unexpected_failure() -> None:
    """
    Verify that unexpected shortlist failures still return the standard API shape.
    """

    with patch(
        "backend.api.v1.candidates.build_candidate_job_description_shortlist",
        side_effect=RuntimeError("boom"),
    ) as mock_build_candidate_job_description_shortlist:
        client = make_client()
        response = client.post(
            "/api/v1/candidates/match-job-description",
            json={
                "job_description": "python data engineer",
                "retrieval_limit": 25,
                "shortlist_limit": 3,
            },
        )

    assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
    assert response.json() == {
        "error": {
            "code": "internal_error",
            "message": "Candidate shortlisting failed unexpectedly.",
            "details": [{"error_type": "RuntimeError"}],
        }
    }
    mock_build_candidate_job_description_shortlist.assert_called_once_with(
        job_description="python data engineer",
        retrieval_limit=25,
        shortlist_limit=3,
    )
