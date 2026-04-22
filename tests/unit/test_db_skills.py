"""
Unit tests for skill database read helpers.

This module tests the small skill query helper in `backend.db.skills`.

It gives the rest of the repository a stable way to check:

- the skill helper returns an empty list when no rows are found
- the skill helper returns a list of plain dictionaries when rows are found
- the SQL helper passes the provided candidate ID into the query parameters
- the helper can be tested without opening a real database connection
- the mocking setup used by these tests is understandable to future readers

Keeping these tests small makes the database access layer easier to trust
because:

- query helpers are easier to debug when tested in isolation
- route handlers do not need to be the first place where SQL issues are found
- tests can validate list/result shaping without needing a live Supabase database
- the backend can grow query modules one small slice at a time

In plain language:

- this module answers the question:

    "Does the skill DB helper behave correctly?"

- it does not connect to a real database
- it does not call Supabase over the network
- it does not test FastAPI routes
- it only tests local Python behaviour around the query helper

Mocking approach
----------------
These tests use `unittest.mock` helpers:

- `MagicMock()` creates flexible fake Python objects whose methods and return
  values can be controlled inside the test.
- `patch(...)` temporarily replaces the real dependency used by the code under
  test with one of those fake objects.

In this module, that means:

- we do not open a real Postgres connection
- we replace `backend.db.skills.postgres_connection`
- we control what the fake cursor returns from `fetchall()`
- we inspect whether `execute(...)` was called correctly
"""

from unittest.mock import MagicMock, patch

from backend.db.skills import get_candidate_skills


def test_get_candidate_skills_returns_empty_list_when_rows_are_missing() -> None:
    """
    Verify that the helper returns an empty list when the candidate has no skills.

    Notes
    -----
    - `cursor.fetchall()` returns an empty list when no SQL rows match the query.
    - The helper should pass that through as an empty list rather than raising
      an error or returning an unexpected shape.
    - This keeps calling code simple and predictable.

    In plain language:

    - pretend the database found no candidate skills
    - call the helper
    - confirm the result is an empty list
    """

    # `MagicMock()` gives us a fake object that can pretend to be a real
    # database cursor.
    #   - We can tell it what should happen when the code calls methods such as
    #     `fetchall()`.
    mock_cursor = MagicMock()
    mock_cursor.fetchall.return_value = []

    # This fake object stands in for the database connection.
    #   - The real code does:
    #
    #       with connection.cursor() as cursor:
    #
    #   - To support that context-manager shape, the test sets:
    #
    #       connection.cursor.return_value.__enter__.return_value
    #
    #     to the fake cursor.
    mock_connection = MagicMock()
    mock_connection.cursor.return_value.__enter__.return_value = mock_cursor

    # `patch(...)` temporarily replaces the real object used inside
    # `backend.db.skills`.
    #
    # Important detail:
    #   - We patch `backend.db.skills.postgres_connection`
    #   - not `backend.db.connection.postgres_connection`
    #
    # because the function under test imports the helper into its own module
    # namespace. The patch must therefore target the name as `skills.py`
    # sees it.
    with patch(
        "backend.db.skills.postgres_connection",
    ) as mock_postgres_connection:
        # The production code uses:
        #
        #     with postgres_connection() as connection:
        #
        # so the patched object also needs to behave like a context manager.
        # This line makes the `with ... as connection:` block receive our fake
        # connection object instead of opening a real database connection.
        mock_postgres_connection.return_value.__enter__.return_value = (
            mock_connection
        )

        result = get_candidate_skills(
            "33333333-3333-3333-3333-333333333331",
        )

    assert result == []
    assert isinstance(result, list)


def test_get_candidate_skills_returns_list_of_dictionaries_when_rows_exist() -> None:
    """
    Verify that the helper returns plain dictionaries when skill rows are found.

    Notes
    -----
    - The connection helper uses `dict_row`, so `fetchall()` returns
      dictionary-like row objects.
    - The helper should convert those rows into normal Python dictionaries.
    - This gives later service or route code a predictable result shape.

    In plain language:

    - pretend the database returned two skill rows
    - call the helper
    - confirm the result is a list of normal dictionaries
    """

    # These fake rows mirror the kind of dictionary-like data that psycopg can
    # return when the connection uses `dict_row`.
    mock_rows = [
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

    # Fake cursor:
    #   - when the helper calls `fetchall()`
    #   - return the fake rows above
    mock_cursor = MagicMock()
    mock_cursor.fetchall.return_value = mock_rows

    # Fake connection:
    #   - when the helper enters `with connection.cursor() as cursor:`
    #   - hand back the fake cursor
    mock_connection = MagicMock()
    mock_connection.cursor.return_value.__enter__.return_value = mock_cursor

    with patch(
        "backend.db.skills.postgres_connection",
    ) as mock_postgres_connection:
        mock_postgres_connection.return_value.__enter__.return_value = (
            mock_connection
        )

        result = get_candidate_skills(
            "33333333-3333-3333-3333-333333333331",
        )

    assert result == mock_rows
    assert isinstance(result, list)
    assert isinstance(result[0], dict)
    assert result[0]["skill_name"] == "Python"
    assert result[1]["skill_name"] == "SQL"


def test_get_candidate_skills_executes_query_with_candidate_id() -> None:
    """
    Verify that the helper passes the supplied candidate ID into the query.

    Notes
    -----
    - This test does not try to validate the entire SQL string.
    - It checks the higher-value contract:
      - SQL was executed
      - the candidate ID was passed as a parameter
    - That helps catch mistakes where the helper ignores the function argument.

    In plain language:

    - call the helper with a known candidate ID
    - check the SQL execute call used that same ID
    """

    candidate_id = "33333333-3333-3333-3333-333333333331"

    # Fake cursor used only so the helper can run without touching a real
    # database.
    #   - Returning an empty list from `fetchall()` is enough here because this
    #     test is about the `execute(...)` call, not the returned row shape.
    mock_cursor = MagicMock()
    mock_cursor.fetchall.return_value = []

    mock_connection = MagicMock()
    mock_connection.cursor.return_value.__enter__.return_value = mock_cursor

    with patch(
        "backend.db.skills.postgres_connection",
    ) as mock_postgres_connection:
        mock_postgres_connection.return_value.__enter__.return_value = (
            mock_connection
        )

        get_candidate_skills(candidate_id)

    # This proves the helper actually attempted to execute SQL once.
    mock_cursor.execute.assert_called_once()

    execute_call_args = mock_cursor.execute.call_args
    _, execute_kwargs = execute_call_args

    # `cursor.execute()` receives:
    #   - the SQL query string
    #   - a parameter dictionary containing `candidate_id`
    #
    # This test focuses on the parameter contract rather than the full SQL text.
    assert execute_kwargs == {}
    assert execute_call_args.args[1] == {
        "candidate_id": candidate_id,
    }
