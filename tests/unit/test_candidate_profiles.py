"""
Unit tests for candidate profile service helpers.

This module tests the service-level composition helper in
`backend.services.candidate_profiles`.

It gives the rest of the repository a stable way to check:

- the service returns `None` when the candidate does not exist
- the service does not fetch skills when the candidate is missing
- the service returns one combined structure when the candidate exists
- the service passes the same candidate ID through to both lower-level helpers
- the service can be tested without touching a real database

Keeping these tests small makes the service layer easier to trust because:

- composition logic is easier to debug when tested in isolation
- route handlers do not need to be the first place where orchestration bugs are found
- tests can validate the combined output shape without needing a live Supabase database
- the service layer can grow one small helper at a time

In plain language:

- this module answers the question:

    "Does the candidate profile service helper combine data correctly?"

- it does not connect to a real database
- it does not call Supabase over the network
- it does not test FastAPI routes
- it only tests local Python behaviour around the service helper

Mocking approach
----------------
These tests use `unittest.mock` helpers:

- `MagicMock()` creates flexible fake Python objects whose methods and return
  values can be controlled inside the test.
- `patch(...)` temporarily replaces the real dependency used by the code under
  test with one of those fake objects.

In this module, that means:

- we do not call the real DB helper functions
- we replace the helper names imported into `candidate_profiles.py`
- we control what those fake helpers return
- we inspect whether they were called correctly
"""

from unittest.mock import patch

from backend.services.candidate_profiles import build_candidate_profile


def test_build_candidate_profile_returns_none_when_candidate_is_missing() -> None:
    """
    Verify that the service returns `None` when the candidate does not exist.

    Notes
    -----
    - The service first calls `get_candidate_profile(candidate_id)`.
    - If that returns `None`, the service should stop immediately.
    - In that case, it should not try to fetch skills.

    In plain language:

    - pretend the candidate helper found nothing
    - call the service
    - confirm the result is `None`
    - confirm the skills helper was not called
    """

    # We patch the helper names as `candidate_profiles.py` sees them.
    #   - That is why the patch targets are:
    #       `backend.services.candidate_profiles.get_candidate_profile`
    #       `backend.services.candidate_profiles.get_candidate_skills`
    #
    #   - We are not patching the original source modules directly here.
    #     `with ... as ...` is Python's context-manager form.
    # 
    #   - In this case, it means:
    #
    #       - temporarily replace `get_candidate_profile` with a fake object
    #       - temporarily replace `get_candidate_skills` with another fake object
    #       - run the indented test code while those replacements are active
    #       - then automatically restore the real functions afterwards
    #
    #   - The `as mock_get_candidate_profile` part gives us a name for the fake
    #     replacement object created by `patch(...)`.
    #     That matters because we want to inspect it later and ask things like:
    #
    #       - was it called?
    #       - how many times was it called?
    #       - what arguments was it called with?
    #
    #   - So, in plain language, this block means:
    #
    #       - "while these two helper functions are temporarily faked,
    #           run `build_candidate_profile(...)` and let me inspect the fake helpers"
    #
    #   - The first patched helper is forced to return `None`, which simulates:
    #
    #       - "the candidate was not found"
    #
    #   - The second patched helper is not given a return value on purpose.
    #     We are not interested in its output here.
    #     We only want to check whether the service tried to call it at all.
    with patch(
        "backend.services.candidate_profiles.get_candidate_profile",
        return_value=None,
    ) as mock_get_candidate_profile, patch(
        "backend.services.candidate_profiles.get_candidate_skills",
    ) as mock_get_candidate_skills:
        # Run the service while the two helper functions are still patched.
        #
        # Because the fake `get_candidate_profile(...)` returns `None`,
        # the service should behave as though the candidate does not exist.
        result = build_candidate_profile(
            "33333333-3333-3333-3333-333333333331",
        )

    assert result is None
    mock_get_candidate_profile.assert_called_once_with(
        "33333333-3333-3333-3333-333333333331",
    )
    mock_get_candidate_skills.assert_not_called()


def test_build_candidate_profile_returns_combined_structure_when_candidate_exists() -> None:
    """
    Verify that the service returns the expected combined structure.

    Notes
    -----
    - If the candidate helper returns a candidate dictionary,
      the service should then fetch skills.
    - The final result should combine both pieces into one dictionary with:
      - `candidate`
      - `skills`

    In plain language:

    - pretend the candidate helper returned a candidate
    - pretend the skills helper returned a list of skills
    - call the service
    - confirm the result combines both pieces exactly
    """

    candidate = {
        "candidate_id": "33333333-3333-3333-3333-333333333331",
        "full_name": "Sarah Jones",
        "current_title": "Senior Data Engineer",
        "current_company_name": "Acme Hiring Ltd",
        "candidate_status": "active",
    }

    skills = [
        {
            "candidate_id": "33333333-3333-3333-3333-333333333331",
            "skill_id": "99999999-9999-9999-9999-999999999991",
            "skill_name": "Python",
            "canonical_name": "python",
            "skill_type": "technical",
            "confidence": 0.9800,
            "evidence_text": "Python mentioned in CV and job history.",
        },
        {
            "candidate_id": "33333333-3333-3333-3333-333333333331",
            "skill_id": "99999999-9999-9999-9999-999999999992",
            "skill_name": "SQL",
            "canonical_name": "sql",
            "skill_type": "technical",
            "confidence": 0.9700,
            "evidence_text": "SQL mentioned in CV and project experience.",
        },
    ]

    with patch(
        "backend.services.candidate_profiles.get_candidate_profile",
        return_value=candidate,
    ) as mock_get_candidate_profile, patch(
        "backend.services.candidate_profiles.get_candidate_skills",
        return_value=skills,
    ) as mock_get_candidate_skills:
        result = build_candidate_profile(
            "33333333-3333-3333-3333-333333333331",
        )

    assert result == {
        "candidate": candidate,
        "skills": skills,
    }
    mock_get_candidate_profile.assert_called_once_with(
        "33333333-3333-3333-3333-333333333331",
    )
    mock_get_candidate_skills.assert_called_once_with(
        "33333333-3333-3333-3333-333333333331",
    )


def test_build_candidate_profile_passes_candidate_id_to_both_helpers() -> None:
    """
    Verify that the same candidate ID is passed through to both helper calls.

    Notes
    -----
    - This test focuses on the call contract between the service layer and the
      lower-level DB helpers.
    - It helps catch mistakes where the service ignores or alters the supplied
      candidate ID.

    In plain language:

    - call the service with a known candidate ID
    - confirm both helper calls used that same ID
    """

    candidate_id = "33333333-3333-3333-3333-333333333331"

    with patch(
        "backend.services.candidate_profiles.get_candidate_profile",
        return_value={"candidate_id": candidate_id},
    ) as mock_get_candidate_profile, patch(
        "backend.services.candidate_profiles.get_candidate_skills",
        return_value=[],
    ) as mock_get_candidate_skills:
        build_candidate_profile(candidate_id)

    mock_get_candidate_profile.assert_called_once_with(candidate_id)
    mock_get_candidate_skills.assert_called_once_with(candidate_id)
