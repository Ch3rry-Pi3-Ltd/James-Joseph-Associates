"""
Operator-facing review endpoints.

This module exposes a compact read-only view of what is currently stored in the
canonical Supabase/Postgres schema so operators can inspect the state of the
ingestion work without going through raw tables.

It gives the rest of the repository a stable way to talk about:

- one small internal review route
- a read-only inspection surface for canonical data
- keeping overview reads separate from ingestion logic
"""

from fastapi import APIRouter, Query

from backend.schemas.review import ReviewOverviewResponse
from backend.services.review_overview import build_review_overview


router = APIRouter(prefix="/review", tags=["review"])


@router.get(
    "/overview",
    response_model=ReviewOverviewResponse,
)
def get_review_overview_route(
    limit: int = Query(
        default=10,
        ge=1,
        le=50,
        description="Maximum number of rows to include in each recent list.",
    ),
) -> ReviewOverviewResponse:
    """
    Return a compact overview of the canonical database contents.

    Parameters
    ----------
    limit : int, default=10
        Maximum number of rows to include in each recent list.

    Returns
    -------
    ReviewOverviewResponse
        Operator-facing overview payload used by the first review UI.

    Notes
    -----
    - This route is intentionally read-only.
    - It is designed for quick inspection, not bulk export.
    - The `limit` parameter is bounded so one request cannot accidentally turn
      the first review page into a heavy table dump.

    Example
    -------
    The public route looks like:

        GET /api/v1/review/overview?limit=5

    A successful response looks like:

        {
            "counts": {
                "people": 5,
                "candidates": 5
            },
            "recent_candidates": [...],
            "recent_jobs": [...],
            "recent_applications": [...],
            "recent_documents": [...],
            "recent_source_records": [...],
            "recent_reconciliation_decisions": [...]
        }

    In plain language:

    - return headline entity counts
    - return a few recent rows from the main canonical tables
    - keep the payload small enough for a first internal review page
    """

    return ReviewOverviewResponse(**build_review_overview(limit=limit))


__all__ = ["router"]
