"""
Skill read helpers for the intelligence backend.

This module contains small database query helpers for reading skill data from
the prototype Supabase/Postgres schema.

It gives the rest of the repository a stable way to talk about:

- fetching the skills linked to one canonical candidate
- joining candidate-skill links to the normalised skill table
- returning a predictable list of dictionary-like result rows
- exposing evidence and confidence attached to extracted candidate skills

Keeping this logic in its own module makes the project easier to grow because:

- route handlers do not need to embed raw SQL
- skill-specific queries stay near each other
- tests can target one small read module at a time
- future repository/service code can build on top of these helpers

In plain language:

- this module answers the question:

    "How does the backend read candidate skills from Postgres?"

- it does not define database tables
- it does not create routes
- it does not write data
- it only reads skill-related records
"""

from typing import Any

from backend.db.connection import postgres_connection


def get_candidate_skills(candidate_id: str) -> list[dict[str, Any]]:
    """
    Return the skills linked to one candidate.

    Parameters
    ----------
    candidate_id : str
        Canonical candidate UUID to look up.

    Returns
    -------
    list[dict[str, Any]]
        List of dictionary rows describing the candidate's linked skills.

        An empty list is returned if the candidate has no linked skills.

    Notes
    -----
    - This reads from the prototype canonical schema, not directly from JobAdder.
    - The query joins:
      - `candidate_skills`
      - `skills`
    - Results are ordered by canonical skill name and then display name so the
      output stays stable for tests and later API responses.

    Returned fields
    ---------------
    Each row currently includes:

    - `candidate_id`
    - `skill_id`
    - `skill_name`
    - `canonical_name`
    - `skill_type`
    - `confidence`
    - `evidence_text`

    In plain language:

    - find the candidate's linked skills
    - include the normalised skill details
    - include confidence and evidence
    - return a list, even if it is empty
    """

    query = """
        SELECT
            cs.candidate_id,
            s.id AS skill_id,
            s.name AS skill_name,
            s.canonical_name,
            s.skill_type,
            cs.confidence,
            cs.evidence_text
        FROM candidate_skills cs
        JOIN skills s
            ON s.id = cs.skill_id
        WHERE cs.candidate_id = %(candidate_id)s
        ORDER BY
            s.canonical_name NULLS LAST,
            s.name
    """

    with postgres_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                query,
                {"candidate_id": candidate_id},
            )
            rows = cursor.fetchall()

    # `fetchall()` returns a list-like collection of rows.
    #   - Converting each row to a plain dict keeps the result predictable for
    #     later services, routes, and tests.
    return [dict(row) for row in rows]


__all__ = [
    "get_candidate_skills",
]
