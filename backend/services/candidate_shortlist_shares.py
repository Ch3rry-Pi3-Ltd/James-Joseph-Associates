"""Application service for secure, expiring recruiter shortlist shares."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from backend.db.candidate_shortlist_shares import (
    get_candidate_shortlist_share,
    revoke_candidate_shortlist_share,
    upsert_candidate_shortlist_share,
)


class CandidateShortlistShareError(RuntimeError):
    """Controlled share failure with an HTTP-friendly error category."""

    def __init__(self, message: str, *, code: str, status_code: int) -> None:
        super().__init__(message)
        self.message = message
        self.code = code
        self.status_code = status_code


def create_candidate_shortlist_share(
    *,
    match_run_id: str,
    created_by_user_id: str,
    created_by_email: str | None,
    role_title: str | None,
    job_description: str,
    shortlisted_candidates: list[dict[str, Any]],
    expires_in_days: int,
) -> dict[str, Any]:
    """Normalize and persist one authenticated shortlist snapshot."""

    now = datetime.now(timezone.utc)
    row = upsert_candidate_shortlist_share(
        match_run_id=match_run_id,
        created_by_user_id=created_by_user_id.strip(),
        created_by_email=(created_by_email or "").strip().casefold() or None,
        role_title=(role_title or "").strip() or None,
        job_description=job_description.strip(),
        shortlisted_candidates=shortlisted_candidates,
        expires_at=now + timedelta(days=expires_in_days),
    )
    return _serialize_share(row, requesting_user_id=created_by_user_id)


def load_candidate_shortlist_share(
    *,
    share_id: str,
    requesting_user_id: str,
) -> dict[str, Any]:
    """Load an active share for an already authenticated approved operator."""

    row = get_candidate_shortlist_share(share_id)
    if row is None:
        raise CandidateShortlistShareError(
            "This shortlist link does not exist.",
            code="shortlist_share_not_found",
            status_code=404,
        )

    if row.get("revoked_at") is not None:
        raise CandidateShortlistShareError(
            "This shortlist link has been revoked.",
            code="shortlist_share_revoked",
            status_code=410,
        )

    expires_at = row["expires_at"]
    if expires_at <= datetime.now(timezone.utc):
        raise CandidateShortlistShareError(
            "This shortlist link has expired.",
            code="shortlist_share_expired",
            status_code=410,
        )

    return _serialize_share(row, requesting_user_id=requesting_user_id)


def revoke_shortlist_share(
    *,
    share_id: str,
    requesting_user_id: str,
) -> dict[str, Any]:
    """Revoke an active share when requested by its creator."""

    existing = get_candidate_shortlist_share(share_id)
    if existing is None:
        raise CandidateShortlistShareError(
            "This shortlist link does not exist.",
            code="shortlist_share_not_found",
            status_code=404,
        )
    if existing["created_by_user_id"] != requesting_user_id.strip():
        raise CandidateShortlistShareError(
            "Only the operator who created this link can revoke it.",
            code="shortlist_share_forbidden",
            status_code=403,
        )

    row = revoke_candidate_shortlist_share(
        share_id=share_id,
        created_by_user_id=requesting_user_id.strip(),
    )
    if row is None:
        row = existing

    return _serialize_share(row, requesting_user_id=requesting_user_id)


def _serialize_share(
    row: dict[str, Any],
    *,
    requesting_user_id: str,
) -> dict[str, Any]:
    """Convert database values into the stable API payload."""

    return {
        "share_id": str(row["id"]),
        "match_run_id": str(row["match_run_id"]),
        "role_title": row.get("role_title"),
        "job_description": row["job_description"],
        "shortlisted_candidates": row["shortlisted_candidates"],
        "created_by_email": row.get("created_by_email"),
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "expires_at": row["expires_at"],
        "revoked_at": row.get("revoked_at"),
        "can_revoke": (
            row["created_by_user_id"] == requesting_user_id.strip()
            and row.get("revoked_at") is None
        ),
    }


__all__ = [
    "CandidateShortlistShareError",
    "create_candidate_shortlist_share",
    "load_candidate_shortlist_share",
    "revoke_shortlist_share",
]
