"""
Application service for recruiter feedback on candidate shortlist results.
"""

from __future__ import annotations

import hashlib
from typing import Any

from backend.db.candidate_match_feedback import upsert_candidate_match_feedback


def save_candidate_match_feedback(
    *,
    match_run_id: str,
    candidate_id: str,
    document_id: str | None,
    reviewer_user_id: str,
    reviewer_email: str | None,
    feedback_value: str,
    feedback_reason: str | None,
    job_description: str,
    shortlist_rank: int,
    fit_score: int,
    retrieval_score: float,
    graph_context_score: float | None,
    ranking_input_score: float | None,
    source_category: str,
) -> dict[str, Any]:
    """Normalize and persist one recruiter judgement and its ranking snapshot."""

    normalized_job_description = job_description.strip()
    normalized_reason = (feedback_reason or "").strip() or None
    normalized_email = (reviewer_email or "").strip().casefold() or None
    job_description_hash = hashlib.sha256(
        normalized_job_description.encode("utf-8")
    ).hexdigest()

    return upsert_candidate_match_feedback(
        match_run_id=match_run_id,
        candidate_id=candidate_id,
        document_id=document_id,
        reviewer_user_id=reviewer_user_id.strip(),
        reviewer_email=normalized_email,
        feedback_value=feedback_value,
        feedback_reason=normalized_reason,
        job_description_hash=job_description_hash,
        job_description=normalized_job_description,
        shortlist_rank=shortlist_rank,
        fit_score=fit_score,
        retrieval_score=retrieval_score,
        graph_context_score=graph_context_score,
        ranking_input_score=ranking_input_score,
        source_category=source_category.strip() or "unknown",
    )


__all__ = ["save_candidate_match_feedback"]
