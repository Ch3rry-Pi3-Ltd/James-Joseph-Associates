"""
Review API response schemas.

This module contains the response model for the first operator-facing database
review endpoint.

It gives the rest of the repository a stable way to talk about:

- the public response shape for the review overview route
- headline counts plus recent-row slices
- OpenAPI documentation for the first review surface
"""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ReviewOverviewResponse(BaseModel):
    """
    Compact review payload returned by the API.

    Notes
    -----
    - The nested rows remain flexible dictionaries for now because the review
      surface is still exploratory.
    - Once the operator page stabilises, the nested row models can become more
      explicit.
    - The top-level response shape is strict even though the nested row shapes
      are still intentionally loose.

    Example
    -------
    A successful response looks like:

        {
            "counts": {
                "candidates": 14,
                "jobs": 3
            },
            "recent_candidates": [],
            "recent_jobs": [],
            "recent_applications": [],
            "recent_documents": [],
            "recent_source_records": []
        }

    In plain language:

    - `counts` holds the headline totals
    - each `recent_*` list holds a small operator-facing sample
    """

    # Keep the top-level response contract strict even while the nested row
    # dictionaries are still evolving.
    model_config = ConfigDict(extra="forbid")

    counts: dict[str, int] = Field(
        default_factory=dict,
        description="Headline canonical entity counts.",
    )
    recent_candidates: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Most recently changed canonical candidates.",
    )
    recent_jobs: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Most recently changed canonical jobs.",
    )
    recent_applications: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Most recently changed canonical applications.",
    )
    recent_documents: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Most recently changed canonical documents.",
    )
    recent_source_records: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Most recent source provenance records.",
    )


__all__ = ["ReviewOverviewResponse"]
