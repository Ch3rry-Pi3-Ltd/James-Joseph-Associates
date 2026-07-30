"""
Persistence helpers for recruiter feedback on candidate shortlist results.
"""

from __future__ import annotations

from typing import Any

from backend.db.connection import postgres_connection


def upsert_candidate_match_feedback(
    *,
    match_run_id: str,
    candidate_id: str,
    document_id: str | None,
    reviewer_user_id: str,
    reviewer_email: str | None,
    feedback_value: str,
    feedback_reason: str | None,
    job_description_hash: str,
    job_description: str,
    shortlist_rank: int,
    fit_score: int,
    retrieval_score: float,
    graph_context_score: float | None,
    ranking_input_score: float | None,
    source_category: str,
) -> dict[str, Any]:
    """Insert or update one reviewer's judgement for one shortlist result."""

    query = """
        INSERT INTO candidate_match_feedback (
            match_run_id,
            candidate_id,
            document_id,
            reviewer_user_id,
            reviewer_email,
            feedback_value,
            feedback_reason,
            job_description_hash,
            job_description,
            shortlist_rank,
            fit_score,
            retrieval_score,
            graph_context_score,
            ranking_input_score,
            source_category
        )
        VALUES (
            %(match_run_id)s::uuid,
            %(candidate_id)s::uuid,
            %(document_id)s::uuid,
            %(reviewer_user_id)s,
            %(reviewer_email)s,
            %(feedback_value)s,
            %(feedback_reason)s,
            %(job_description_hash)s,
            %(job_description)s,
            %(shortlist_rank)s,
            %(fit_score)s,
            %(retrieval_score)s,
            %(graph_context_score)s,
            %(ranking_input_score)s,
            %(source_category)s
        )
        ON CONFLICT (match_run_id, candidate_id, reviewer_user_id)
        DO UPDATE SET
            document_id = EXCLUDED.document_id,
            reviewer_email = EXCLUDED.reviewer_email,
            feedback_value = EXCLUDED.feedback_value,
            feedback_reason = EXCLUDED.feedback_reason,
            job_description_hash = EXCLUDED.job_description_hash,
            job_description = EXCLUDED.job_description,
            shortlist_rank = EXCLUDED.shortlist_rank,
            fit_score = EXCLUDED.fit_score,
            retrieval_score = EXCLUDED.retrieval_score,
            graph_context_score = EXCLUDED.graph_context_score,
            ranking_input_score = EXCLUDED.ranking_input_score,
            source_category = EXCLUDED.source_category
        RETURNING
            id,
            match_run_id,
            candidate_id,
            reviewer_user_id,
            reviewer_email,
            feedback_value,
            feedback_reason,
            created_at,
            updated_at
    """
    parameters = {
        "match_run_id": match_run_id,
        "candidate_id": candidate_id,
        "document_id": document_id,
        "reviewer_user_id": reviewer_user_id,
        "reviewer_email": reviewer_email,
        "feedback_value": feedback_value,
        "feedback_reason": feedback_reason,
        "job_description_hash": job_description_hash,
        "job_description": job_description,
        "shortlist_rank": shortlist_rank,
        "fit_score": fit_score,
        "retrieval_score": retrieval_score,
        "graph_context_score": graph_context_score,
        "ranking_input_score": ranking_input_score,
        "source_category": source_category,
    }

    with postgres_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(query, parameters)
            row = cursor.fetchone()
        connection.commit()

    if row is None:
        raise RuntimeError("Candidate match feedback was not returned after upsert.")

    return dict(row)


__all__ = ["upsert_candidate_match_feedback"]
