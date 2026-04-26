"""
Unit tests for JobAdder OAuth database helpers.

This module tests the small persistence helpers in `backend.db.jobadder_oauth`.

It gives the rest of the repository a stable way to check:

- the JobAdder OAuth connection can be saved without touching a real database
- the saved SQL parameters are shaped correctly
- the helper updates an existing connection record through an upsert pattern
- the helper reads back one stored JobAdder OAuth connection correctly
- the helper returns `None` when no stored connection exists
- invalid or missing JobAdder account identifiers fail clearly before SQL runs

Keeping these tests small makes the persistence layer easier to trust because:

- route handlers and services do not need to be the first place where SQL
  persistence bugs are found
- tests can validate parameter shaping without a live Supabase/Postgres instance
- the backend can grow the JobAdder integration one small slice at a time
- token storage logic stays consistent with the existing DB-helper testing style

In plain language:

- this module answers the question:

    "Do the JobAdder OAuth DB helpers save and fetch connection records correctly?"

- it does not call the real database
- it does not call JobAdder
- it does not require a live Supabase project
- it only tests local Python behaviour around the DB helper functions
"""

from unittest.mock import MagicMock, patch

import pytest

from backend.db.jobadder_oauth import (
    get_jobadder_oauth_connection,
    save_jobadder_oauth_connection,
)
from backend.services.jobadder_oauth import JobAdderTokenSet


def build_token_set(
    *,
    account: int | str | None = 123456,
    api_url: str | None = "https://api.jobadder.com",
    instance: str | None = "jobadder-prod-au",
) -> JobAdderTokenSet:
    """
    Build a small fake `JobAdderTokenSet` for DB-helper tests.

    Parameters
    ----------
    account : int | str | None
        Fake JobAdder account value placed into the raw payload.

    api_url : str | None
        Fake JobAdder API base URL placed into the raw payload.

    instance : str | None
        Fake JobAdder instance value placed into the raw payload.

    Returns
    -------
    JobAdderTokenSet
        Fake token set suitable for testing DB persistence behaviour.

    Notes
    -----
    - These tests do not care about live JobAdder behaviour.
    - They only need a realistic enough token object for the DB helper to read.

    In plain language:

    - create one fake token object
    - reuse it in the tests below
    """

    return JobAdderTokenSet(
        access_token="jobadder-access-token",
        token_type="Bearer",
        expires_in=3600,
        refresh_token="jobadder-refresh-token",
        scope="read write offline_access",
        raw_payload={
            "api": api_url,
            "instance": instance,
            "account": account,
        },
    )


def test_save_jobadder_oauth_connection_returns_saved_row_dictionary() -> None:
    """
    Verify that the save helper returns a plain dictionary when the row is saved.

    In plain language:

    - pretend the database accepted the upsert
    - return one saved row
    - confirm the helper returns that row as a normal dictionary
    """

    token_set = build_token_set()

    saved_row = {
        "id": "11111111-1111-1111-1111-111111111111",
        "access_token": "jobadder-access-token",
        "refresh_token": "jobadder-refresh-token",
        "token_type": "Bearer",
        "expires_in_seconds": 3600,
        "obtained_at": "2026-04-26T12:00:00+00:00",
        "api_url": "https://api.jobadder.com",
        "jobadder_instance": "jobadder-prod-au",
        "jobadder_account": 123456,
        "created_at": "2026-04-26T12:00:00+00:00",
        "updated_at": "2026-04-26T12:00:00+00:00",
    }

    # Fake cursor:
    #   - this stands in for the real psycopg cursor object
    #   - when the helper calls `fetchone()` after the `returning ...` SQL
    #     clause, we want it to behave as if Postgres returned the saved row
    mock_cursor = MagicMock()
    mock_cursor.fetchone.return_value = saved_row

    # Fake connection:
    #   - the production code uses:
    #
    #       with postgres_connection() as connection:
    #           with connection.cursor() as cursor:
    #
    #   - so the fake connection must also support the cursor context-manager
    #     chain and yield our fake cursor at the end
    mock_connection = MagicMock()
    mock_connection.cursor.return_value.__enter__.return_value = mock_cursor

    with patch(
        "backend.db.jobadder_oauth.postgres_connection",
    ) as mock_postgres_connection:
        # Patch the name exactly as `backend.db.jobadder_oauth` sees it.
        #
        # The helper under test does:
        #
        #     with postgres_connection() as connection:
        #
        # so the patched object needs to behave like a context manager too.
        # This line makes the `with ... as connection:` block receive our fake
        # connection object instead of opening a real Postgres connection.
        mock_postgres_connection.return_value.__enter__.return_value = (
            mock_connection
        )

        result = save_jobadder_oauth_connection(token_set)

    assert result == saved_row
    assert isinstance(result, dict)
    assert result["jobadder_account"] == 123456
    assert result["refresh_token"] == "jobadder-refresh-token"


