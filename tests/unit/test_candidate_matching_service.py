from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest

from backend.services import candidate_matching
from backend.services.candidate_matching import (
    CandidateMatchingError,
    CandidateShortlistAssessment,
    CandidateShortlistSelection,
    build_candidate_job_description_shortlist,
)


def test_build_candidate_job_description_shortlist_returns_empty_when_no_candidates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    Verify that no LLM call is made when retrieval returns no candidates.
    """

    captured: dict[str, object] = {}

    def fake_search_candidates_hybrid(**kwargs: object) -> list[dict[str, object]]:
        captured.update(kwargs)
        return []

    monkeypatch.setattr(
        candidate_matching,
        "search_candidates_hybrid",
        fake_search_candidates_hybrid,
    )

    def fail_if_called(**kwargs: object) -> None:
        raise AssertionError("LLM ranking should not run when retrieval is empty")

    monkeypatch.setattr(
        candidate_matching,
        "_rank_retrieved_candidates_for_job_description",
        fail_if_called,
    )

    result = build_candidate_job_description_shortlist(
        job_description="python data engineer",
        retrieval_limit=25,
        shortlist_limit=3,
    )

    assert result == {
        "job_description": "python data engineer",
        "retrieval_limit": 25,
        "shortlist_limit": 3,
        "retrieved_candidate_count": 0,
        "shortlisted_candidates": [],
    }
    assert captured == {
        "query": "python data engineer",
        "limit": 25,
        "include_text": True,
        "include_semantic": True,
    }


def test_build_candidate_job_description_shortlist_merges_retrieval_and_ranking(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    Verify that the service enriches shortlisted candidate IDs with resume data.
    """

    retrieved_candidates = [
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
            "match_score": 0.812345,
            "retrieval_sources": ["text", "semantic"],
            "text_rank": 2,
            "semantic_rank": 1,
            "text_score": 0.723,
            "semantic_score": 0.954,
            "semantic_block_type": "skills",
            "semantic_block_label": "Core skills",
            "match_excerpt": "python pipelines cloud",
        },
        {
            "candidate_id": "cand-2",
            "person_id": "person-2",
            "full_name": "Mark Smith",
            "current_title": "Data Platform Lead",
            "candidate_status": "active",
            "current_company_name": "Northwind",
            "resume_updated_at": "2026-03-10T09:00:00+00:00",
            "document_id": "doc-2",
            "document_title": "Mark-Smith-CV.pdf",
            "document_source_uri": "dropbox:///cv/Mark-Smith-CV.pdf",
            "match_score": 0.734,
            "retrieval_sources": ["text"],
            "text_rank": 1,
            "semantic_rank": None,
            "text_score": 0.734,
            "semantic_score": None,
            "semantic_block_type": None,
            "semantic_block_label": None,
            "match_excerpt": "sql airflow analytics",
        },
    ]

    monkeypatch.setattr(
        candidate_matching,
        "search_candidates_hybrid",
        lambda **kwargs: retrieved_candidates,
    )
    monkeypatch.setattr(
        candidate_matching,
        "_rank_retrieved_candidates_for_job_description",
        lambda **kwargs: [
            CandidateShortlistAssessment(
                candidate_id="cand-2",
                fit_score=89,
                fit_summary="Strong fit for platform leadership and SQL depth.",
                strengths=["Platform leadership", "SQL"],
                gaps=["Less explicit Python depth"],
            ),
            CandidateShortlistAssessment(
                candidate_id="cand-1",
                fit_score=84,
                fit_summary="Strong hands-on pipeline experience.",
                strengths=["Python", "Cloud pipelines"],
                gaps=["Leadership less explicit"],
            ),
        ],
    )

    result = build_candidate_job_description_shortlist(
        job_description="python data engineer",
        retrieval_limit=25,
        shortlist_limit=3,
    )

    assert result["retrieved_candidate_count"] == 2
    assert len(result["shortlisted_candidates"]) == 2
    assert result["shortlisted_candidates"][0]["candidate_id"] == "cand-2"
    assert result["shortlisted_candidates"][0]["fit_score"] == 89
    assert result["shortlisted_candidates"][0]["retrieval_score"] == 0.734
    assert result["shortlisted_candidates"][0]["retrieval_sources"] == ["text"]
    assert result["shortlisted_candidates"][1]["candidate_id"] == "cand-1"


