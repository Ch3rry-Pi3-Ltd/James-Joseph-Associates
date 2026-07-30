"""Persistence helpers for authenticated, expiring shortlist shares."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from psycopg.types.json import Jsonb

from backend.db.connection import postgres_connection


def upsert_candidate_shortlist_share(
    *,
    match_run_id: str,
    created_by_user_id: str,
    created_by_email: str | None,
    role_title: str | None,
    job_description: str,
    shortlisted_candidates: list[dict[str, Any]],
    expires_at: datetime,
) -> dict[str, Any]:
    """Create or refresh one creator's share for a shortlist run."""

    query = """
        INSERT INTO candidate_shortlist_shares (
            match_run_id,
            created_by_user_id,
            created_by_email,
            role_title,
            job_description,
            shortlisted_candidates,
            expires_at
        )
        VALUES (
            %(match_run_id)s::uuid,
            %(created_by_user_id)s,
            %(created_by_email)s,
            %(role_title)s,
            %(job_description)s,
            %(shortlisted_candidates)s,
            %(expires_at)s
        )
        ON CONFLICT (match_run_id, created_by_user_id)
        DO UPDATE SET
            created_by_email = EXCLUDED.created_by_email,
            role_title = EXCLUDED.role_title,
            job_description = EXCLUDED.job_description,
            shortlisted_candidates = EXCLUDED.shortlisted_candidates,
            expires_at = EXCLUDED.expires_at,
            revoked_at = NULL
        RETURNING *
    """
    parameters = {
        "match_run_id": match_run_id,
        "created_by_user_id": created_by_user_id,
        "created_by_email": created_by_email,
        "role_title": role_title,
        "job_description": job_description,
        "shortlisted_candidates": Jsonb(shortlisted_candidates),
        "expires_at": expires_at,
    }

    with postgres_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(query, parameters)
            row = cursor.fetchone()
        connection.commit()

    if row is None:
        raise RuntimeError("Shortlist share was not returned after upsert.")

    return dict(row)


def get_candidate_shortlist_share(share_id: str) -> dict[str, Any] | None:
    """Return one shortlist share without exposing other share records."""

    query = """
        SELECT *
        FROM candidate_shortlist_shares
        WHERE id = %(share_id)s::uuid
        LIMIT 1
    """

    with postgres_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(query, {"share_id": share_id})
            row = cursor.fetchone()

    return dict(row) if row is not None else None


def revoke_candidate_shortlist_share(
    *,
    share_id: str,
    created_by_user_id: str,
) -> dict[str, Any] | None:
    """Revoke a share only when the requesting operator created it."""

    query = """
        UPDATE candidate_shortlist_shares
        SET revoked_at = NOW()
        WHERE id = %(share_id)s::uuid
          AND created_by_user_id = %(created_by_user_id)s
          AND revoked_at IS NULL
        RETURNING *
    """

    with postgres_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                query,
                {
                    "share_id": share_id,
                    "created_by_user_id": created_by_user_id,
                },
            )
            row = cursor.fetchone()
        connection.commit()

    return dict(row) if row is not None else None


__all__ = [
    "get_candidate_shortlist_share",
    "revoke_candidate_shortlist_share",
    "upsert_candidate_shortlist_share",
]
