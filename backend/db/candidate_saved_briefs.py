"""Persistence helpers for private recruiter role briefs and result snapshots."""

from __future__ import annotations

from typing import Any

from psycopg.types.json import Jsonb

from backend.db.connection import postgres_connection


def create_candidate_saved_brief(
    *,
    created_by_user_id: str,
    created_by_email: str | None,
    title: str,
    job_description: str,
    target_company_name: str | None,
    retrieval_focus_terms: str,
    search_result_limit: int,
    retrieval_limit: int,
    shortlist_limit: int,
    last_match_run_id: str | None,
    retrieved_candidate_count: int,
    search_results: list[dict[str, Any]],
    shortlisted_candidates: list[dict[str, Any]],
) -> dict[str, Any]:
    """Insert one saved role brief owned by the authenticated operator."""

    query = """
        INSERT INTO candidate_saved_briefs (
            created_by_user_id,
            created_by_email,
            title,
            job_description,
            target_company_name,
            retrieval_focus_terms,
            search_result_limit,
            retrieval_limit,
            shortlist_limit,
            last_match_run_id,
            retrieved_candidate_count,
            search_results,
            shortlisted_candidates
        )
        VALUES (
            %(created_by_user_id)s,
            %(created_by_email)s,
            %(title)s,
            %(job_description)s,
            %(target_company_name)s,
            %(retrieval_focus_terms)s,
            %(search_result_limit)s,
            %(retrieval_limit)s,
            %(shortlist_limit)s,
            %(last_match_run_id)s::uuid,
            %(retrieved_candidate_count)s,
            %(search_results)s,
            %(shortlisted_candidates)s
        )
        RETURNING *
    """
    parameters = _build_parameters(
        created_by_user_id=created_by_user_id,
        created_by_email=created_by_email,
        title=title,
        job_description=job_description,
        target_company_name=target_company_name,
        retrieval_focus_terms=retrieval_focus_terms,
        search_result_limit=search_result_limit,
        retrieval_limit=retrieval_limit,
        shortlist_limit=shortlist_limit,
        last_match_run_id=last_match_run_id,
        retrieved_candidate_count=retrieved_candidate_count,
        search_results=search_results,
        shortlisted_candidates=shortlisted_candidates,
    )

    with postgres_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(query, parameters)
            row = cursor.fetchone()
        connection.commit()

    if row is None:
        raise RuntimeError("Saved role brief was not returned after insert.")
    return dict(row)


def list_candidate_saved_briefs(
    *,
    created_by_user_id: str,
    limit: int,
) -> list[dict[str, Any]]:
    """Return compact saved-brief summaries for one operator."""

    query = """
        SELECT
            id,
            title,
            target_company_name,
            LEFT(job_description, 240) AS job_description_preview,
            last_match_run_id,
            retrieved_candidate_count,
            jsonb_array_length(search_results) AS search_result_count,
            jsonb_array_length(shortlisted_candidates) AS shortlist_count,
            created_at,
            updated_at
        FROM candidate_saved_briefs
        WHERE created_by_user_id = %(created_by_user_id)s
        ORDER BY updated_at DESC, id DESC
        LIMIT %(limit)s
    """

    with postgres_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                query,
                {
                    "created_by_user_id": created_by_user_id,
                    "limit": limit,
                },
            )
            rows = cursor.fetchall()

    return [dict(row) for row in rows]


def get_candidate_saved_brief(
    *,
    saved_brief_id: str,
    created_by_user_id: str,
) -> dict[str, Any] | None:
    """Return one saved brief only when it belongs to the requesting operator."""

    query = """
        SELECT *
        FROM candidate_saved_briefs
        WHERE id = %(saved_brief_id)s::uuid
          AND created_by_user_id = %(created_by_user_id)s
        LIMIT 1
    """

    with postgres_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                query,
                {
                    "saved_brief_id": saved_brief_id,
                    "created_by_user_id": created_by_user_id,
                },
            )
            row = cursor.fetchone()

    return dict(row) if row is not None else None


