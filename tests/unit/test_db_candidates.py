"""
Unit tests for candidate database read helpers.

This module tests the small candidate query helper in `backend.db.candidates`.

It gives the rest of the repository a stable way to check:

- the candidate helper returns `None` when no row is found
- the candidate helper returns a plain dictionary when a row is found
- the SQL helper passes the provided candidate ID into the query parameters
- the helper can be tested without opening a real database connection
- the mocking setup used by these tests is understandable to future readers

Keeping these tests small makes the database access layer easier to trust
because:

- query helpers are easier to debug when tested in isolation
- route handlers do not need to be the first place where SQL issues are found
- tests can validate result-shaping without needing a live Supabase database
- the backend can grow query modules one small slice at a time

In plain language:

- this module answers the question:

    "Does the candidate DB helper behave correctly?"

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
- we replace `backend.db.candidates.postgres_connection`
- we control what the fake cursor returns from `fetchone()`
- we inspect whether `execute(...)` was called correctly
"""

from unittest.mock import MagicMock, patch

from backend.db.candidates import get_candidate_profile


def test_get_candidate_profile_returns_none_when_row_is_missing() -> None:
    """
    Verify that the helper returns `None` when the candidate does not exist.

    Notes
    -----
    - `cursor.fetchone()` returns `None` when no SQL row matches the query.
    - The helper should pass that through as `None` rather than raising an
      error or returning an unexpected shape.
    - This keeps calling code simple and explicit.

    In plain language:

    - pretend the database found no candidate
    - call the helper
    - confirm the result is `None`
    """

    # `MagicMock()` gives us a fake object that can pretend to be a real
    # database cursor.
    #   - We can tell it what should happen when the code calls methods such as
    #     `fetchone()`.
    mock_cursor = MagicMock()
    mock_cursor.fetchone.return_value = None

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
    # `backend.db.candidates`.
    #
    # Important detail:
    #   - We patch `backend.db.candidates.postgres_connection`
    #   - not `backend.db.connection.postgres_connection`
    #
    # because the function under test imports the helper into its own module
    # namespace. The patch must therefore target the name as `candidates.py`
    # sees it.
    with patch(
        "backend.db.candidates.postgres_connection",
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

        result = get_candidate_profile(
            "33333333-3333-3333-3333-333333333331",
        )

    assert result is None


def test_get_candidate_profile_returns_dictionary_when_row_exists() -> None:
    """
    Verify that the helper returns a plain dictionary when a candidate is found.

    Notes
    -----
    - The connection helper uses `dict_row`, so `fetchone()` returns a
      dictionary-like row object.
    - The helper should convert that row into a normal Python `dict`.
    - This gives later service or route code a predictable result shape.

    In plain language:

    - pretend the database returned one candidate row
    - call the helper
    - confirm the result is a normal dictionary
    """

    # This fake row mirrors the kind of dictionary-like data that psycopg can
    # return when the connection uses `dict_row`
    mock_row = {
        "candidate_id": "33333333-3333-3333-3333-333333333331",
        "person_id": "22222222-2222-2222-2222-222222222221",
        "full_name": "Sarah Jones",
        "first_name": "Sarah",
        "last_name": "Jones",
        "primary_email": "sarah.jones@example.com",
        "primary_phone": "+447700900111",
        "linkedin_url": "https://linkedin.com/in/sarah-jones",
        "location": "London, UK",
        "headline": "Senior Data Engineer",
        "summary": "Prototype candidate person record.",
        "current_title": "Senior Data Engineer",
        "candidate_status": "active",
        "availability_status": "open_to_move",
        "salary_expectation": 95000.00,
        "notice_period": "1 month",
        "last_contacted_at": "2026-04-15T12:00:00+00:00",
        "resume_updated_at": "2026-04-20T12:00:00+00:00",
        "current_company_id": "11111111-1111-1111-1111-111111111111",
        "current_company_name": "Acme Hiring Ltd",
    }

    # Fake cursor:
    #   - when the helper calls `fetchone()`
    #   - return the fake row above
    mock_cursor = MagicMock()
    mock_cursor.fetchone.return_value = mock_row

    # Fake connection:
    #   - when the helper enters `with connection.cursor() as cursor:`
    #   - hand back the fake cursor
    mock_connection = MagicMock()
    mock_connection.cursor.return_value.__enter__.return_value = mock_cursor

    with patch(
        "backend.db.candidates.postgres_connection",
    ) as mock_postgres_connection:
        mock_postgres_connection.return_value.__enter__.return_value = (
            mock_connection
        )

        result = get_candidate_profile(
            "33333333-3333-3333-3333-333333333331",
        )

    assert result == mock_row
    assert isinstance(result, dict)
    assert result["full_name"] == "Sarah Jones"
    assert result["current_company_name"] == "Acme Hiring Ltd"


def test_get_candidate_profile_executes_query_with_candidate_id() -> None:
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
    #   - Returning `None` from `fetchone()` is enough here because this test is
    #     about the `execute(...)` call, not the returned row shape.
    mock_cursor = MagicMock()
    mock_cursor.fetchone.return_value = None

    mock_connection = MagicMock()
    mock_connection.cursor.return_value.__enter__.return_value = mock_cursor

    with patch(
        "backend.db.candidates.postgres_connection",
    ) as mock_postgres_connection:
        mock_postgres_connection.return_value.__enter__.return_value = (
            mock_connection
        )

        get_candidate_profile(candidate_id)

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
