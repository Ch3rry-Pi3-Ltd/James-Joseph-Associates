"""
Candidate shortlist helpers for role-brief matching.

This module turns the existing canonical resume search into a recruiter-facing
shortlist workflow:

- retrieve candidate resumes from Supabase
- send the retrieved pool plus the job description to the LLM
- return the top shortlisted candidates with reasons
"""

from __future__ import annotations

import json
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, ConfigDict, Field

from backend.llm.models import DEFAULT_REASONING_MODEL_PROFILE
from backend.llm.providers import build_langchain_chat_model
from backend.services.candidate_retrieval import search_candidates_hybrid


class CandidateMatchingError(RuntimeError):
    """
    Raised when candidate shortlisting fails after retrieval.
    """

    def __init__(
        self,
        message: str,
        *,
        stage: str,
        details: list[dict[str, Any]] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.stage = stage
        self.details = details or []


class CandidateShortlistAssessment(BaseModel):
    """
    One candidate selected by the LLM shortlist step.
    """

    model_config = ConfigDict(extra="forbid")

    candidate_id: str = Field(min_length=1)
    fit_score: int = Field(ge=0, le=100)
    fit_summary: str = Field(min_length=1)
    strengths: list[str] = Field(default_factory=list)
    gaps: list[str] = Field(default_factory=list)


class CandidateShortlistSelection(BaseModel):
    """
    Structured shortlist returned by the LLM.
    """

    model_config = ConfigDict(extra="forbid")

    shortlisted_candidates: list[CandidateShortlistAssessment] = Field(
        default_factory=list,
    )


def build_candidate_job_description_shortlist(
    *,
    job_description: str,
    retrieval_limit: int = 25,
    shortlist_limit: int = 3,
) -> dict[str, Any]:
    """
    Return a recruiter-facing shortlist for one free-text job description.
    """

    normalized_job_description = job_description.strip()
    if normalized_job_description == "":
        raise CandidateMatchingError(
            "Job description must not be blank.",
            stage="validation",
            details=[{"field": "job_description"}],
        )

    bounded_retrieval_limit = max(1, min(int(retrieval_limit), 100))
    bounded_shortlist_limit = max(1, min(int(shortlist_limit), 10))

    retrieved_candidates = search_candidates_hybrid(
        query=normalized_job_description,
        limit=bounded_retrieval_limit,
    )
    if not retrieved_candidates:
        return {
            "job_description": normalized_job_description,
            "retrieval_limit": bounded_retrieval_limit,
            "shortlist_limit": bounded_shortlist_limit,
            "retrieved_candidate_count": 0,
            "shortlisted_candidates": [],
        }

    shortlist_assessments = _rank_retrieved_candidates_for_job_description(
        job_description=normalized_job_description,
        retrieved_candidates=retrieved_candidates,
        shortlist_limit=bounded_shortlist_limit,
    )

    candidates_by_id = {
        str(candidate["candidate_id"]): candidate for candidate in retrieved_candidates
    }
    shortlisted_candidates: list[dict[str, Any]] = []
    seen_candidate_ids: set[str] = set()

    for assessment in shortlist_assessments:
        candidate_id = assessment.candidate_id.strip()
        if candidate_id == "" or candidate_id in seen_candidate_ids:
            continue
        matched_candidate = candidates_by_id.get(candidate_id)
        if matched_candidate is None:
            continue

        shortlisted_candidates.append(
            {
                "candidate_id": candidate_id,
                "person_id": matched_candidate["person_id"],
                "full_name": matched_candidate.get("full_name"),
                "current_title": matched_candidate.get("current_title"),
                "candidate_status": matched_candidate.get("candidate_status"),
                "current_company_name": matched_candidate.get(
                    "current_company_name"
                ),
                "resume_updated_at": matched_candidate.get("resume_updated_at"),
                "document_id": matched_candidate["document_id"],
                "document_title": matched_candidate.get("document_title"),
                "document_source_uri": matched_candidate.get("document_source_uri"),
                "retrieval_score": float(matched_candidate.get("match_score") or 0.0),
                "fit_score": assessment.fit_score,
                "fit_summary": assessment.fit_summary,
                "strengths": list(assessment.strengths),
                "gaps": list(assessment.gaps),
                "match_excerpt": matched_candidate.get("match_excerpt"),
            }
        )
        seen_candidate_ids.add(candidate_id)

        if len(shortlisted_candidates) >= bounded_shortlist_limit:
            break

    return {
        "job_description": normalized_job_description,
        "retrieval_limit": bounded_retrieval_limit,
        "shortlist_limit": bounded_shortlist_limit,
        "retrieved_candidate_count": len(retrieved_candidates),
        "shortlisted_candidates": shortlisted_candidates,
    }


def _rank_retrieved_candidates_for_job_description(
    *,
    job_description: str,
    retrieved_candidates: list[dict[str, Any]],
    shortlist_limit: int,
) -> list[CandidateShortlistAssessment]:
    """
    Ask the reasoning model to choose the strongest candidates from retrieval.
    """

    system_prompt = (
        "You are a recruitment assistant. "
        "You will receive a free-text job description and a retrieved pool of "
        "candidate resume matches. Choose only the strongest candidates for the role. "
        "Base your decision on the provided candidate data only. "
        "Do not invent missing experience. "
        "Prefer concrete evidence over generic recruiter language. "
        "Return no more than the requested shortlist limit."
    )

    candidate_payload = [
        {
            "candidate_id": candidate["candidate_id"],
            "full_name": candidate.get("full_name"),
            "current_title": candidate.get("current_title"),
            "candidate_status": candidate.get("candidate_status"),
            "current_company_name": candidate.get("current_company_name"),
            "resume_updated_at": candidate.get("resume_updated_at"),
            "document_title": candidate.get("document_title"),
            "retrieval_score": candidate.get("match_score"),
            "match_excerpt": candidate.get("match_excerpt"),
        }
        for candidate in retrieved_candidates
    ]

    user_prompt = (
        f"Job description:\n{job_description}\n\n"
        f"Return the top {shortlist_limit} candidates only.\n\n"
        "Retrieved candidates:\n"
        f"{json.dumps(candidate_payload, indent=2, ensure_ascii=False)}\n\n"
        "For each shortlisted candidate:\n"
        "- use the exact candidate_id from the supplied list\n"
        "- assign a fit_score from 0 to 100\n"
        "- write one brief fit_summary grounded in the retrieved evidence\n"
        "- list concrete strengths as short evidence-backed bullet phrases\n"
        "- list any obvious gaps only when they are genuinely missing or unclear from the evidence\n"
        "- avoid generic filler such as 'strong background' unless you name the actual area\n"
    )

    prompt = ChatPromptTemplate.from_messages(
        [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt),
        ]
    )

    try:
        chat_model = build_langchain_chat_model(
            profile=DEFAULT_REASONING_MODEL_PROFILE,
        )
        structured_model = chat_model.with_structured_output(
            CandidateShortlistSelection
        )
        chain = prompt | structured_model
        raw_result = chain.invoke({})
    except Exception as exc:  # pragma: no cover - exercised via service tests
        raise CandidateMatchingError(
            "Candidate shortlisting failed during LLM ranking.",
            stage="llm_ranking",
            details=[{"error_type": exc.__class__.__name__, "message": str(exc)}],
        ) from exc

    if isinstance(raw_result, CandidateShortlistSelection):
        return raw_result.shortlisted_candidates

    if isinstance(raw_result, dict):
        return CandidateShortlistSelection(**raw_result).shortlisted_candidates

    raise CandidateMatchingError(
        "Candidate shortlisting returned an unexpected response shape.",
        stage="llm_ranking",
        details=[{"result_type": raw_result.__class__.__name__}],
    )


__all__ = [
    "CandidateMatchingError",
    "CandidateShortlistAssessment",
    "CandidateShortlistSelection",
    "build_candidate_job_description_shortlist",
]