def test_rank_retrieved_candidates_for_job_description_raises_matching_error_on_llm_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    Verify that LLM ranking failures are converted into CandidateMatchingError.
    """

    def raise_model_error(**kwargs: object) -> None:
        raise RuntimeError("model unavailable")

    monkeypatch.setattr(
        candidate_matching,
        "build_langchain_chat_model",
        raise_model_error,
    )

    with pytest.raises(CandidateMatchingError) as error:
        candidate_matching._rank_retrieved_candidates_for_job_description(
            job_description="python data engineer",
            retrieved_candidates=[
                {
                    "candidate_id": "cand-1",
                    "full_name": "Sarah Jones",
                    "current_title": "Senior Data Engineer",
                    "candidate_status": "active",
                    "current_company_name": "Acme Hiring Ltd",
                    "resume_updated_at": "2026-04-20T12:00:00+00:00",
                    "document_title": "Sarah-Jones-CV.pdf",
                    "match_score": 0.812345,
                    "match_excerpt": "python pipelines cloud",
                }
            ],
            shortlist_limit=3,
        )

    assert error.value.stage == "llm_ranking"
    assert error.value.details[0]["error_type"] == "RuntimeError"


def test_rank_retrieved_candidates_for_job_description_accepts_dict_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    Verify that dict-shaped structured output is normalized through Pydantic.
    """

    class FakeStructuredModel:
        def __call__(self, _: object) -> dict[str, object]:
            return {
                "shortlisted_candidates": [
                    {
                        "candidate_id": "cand-1",
                        "fit_score": 91,
                        "fit_summary": "Excellent match.",
                        "strengths": ["Python", "ETL"],
                        "gaps": [],
                    }
                ]
            }

    class FakeChatModel:
        def with_structured_output(
            self,
            schema: type[CandidateShortlistSelection],
        ) -> FakeStructuredModel:
            return FakeStructuredModel()

    monkeypatch.setattr(
        candidate_matching,
        "build_langchain_chat_model",
        lambda **kwargs: FakeChatModel(),
    )

    result = candidate_matching._rank_retrieved_candidates_for_job_description(
        job_description="python data engineer",
        retrieved_candidates=[
            {
                "candidate_id": "cand-1",
                "full_name": "Sarah Jones",
                "current_title": "Senior Data Engineer",
                "candidate_status": "active",
                "current_company_name": "Acme Hiring Ltd",
                "resume_updated_at": "2026-04-20T12:00:00+00:00",
                "document_title": "Sarah-Jones-CV.pdf",
                "match_score": 0.812345,
                "match_excerpt": "python pipelines cloud",
            }
        ],
        shortlist_limit=3,
    )

    assert len(result) == 1
    assert result[0].candidate_id == "cand-1"
    assert result[0].fit_score == 91


def test_rank_retrieved_candidates_for_job_description_serializes_uuid_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    Verify that retrieval rows with UUID/datetime fields are prompt-serializable.
    """

    captured: dict[str, object] = {}

    class FakeStructuredModel:
        def __call__(self, prompt_value: object) -> dict[str, object]:
            captured["prompt_value"] = prompt_value
            return {
                "shortlisted_candidates": [
                    {
                        "candidate_id": str(candidate_id),
                        "fit_score": 90,
                        "fit_summary": "Good fit.",
                        "strengths": ["Python"],
                        "gaps": [],
                    }
                ]
            }

    class FakeChatModel:
        def with_structured_output(
            self,
            schema: type[CandidateShortlistSelection],
        ) -> FakeStructuredModel:
            return FakeStructuredModel()

    candidate_id = uuid4()

    monkeypatch.setattr(
        candidate_matching,
        "build_langchain_chat_model",
        lambda **kwargs: FakeChatModel(),
    )

    result = candidate_matching._rank_retrieved_candidates_for_job_description(
        job_description="python data engineer",
        retrieved_candidates=[
            {
                "candidate_id": candidate_id,
                "full_name": "Sarah Jones",
                "current_title": "Senior Data Engineer",
                "candidate_status": "active",
                "current_company_name": "Acme Hiring Ltd",
                "resume_updated_at": datetime(2026, 4, 20, 12, 0, tzinfo=timezone.utc),
                "document_title": "Sarah-Jones-CV.pdf",
                "match_score": 0.812345,
                "match_excerpt": "python pipelines cloud",
            }
        ],
        shortlist_limit=3,
    )

    assert len(result) == 1
    assert result[0].candidate_id == str(candidate_id)
