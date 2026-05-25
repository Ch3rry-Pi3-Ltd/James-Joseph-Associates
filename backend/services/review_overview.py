"""
Review overview service helpers.

This module provides a thin service boundary for the operator-facing review
overview payload used by the first Supabase inspection page.

It gives the rest of the repository a stable way to talk about:

- one reusable review overview payload
- keeping routes free of direct database calls
- adding future composition logic without rewriting the route layer

In plain language:

- this module answers the question:

    "How does the API ask for the operator overview payload?"

- it does not run SQL directly
- it does not define FastAPI routes
- it exists so the route layer stays thin
"""

from typing import Any

from backend.db.review import get_review_overview


def build_review_overview(limit: int = 10) -> dict[str, Any]:
    """
    Build one review overview payload for API and UI consumers.

    Parameters
    ----------
    limit : int, default=10
        Maximum number of rows to include in each recent list.

    Returns
    -------
    dict[str, Any]
        Compact database review payload.

    Notes
    -----
    - This is intentionally a thin service boundary right now.
    - If later we need filtering, permissions, or extra composition logic, this
      is the place to add it without rewriting the route layer.

    Example
    -------
    Build a five-row overview slice:

        from backend.services.review_overview import build_review_overview

        overview = build_review_overview(limit=5)
        print(overview["recent_documents"])

    In plain language:

    - ask the DB layer for the overview
    - return it unchanged for the API and UI
    """

    return get_review_overview(limit=limit)


__all__ = ["build_review_overview"]
