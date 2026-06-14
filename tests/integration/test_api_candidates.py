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

from fastapi import status
from fastapi.testclient import TestClient

from backend.main import app


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
                "fit_score": 92,
                "fit_summary": "Excellent match for the role.",
                "strengths": ["Python", "Cloud data pipelines"],
                "gaps": ["Leadership scope not explicit"],
                "match_excerpt": "<mark>python</mark> pipelines cloud",
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
