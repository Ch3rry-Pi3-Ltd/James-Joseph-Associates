"""
Candidate profile service helpters for the intelligence backend.

This module combines small database read helpers into a higher-level candidate
profile shape that later API routes, workflow steps, or service logic can use.

It gives the rest of the repository a stable way to talk about:

- reading one candidate profile
- reading the candidate's linked skills
- returning one combined backend-facing structure
- keeping composition logic out of route handlers

Keeping this logic in a service module makes the project easier to grow because:

- database query helpers stay focused on one table/query concern at a time
- route handlers do not need to coordinate multiple DB calls directly
- future workflow code can reuse one stable service function
- later enrichment logic can be added here without rewriting the DB helpers

In plain language:

- this module answers the question:

    "How does the backend assemble a candidate profile view?"

- it does not define SQL tables
- it does not create routes
- it does not write data
- it only coordinates existing read helpers
"""

from typing import Any

from backend.db.candidates import get_candidate_profile
from backend.db.skills import get_candidate_skills

def build_candidate_profile(candidate_id: str) -> dict[str, Any] | None:
    """
    Return one combined profile structure.

    Parameters
    ----------
    candidate_id : str
        Canonical candidate UUID to lookup.

    Returns
    -------
    dict[str, Any] | None
        Combined candidate profile structure.

        Returns `None` if the candidate does not exist.

    Notes
    -----
    - This function composes lower-level DB read helpers.
    - If the candidate profile does not exist, the function returns `None`
      immediately.
    - If the candidate exists, the returned structure includes:

        - the candidate profile data
        - the list of linked skills

    Returned shape
    --------------
    The returned dictionary currently looks like:

        {
            "candidate": {...},
            "skills": {...},
        }

    In plain language:

    - fetch the candidate profile
    - stop if the candidate does not exist
    - fetch the candidate skills
    - return one combined object

    Example
    -------
    Build one backend-facing candidate profile object:

        from backend.services.candidate_profiles import build_candidate_profile

        profile = build_candidate_profile(
            "33333333-3333-3333-3333-333333333331",
        )

        if profile is not None:
            print(profile["candidate"]["full_name"])
            print(profile["skills"])
    """

    candidate = get_candidate_profile(candidate_id)

    # If the candidate does not exist, do not continue to the skill query
    #   - Returning early keeps the control flow explicit and avoids pointless
    #     extra database work.
    if candidate is None:
        return None
    
    skills = get_candidate_skills(candidate_id)

    return {
        "candidate": candidate,
        "skills": skills,
    }

__all__ = [
    "build_candidate_profile",
]