"""
Candidate read helpers for the intelligence backend.

This module contains small database query helpers for reading candidate data
from the prototype Supabase/Postgres schema.

It gives the rest of the repository a stable way to talk about:

- fetching one canonical candidate profile
- joining the candidate record to the linked person record
- joining the candidate record to the current company record
- returning a predictable dictionary-like result shape

Keeping this logic in its own module makes the project easier to grow because:

- route handlers do not need to embed raw SQL
- candidate-specific queries stay near each other
- tests can target one small read module at a time
- future repository/service code can build on top of these helpers

In plain language:

- this module answers the question:

    "How does the backend read a candidate profile from Postgres?"

- it does not define database tables
- it does not create routes
- it does not write data
- it only reads candidate-related records

Notes
-----
- This module currently targets the prototype schema.
- The query shape may evolve once we inspect real source-system payloads.
- The helper returns a simple dictionary-like object so later layers can decide
  how to serialise it for APIs or workflows.

Important boundaries
--------------------
This module should not contain:

- FastAPI route handlers
- request/response models
- write/update logic
- LLM calls
- LangGraph workflow steps
- business decisions about matching or ranking
"""

from typing import Any

from backend.db.connection import postgres_connection


def get_candidate_profile(candidate_id: str) -> dict[str, Any] | None:
    """
    Return one candidate profile joined to person and company details.

    Parameters
    ----------
    candidate_id : str
        Canonical candidate UUID to look up.

    Returns
    -------
    dict[str, Any] | None
        Dictionary-like row containing the joined candidate profile fields.

        Returns `None` if no candidate exists for the supplied ID.

    Notes
    -----
    - This reads from the prototype canonical schema, not directly from JobAdder.
    - The query joins:
      - `candidates`
      - `people`
      - `companies`
    - A left join is used for the current company because the candidate may not
      always have a linked company record.

    Returned fields
    ---------------
    The row currently includes:

    - `candidate_id`
    - `person_id`
    - `full_name`
    - `first_name`
    - `last_name`
    - `primary_email`
    - `primary_phone`
    - `linkedin_url`
    - `location`
    - `headline`
    - `summary`
    - `current_title`
    - `candidate_status`
    - `availability_status`
    - `salary_expectation`
    - `notice_period`
    - `last_contacted_at`
    - `resume_updated_at`
    - `current_company_id`
    - `current_company_name`

    In plain language:

    - find one candidate by canonical ID
    - include the linked person details
    - include the linked current company name if present
    - return one row or nothing

    Example
    -------
    Read one candidate profile by canonical candidate ID:

        from backend.db.candidates import get_candidate_profile

        profile = get_candidate_profile(
            "33333333-3333-3333-3333-333333333331",
        )

        if profile is not None:
            print(profile["full_name"])
            print(profile["current_company_name"])
    """

    query = """
        SELECT
            c.id AS candidate_id,
            p.id AS person_id,
            p.full_name,
            p.first_name,
            p.last_name,
            p.primary_email,
            p.primary_phone,
            p.linkedin_url,
            p.location,
            p.headline,
            p.summary,
            c.current_title,
            c.candidate_status,
            c.availability_status,
            c.salary_expectation,
            c.notice_period,
            c.last_contacted_at,
            c.resume_updated_at,
            co.id AS current_company_id,
            co.name AS current_company_name
        FROM candidates c
        JOIN people p
            ON p.id = c.person_id
        LEFT JOIN companies co
            ON co.id = c.current_company_id
        WHERE c.id = %(candidate_id)s
        LIMIT 1
    """

    with postgres_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                query,
                {"candidate_id": candidate_id},
            )
            row = cursor.fetchone()

    # `fetchone()` returns `None` when no row matches the candidate ID.
    #   - Returning `None` keeps the calling code simple and explicit.
    if row is None:
        return None

    return dict(row)


__all__ = [
    "get_candidate_profile",
]
