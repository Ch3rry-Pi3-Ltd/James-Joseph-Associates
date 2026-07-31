"""Application service for private saved role briefs and result snapshots."""

from __future__ import annotations

from typing import Any

from backend.db.candidate_saved_briefs import (
    create_candidate_saved_brief,
    delete_candidate_saved_brief,
    get_candidate_saved_brief,
    list_candidate_saved_briefs,
    update_candidate_saved_brief,
)


class CandidateSavedBriefError(RuntimeError):
    """Controlled saved-brief failure with an HTTP-friendly error category."""

    def __init__(self, message: str, *, code: str, status_code: int) -> None:
        super().__init__(message)
        self.message = message
        self.code = code
        self.status_code = status_code


def create_saved_brief(
    *,
    created_by_user_id: str,
    created_by_email: str | None,
    payload: dict[str, Any],
) -> dict[str, Any]:
    """Normalize and create one operator-owned saved role brief."""

    row = create_candidate_saved_brief(
        created_by_user_id=created_by_user_id.strip(),
        created_by_email=_normalize_email(created_by_email),
        **_normalize_payload(payload),
    )
    return _serialize_detail(row)


def list_saved_briefs(
    *,
    created_by_user_id: str,
    limit: int,
) -> dict[str, Any]:
    """List compact saved-brief summaries for one operator."""

    rows = list_candidate_saved_briefs(
        created_by_user_id=created_by_user_id.strip(),
        limit=limit,
    )
    return {
        "saved_briefs": [_serialize_summary(row) for row in rows],
        "count": len(rows),
    }


def load_saved_brief(
    *,
    saved_brief_id: str,
    created_by_user_id: str,
) -> dict[str, Any]:
    """Load one operator-owned role brief and its latest result snapshots."""

    row = get_candidate_saved_brief(
        saved_brief_id=saved_brief_id,
        created_by_user_id=created_by_user_id.strip(),
    )
    if row is None:
        raise CandidateSavedBriefError(
            "Saved role brief was not found.",
            code="saved_brief_not_found",
            status_code=404,
        )
    return _serialize_detail(row)


def update_saved_brief(
    *,
    saved_brief_id: str,
    created_by_user_id: str,
    created_by_email: str | None,
    payload: dict[str, Any],
) -> dict[str, Any]:
    """Update one saved role brief when it belongs to the operator."""

    row = update_candidate_saved_brief(
        saved_brief_id=saved_brief_id,
        created_by_user_id=created_by_user_id.strip(),
        created_by_email=_normalize_email(created_by_email),
        **_normalize_payload(payload),
    )
    if row is None:
        raise CandidateSavedBriefError(
            "Saved role brief was not found.",
            code="saved_brief_not_found",
            status_code=404,
        )
    return _serialize_detail(row)


def remove_saved_brief(
    *,
    saved_brief_id: str,
    created_by_user_id: str,
) -> None:
    """Delete one operator-owned role brief."""

    deleted = delete_candidate_saved_brief(
        saved_brief_id=saved_brief_id,
        created_by_user_id=created_by_user_id.strip(),
    )
    if not deleted:
        raise CandidateSavedBriefError(
            "Saved role brief was not found.",
            code="saved_brief_not_found",
            status_code=404,
        )


def _normalize_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Normalize optional text while preserving validated result snapshots."""

    return {
        "title": str(payload["title"]).strip(),
        "job_description": str(payload["job_description"]).strip(),
        "target_company_name": (
            str(payload.get("target_company_name") or "").strip() or None
        ),
        "retrieval_focus_terms": str(payload["retrieval_focus_terms"]).strip(),
        "search_result_limit": int(payload["search_result_limit"]),
        "retrieval_limit": int(payload["retrieval_limit"]),
        "shortlist_limit": int(payload["shortlist_limit"]),
        "last_match_run_id": (
            str(payload["last_match_run_id"])
            if payload.get("last_match_run_id") is not None
            else None
        ),
        "retrieved_candidate_count": int(payload["retrieved_candidate_count"]),
        "search_results": list(payload["search_results"]),
        "shortlisted_candidates": list(payload["shortlisted_candidates"]),
    }


def _normalize_email(value: str | None) -> str | None:
    """Normalize an optional authenticated operator email."""

    return (value or "").strip().casefold() or None


def _serialize_detail(row: dict[str, Any]) -> dict[str, Any]:
    """Convert database identifiers into the stable API detail payload."""

    return {
        "saved_brief_id": str(row["id"]),
        "title": row["title"],
        "job_description": row["job_description"],
        "target_company_name": row.get("target_company_name"),
        "retrieval_focus_terms": row["retrieval_focus_terms"],
        "search_result_limit": row["search_result_limit"],
        "retrieval_limit": row["retrieval_limit"],
        "shortlist_limit": row["shortlist_limit"],
        "last_match_run_id": (
            str(row["last_match_run_id"])
            if row.get("last_match_run_id") is not None
            else None
        ),
        "retrieved_candidate_count": row["retrieved_candidate_count"],
        "search_results": row["search_results"],
        "shortlisted_candidates": row["shortlisted_candidates"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def _serialize_summary(row: dict[str, Any]) -> dict[str, Any]:
    """Convert one compact database row into a saved-brief list item."""

    return {
        "saved_brief_id": str(row["id"]),
        "title": row["title"],
        "target_company_name": row.get("target_company_name"),
        "job_description_preview": row["job_description_preview"],
        "last_match_run_id": (
            str(row["last_match_run_id"])
            if row.get("last_match_run_id") is not None
            else None
        ),
        "retrieved_candidate_count": row["retrieved_candidate_count"],
        "search_result_count": row["search_result_count"],
        "shortlist_count": row["shortlist_count"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


__all__ = [
    "CandidateSavedBriefError",
    "create_saved_brief",
    "list_saved_briefs",
    "load_saved_brief",
    "remove_saved_brief",
    "update_saved_brief",
]
