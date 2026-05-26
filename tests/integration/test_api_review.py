"""
Integration tests for the review overview API route.
"""

from unittest.mock import patch

from fastapi import status
from fastapi.testclient import TestClient

from backend.main import app


def make_client() -> TestClient:
    """
    Create a test client for the real FastAPI application.
    """

    return TestClient(app)


def test_review_overview_route_returns_compact_payload() -> None:
    """
    Verify that the public overview route returns the expected payload.
    """

    service_result = {
        "counts": {
            "people": 4,
            "candidates": 3,
            "jobs": 2,
            "applications": 5,
            "documents": 6,
            "source_records": 7,
        },
        "recent_candidates": [{"candidate_id": "cand-1"}],
        "recent_jobs": [{"job_id": "job-1"}],
        "recent_applications": [{"application_id": "app-1"}],
        "recent_documents": [{"document_id": "doc-1"}],
        "recent_source_records": [{"source_record_uuid": "src-1"}],
        "document_type_counts": [{"document_type": "candidate_attachment"}],
        "source_system_counts": [{"source_system": "recruiterflow"}],
        "candidate_attachment_health": {
            "total": 106,
            "reference_only": 81,
            "byte_backed": 25,
            "extracted_successfully": 22,
            "unsupported": 2,
            "failed": 1,
        },
    }

    with patch(
        "backend.api.v1.review.build_review_overview",
        return_value=service_result,
    ) as mock_build_review_overview:
        client = make_client()
        response = client.get("/api/v1/review/overview?limit=5")

    assert response.status_code == status.HTTP_200_OK
    assert response.json() == service_result
    mock_build_review_overview.assert_called_once_with(limit=5)