def test_save_jobadder_oauth_connection_executes_upsert_with_expected_parameters() -> None:
    """
    Verify that the save helper sends the expected SQL parameters to `execute()`.

    Notes
    -----
    - This test does not try to assert the full SQL string exactly.
    - It checks the higher-value contract:
      - SQL was executed
      - the key stored values were passed correctly
    - That keeps the test readable while still proving the important behaviour.

    In plain language:

    - save a fake token set
    - inspect the SQL call
    - confirm the important parameter values are correct
    """

    token_set = build_token_set(account="123456")

    mock_cursor = MagicMock()
    mock_cursor.fetchone.return_value = {
        "id": "11111111-1111-1111-1111-111111111111",
        "access_token": "jobadder-access-token",
        "refresh_token": "jobadder-refresh-token",
        "token_type": "Bearer",
        "expires_in_seconds": 3600,
        "obtained_at": "2026-04-26T12:00:00+00:00",
        "api_url": "https://api.jobadder.com",
        "jobadder_instance": "jobadder-prod-au",
        "jobadder_account": 123456,
        "created_at": "2026-04-26T12:00:00+00:00",
        "updated_at": "2026-04-26T12:00:00+00:00",
    }

    mock_connection = MagicMock()
    mock_connection.cursor.return_value.__enter__.return_value = mock_cursor

    with patch(
        "backend.db.jobadder_oauth.postgres_connection",
    ) as mock_postgres_connection:
        mock_postgres_connection.return_value.__enter__.return_value = (
            mock_connection
        )

        save_jobadder_oauth_connection(token_set)

    # Prove that one SQL statement was sent.
    #   - This confirms the helper actually attempted the write.
    mock_cursor.execute.assert_called_once()

    execute_call_args = mock_cursor.execute.call_args
    sql_query = execute_call_args.args[0]
    params = execute_call_args.args[1]

    # Check the broad SQL contract rather than every line.
    #   - We care that this is the expected table and upsert pattern.
    assert "insert into jobadder_oauth_connections" in sql_query.lower()
    assert "on conflict (jobadder_account)" in sql_query.lower()

    # Check the important values that should be persisted.
    #   - These assertions prove the helper translated the token object into
    #     the right SQL parameter dictionary.
    assert params["access_token"] == "jobadder-access-token"
    assert params["refresh_token"] == "jobadder-refresh-token"
    assert params["token_type"] == "Bearer"
    assert params["expires_in_seconds"] == 3600
    assert params["api_url"] == "https://api.jobadder.com"
    assert params["jobadder_instance"] == "jobadder-prod-au"
    assert params["jobadder_account"] == 123456

    # `obtained_at` is generated at runtime, so we do not compare an exact
    # timestamp string here.
    assert params["obtained_at"] is not None


def test_save_jobadder_oauth_connection_raises_when_jobadder_account_is_missing() -> None:
    """
    Verify that the save helper fails clearly when the token set has no usable
    JobAdder account identifier.

    Notes
    -----
    - The helper should reject this before SQL runs.
    - The JobAdder account acts as the natural key for the stored connection.

    In plain language:

    - give the helper a token set with no account
    - confirm it raises a clear error
    - confirm no database call was attempted
    """

    token_set = build_token_set(account=None)

    with patch("backend.db.jobadder_oauth.postgres_connection") as mock_connection:
        with pytest.raises(ValueError) as exc_info:
            save_jobadder_oauth_connection(token_set)

    assert str(exc_info.value) == (
        "JobAdder token set did not include a usable account identifier."
    )
    mock_connection.assert_not_called()


def test_save_jobadder_oauth_connection_raises_when_jobadder_account_is_not_numeric() -> None:
    """
    Verify that the save helper rejects a non-numeric account value cleanly.

    In plain language:

    - give the helper an invalid account string
    - confirm it raises the same clear validation error
    """

    token_set = build_token_set(account="not-a-number")

    with patch("backend.db.jobadder_oauth.postgres_connection") as mock_connection:
        with pytest.raises(ValueError) as exc_info:
            save_jobadder_oauth_connection(token_set)

    assert str(exc_info.value) == (
        "JobAdder token set did not include a usable account identifier."
    )
    mock_connection.assert_not_called()