def update_candidate_saved_brief(
    *,
    saved_brief_id: str,
    created_by_user_id: str,
    created_by_email: str | None,
    title: str,
    job_description: str,
    target_company_name: str | None,
    retrieval_focus_terms: str,
    search_result_limit: int,
    retrieval_limit: int,
    shortlist_limit: int,
    last_match_run_id: str | None,
    retrieved_candidate_count: int,
    search_results: list[dict[str, Any]],
    shortlisted_candidates: list[dict[str, Any]],
) -> dict[str, Any] | None:
    """Update one saved role brief without crossing operator ownership."""

    query = """
        UPDATE candidate_saved_briefs
        SET
            created_by_email = %(created_by_email)s,
            title = %(title)s,
            job_description = %(job_description)s,
            target_company_name = %(target_company_name)s,
            retrieval_focus_terms = %(retrieval_focus_terms)s,
            search_result_limit = %(search_result_limit)s,
            retrieval_limit = %(retrieval_limit)s,
            shortlist_limit = %(shortlist_limit)s,
            last_match_run_id = %(last_match_run_id)s::uuid,
            retrieved_candidate_count = %(retrieved_candidate_count)s,
            search_results = %(search_results)s,
            shortlisted_candidates = %(shortlisted_candidates)s
        WHERE id = %(saved_brief_id)s::uuid
          AND created_by_user_id = %(created_by_user_id)s
        RETURNING *
    """
    parameters = _build_parameters(
        created_by_user_id=created_by_user_id,
        created_by_email=created_by_email,
        title=title,
        job_description=job_description,
        target_company_name=target_company_name,
        retrieval_focus_terms=retrieval_focus_terms,
        search_result_limit=search_result_limit,
        retrieval_limit=retrieval_limit,
        shortlist_limit=shortlist_limit,
        last_match_run_id=last_match_run_id,
        retrieved_candidate_count=retrieved_candidate_count,
        search_results=search_results,
        shortlisted_candidates=shortlisted_candidates,
    )
    parameters["saved_brief_id"] = saved_brief_id

    with postgres_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(query, parameters)
            row = cursor.fetchone()
        connection.commit()

    return dict(row) if row is not None else None


def delete_candidate_saved_brief(
    *,
    saved_brief_id: str,
    created_by_user_id: str,
) -> bool:
    """Delete one saved role brief without crossing operator ownership."""

    query = """
        DELETE FROM candidate_saved_briefs
        WHERE id = %(saved_brief_id)s::uuid
          AND created_by_user_id = %(created_by_user_id)s
        RETURNING id
    """

    with postgres_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                query,
                {
                    "saved_brief_id": saved_brief_id,
                    "created_by_user_id": created_by_user_id,
                },
            )
            row = cursor.fetchone()
        connection.commit()

    return row is not None


def _build_parameters(
    *,
    created_by_user_id: str,
    created_by_email: str | None,
    title: str,
    job_description: str,
    target_company_name: str | None,
    retrieval_focus_terms: str,
    search_result_limit: int,
    retrieval_limit: int,
    shortlist_limit: int,
    last_match_run_id: str | None,
    retrieved_candidate_count: int,
    search_results: list[dict[str, Any]],
    shortlisted_candidates: list[dict[str, Any]],
) -> dict[str, Any]:
    """Build the shared insert/update parameter mapping."""

    return {
        "created_by_user_id": created_by_user_id,
        "created_by_email": created_by_email,
        "title": title,
        "job_description": job_description,
        "target_company_name": target_company_name,
        "retrieval_focus_terms": retrieval_focus_terms,
        "search_result_limit": search_result_limit,
        "retrieval_limit": retrieval_limit,
        "shortlist_limit": shortlist_limit,
        "last_match_run_id": last_match_run_id,
        "retrieved_candidate_count": retrieved_candidate_count,
        "search_results": Jsonb(search_results),
        "shortlisted_candidates": Jsonb(shortlisted_candidates),
    }


__all__ = [
    "create_candidate_saved_brief",
    "delete_candidate_saved_brief",
    "get_candidate_saved_brief",
    "list_candidate_saved_briefs",
    "update_candidate_saved_brief",
]
