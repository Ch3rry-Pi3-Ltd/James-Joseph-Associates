from __future__ import annotations

from unittest.mock import patch

from fastapi import status
from fastapi.testclient import TestClient

from backend.main import app
from backend.services.recruiter_question_answering import (
    RecruiterQuestionAnsweringError,
)
from backend.settings import get_settings


def make_client() -> TestClient:
    return TestClient(app)


def test_operator_route_requires_bearer_token(monkeypatch) -> None:
    get_settings.cache_clear()
    monkeypatch.setenv("ADMIN_API_TOKEN", "test-admin-token")

    client = make_client()
    response = client.get("/api/v1/operator/company-directory")

    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    assert response.json() == {
        "error": {
            "code": "unauthorized",
            "message": "Valid operator bearer credentials were not provided.",
            "details": [],
        }
    }

    get_settings.cache_clear()


def test_operator_role_search_route_returns_bounded_payload(monkeypatch) -> None:
    get_settings.cache_clear()
    monkeypatch.setenv("ADMIN_API_TOKEN", "test-admin-token")

    with patch(
        "backend.api.v1.operator.mcp_read_adapter.search_candidates_for_role",
        return_value={
            "role_brief": "Rust quant developer",
            "retrieval_query": "Rust quant developer",
            "detected_target_company": None,
            "candidate_pool_size": 12,
            "search_limit": 10,
            "candidate_pool_limit": 25,
            "shortlist_limit": 5,
            "search_results": [{"candidate_id": "cand-1"}],
            "shortlist_results": [{"candidate_id": "cand-1", "fit_score": 95}],
        },
    ) as mock_search:
        client = make_client()
        response = client.post(
            "/api/v1/operator/search-candidates-for-role",
            headers={"Authorization": "Bearer test-admin-token"},
            json={"role_brief": "Rust quant developer"},
        )

    assert response.status_code == status.HTTP_200_OK
    assert response.json()["candidate_pool_size"] == 12
    assert response.json()["shortlist_results"] == [
        {"candidate_id": "cand-1", "fit_score": 95}
    ]
    mock_search.assert_called_once()

    get_settings.cache_clear()


def test_operator_answer_question_route_serializes_service_error(monkeypatch) -> None:
    get_settings.cache_clear()
    monkeypatch.setenv("ADMIN_API_TOKEN", "test-admin-token")

    with patch(
        "backend.api.v1.operator.answer_recruiter_question",
        side_effect=RecruiterQuestionAnsweringError(
            "Recruiter answer generation failed during LLM synthesis.",
            stage="llm_answer",
            code="internal_error",
            status_code=500,
            details=[{"candidate_id": "cand-1"}],
        ),
    ):
        client = make_client()
        response = client.post(
            "/api/v1/operator/answer-question",
            headers={"Authorization": "Bearer test-admin-token"},
            json={"question": "Who is candidate cand-1?"},
        )

    assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
    assert response.json() == {
        "error": {
            "code": "internal_error",
            "message": "Recruiter answer generation failed during LLM synthesis.",
            "details": [
                {"stage": "llm_answer"},
                {"candidate_id": "cand-1"},
            ],
        }
    }
    get_settings.cache_clear()