def test_save_jobadder_oauth_connection_raises_when_database_returns_no_row() -> None:
    """
    Verify that the save helper fails clearly if the database did not return the
    saved row.

    Notes
    -----
    - The SQL uses `returning ...`, so a missing row should be treated as an
      unexpected failure.
    - This protects the calling code from silently thinking the save worked.

    In plain language:

    - pretend the database saved nothing useful
    - confirm the helper raises a runtime error
    """

    token_set = build_token_set()

    mock_cursor = MagicMock()
    mock_cursor.fetchone.return_value = None

    mock_connection = MagicMock()
    mock_connection.cursor.return_value.__enter__.return_value = mock_cursor

    with patch(
        "backend.db.jobadder_oauth.postgres_connection",
    ) as mock_postgres_connection:
        mock_postgres_connection.return_value.__enter__.return_value = (
            mock_connection
        )

        with pytest.raises(RuntimeError) as exc_info:
            save_jobadder_oauth_connection(token_set)

    assert str(exc_info.value) == "Failed to save JobAdder OAuth connection."


def test_get_jobadder_oauth_connection_returns_none_when_row_is_missing() -> None:
    """
    Verify that the read helper returns `None` when no connection exists.

    In plain language:

    - pretend the database found nothing
    - call the helper
    - confirm the result is none
    """

    mock_cursor = MagicMock()
    mock_cursor.fetchone.return_value = None

    mock_connection = MagicMock()
    mock_connection.cursor.return_value.__enter__.return_value = mock_cursor

    with patch(
        "backend.db.jobadder_oauth.postgres_connection",
    ) as mock_postgres_connection:
        mock_postgres_connection.return_value.__enter__.return_value = (
            mock_connection
        )

        result = get_jobadder_oauth_connection(123456)

    assert result is None


def test_get_jobadder_oauth_connection_returns_dictionary_when_row_exists() -> None:
    """
    Verify that the read helper returns a plain dictionary when a stored
    connection exists.

    In plain language:

    - pretend the database returned one connection row
    - call the helper
    - confirm the result is a normal dictionary
    """

    stored_row = {
        "id": "11111111-1111-1111-1111-111111111111",
        "access_token": "jobadder-access-token",
        "refresh_token": "jobadder-refresh-token",
        "token_type": "Bearer",
        "expires_in_seconds": 3600,
        "obtained_at": "2026-04-26T12:00:00+00:00",
        "api_url": "https://api.jobadder.com",
        "jobadder_instance": "jobadder-prod-au",
        "jobadder_account": 123456,
        "created_at": "2026-04-26T12:00:00+00:00",
        "updated_at": "2026-04-26T12:00:00+00:00",
    }

    mock_cursor = MagicMock()
    mock_cursor.fetchone.return_value = stored_row

    mock_connection = MagicMock()
    mock_connection.cursor.return_value.__enter__.return_value = mock_cursor

    with patch(
        "backend.db.jobadder_oauth.postgres_connection",
    ) as mock_postgres_connection:
        mock_postgres_connection.return_value.__enter__.return_value = (
            mock_connection
        )

        result = get_jobadder_oauth_connection(123456)

    assert result == stored_row
    assert isinstance(result, dict)
    assert result["jobadder_account"] == 123456
    assert result["api_url"] == "https://api.jobadder.com"


def test_get_jobadder_oauth_connection_executes_query_with_jobadder_account() -> None:
    """
    Verify that the read helper passes the supplied JobAdder account into the
    SQL parameters.

    Notes
    -----
    - This test focuses on the parameter contract, not the exact full SQL text.
    - That is enough to prove the helper is querying for the requested account.

    In plain language:

    - call the helper with one account number
    - confirm the SQL received that same number
    """

    mock_cursor = MagicMock()
    mock_cursor.fetchone.return_value = None

    mock_connection = MagicMock()
    mock_connection.cursor.return_value.__enter__.return_value = mock_cursor

    with patch(
        "backend.db.jobadder_oauth.postgres_connection",
    ) as mock_postgres_connection:
        mock_postgres_connection.return_value.__enter__.return_value = (
            mock_connection
        )

        get_jobadder_oauth_connection(123456)

    mock_cursor.execute.assert_called_once()

    execute_call_args = mock_cursor.execute.call_args
    sql_query = execute_call_args.args[0]
    params = execute_call_args.args[1]

    assert "from jobadder_oauth_connections" in sql_query.lower()
    assert "where jobadder_account = %(jobadder_account)s" in sql_query.lower()
    assert params == {
        "jobadder_account": 123456,
    }
