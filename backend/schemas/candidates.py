"""
Candidate API response schemas.

This module contains small Pydantic models used by candidate-related API
endpoints.

It gives the rest of the repository a stable way to talk about:

- the API response shape for one candidate profile view
- returning candidate data and linked skills together
- generating FastAPI/OpenAPI documentation for candidate endpoints
- keeping route modules focused on request handling rather than schema classes

Keeping these schemas in their own module makes the project easier to extend
because:

- candidate route modules can stay focused on endpoint behaviour
- tests can assert one shared response contract
- future candidate endpoints can reuse the same schema file
- response model growth has a clear home

In plain language:

- this module answers the question:

    "What should a candidate profile API response look like?"

- it does not define database tables
- it does not run SQL queries
- it does not contain route handlers
- it does not decide how candidate data is fetched
"""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class CandidateProfileResponse(BaseModel):
    """
    Combined candidate profile response returned by the API.

    Attributes
    ----------
    candidate : dict[str, Any]
        Canonical candidate profile data returned by the service layer.

    skills : list[dict[str, Any]]
        Skills linked to the candidate, including evidence and confidence where
        available.

    Notes
    -----
    - The underlying candidate and skill dictionaries currently come from the
      prototype Supabase/Postgres service layer.
    - This response model is intentionally a thin wrapper around those service
      results for the current prototype stage.
    - Later, if the API contract needs stricter field-level typing, this model
      is the right place to introduce that.
    - For now, keeping the nested payloads as dictionaries lets the API move
      quickly while the canonical schema is still being proven out.
    - Once the candidate profile shape stabilises, the nested dictionaries can
      be replaced with more explicit Pydantic models.

    Example
    -------
    A successful response should look like:

        {
            "candidate": {
                "candidate_id": "33333333-3333-3333-3333-333333333331",
                "full_name": "Sarah Jones"
            },
            "skills": [
                {
                    "skill_name": "Python",
                    "confidence": 0.98
                }
            ]
        }

    In plain language:

    - `candidate` holds the main candidate profile details
    - `skills` holds the linked skill rows for that candidate
    - together they form the first usable candidate profile view exposed by the API
    """

    # Reject unexpected top-level fields so the route response stays explicit
    #   - Without this, accidental extra keys could appear in responses and
    #     still pass validation.
    #   - This is useful here because this schema is part of the public API
    #     contract, even though the nested candidate/skill payloads are still
    #     flexible dictionaries for the prototype stage.
    model_config = ConfigDict(extra="forbid")

    # `candidate` contains the main candidate profile object returned by the
    # service layer
    #   - At the moment this is a plain dictionary because the profile fields
    #     are still evolving with the prototype schema.
    #   - This field is required because the route only returns this model when
    #     a candidate has been found.
    candidate: dict[str, Any] = Field(
        description="Canonical candidate profile data.",
    )

    # `skills` contains the skill rows linked to the candidate
    #   - This defaults to an empty list so API clients do not need to handle
    #     `null` when a candidate has no skills.
    #   - Keeping this as a list also matches the output shape from the current
    #     service helper.
    skills: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Skills linked to the candidate.",
    )


__all__ = ["CandidateProfileResponse"]
