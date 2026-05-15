"""
Unit tests for Dropbox OAuth database helpers.

This module tests the small persistence helpers in `backend.db.dropbox_oauth`.

It gives the rest of the repository a stable way to check:

- the Dropbox OAuth connection can be saved without touching a real database
- the saved SQL parameters are shaped correctly
- the helper updates an existing connection record through an upsert pattern
- the helper reads back one stored Dropbox OAuth connection correctly
- invalid or missing Dropbox account identifiers fail clearly before SQL runs
"""

from unittest.mock import MagicMock, patch

import pytest

from backend.db.dropbox_oauth import (
    get_dropbox_oauth_connection,
    save_dropbox_oauth_connection,
)
from backend.services.dropbox_oauth import DropboxTokenSet


def build_token_set(
    *,
    account_id: str | None = "dbid:AAExample",
) -> DropboxTokenSet:
    """
    Build a small fake `DropboxTokenSet` for DB-helper tests.

    Example
    -------
    Calling:

        build_token_set(account_id="dbid:AAExample")

    returns a realistic-enough normalized token object for the DB helper to
    shape into SQL parameters.
    """

    return DropboxTokenSet(
        access_token="dropbox-access-token",
        token_type="bearer",
        expires_in=14400,
        refresh_token="dropbox-refresh-token",
        scope="account_info.read files.metadata.read",
        account_id=account_id,
        raw_payload={
            "account_id": account_id,
        },
    )


def test_save_dropbox_oauth_connection_returns_saved_row_dictionary() -> None:
    """
    Verify that the save helper returns a plain dictionary when the row is
    saved.

    Example
    -------
    We simulate Postgres returning the `returning ...` row from the upsert and
    confirm the helper passes that row back as a normal dictionary.
    """

    token_set = build_token_set()

    saved_row = {
        "id": "11111111-1111-1111-1111-111111111111",
        "access_token": "dropbox-access-token",
        "refresh_token": "dropbox-refresh-token",
        "token_type": "bearer",
        "expires_in_seconds": 14400,
        "obtained_at": "2026-05-15T12:00:00+00:00",
        "scope": "account_info.read files.metadata.read",
        "dropbox_account_id": "dbid:AAExample",
        "created_at": "2026-05-15T12:00:00+00:00",
        "updated_at": "2026-05-15T12:00:00+00:00",
    }

    mock_cursor = MagicMock()
    mock_cursor.fetchone.return_value = saved_row

    mock_connection = MagicMock()
    mock_connection.cursor.return_value.__enter__.return_value = mock_cursor

    with patch(
        "backend.db.dropbox_oauth.postgres_connection",
    ) as mock_postgres_connection:
        mock_postgres_connection.return_value.__enter__.return_value = mock_connection

        result = save_dropbox_oauth_connection(token_set)

    assert result == saved_row
    assert isinstance(result, dict)
    assert result["dropbox_account_id"] == "dbid:AAExample"
    mock_connection.commit.assert_called_once()


def test_save_dropbox_oauth_connection_executes_upsert_with_expected_parameters() -> None:
    """
    Verify that the save helper sends the expected SQL parameters to
    `execute()`.

    Example
    -------
    This test checks the higher-value contract:

    - the helper targeted the correct table
    - the helper used the expected upsert pattern
    - the important stored values were shaped correctly
    """

    token_set = build_token_set()

    mock_cursor = MagicMock()
    mock_cursor.fetchone.return_value = {
        "id": "11111111-1111-1111-1111-111111111111",
        "access_token": "dropbox-access-token",
        "refresh_token": "dropbox-refresh-token",
        "token_type": "bearer",
        "expires_in_seconds": 14400,
        "obtained_at": "2026-05-15T12:00:00+00:00",
        "scope": "account_info.read files.metadata.read",
        "dropbox_account_id": "dbid:AAExample",
        "created_at": "2026-05-15T12:00:00+00:00",
        "updated_at": "2026-05-15T12:00:00+00:00",
    }

    mock_connection = MagicMock()
    mock_connection.cursor.return_value.__enter__.return_value = mock_cursor

    with patch(
        "backend.db.dropbox_oauth.postgres_connection",
    ) as mock_postgres_connection:
        mock_postgres_connection.return_value.__enter__.return_value = mock_connection

        save_dropbox_oauth_connection(token_set)

    mock_cursor.execute.assert_called_once()

    execute_call_args = mock_cursor.execute.call_args
    sql_query = execute_call_args.args[0]
    params = execute_call_args.args[1]

    assert "insert into dropbox_oauth_connections" in sql_query.lower()
    assert "on conflict (dropbox_account_id)" in sql_query.lower()
    assert params["access_token"] == "dropbox-access-token"
    assert params["refresh_token"] == "dropbox-refresh-token"
    assert params["token_type"] == "bearer"
    assert params["expires_in_seconds"] == 14400
    assert params["scope"] == "account_info.read files.metadata.read"
    assert params["dropbox_account_id"] == "dbid:AAExample"
    assert params["obtained_at"] is not None


def test_save_dropbox_oauth_connection_raises_when_account_id_is_missing() -> None:
    """
    Verify that the save helper fails clearly when the token set has no usable
    Dropbox account identifier.

    Example
    -------
    If the normalized token set does not carry `account_id`, the helper should
    reject it before any SQL is attempted.
    """

    token_set = build_token_set(account_id=None)

    with patch("backend.db.dropbox_oauth.postgres_connection") as mock_connection:
        with pytest.raises(ValueError) as exc_info:
            save_dropbox_oauth_connection(token_set)

    assert str(exc_info.value) == (
        "Dropbox token set did not include a usable account identifier."
    )
    mock_connection.assert_not_called()


def test_get_dropbox_oauth_connection_returns_dictionary_when_row_exists() -> None:
    """
    Verify that the read helper returns a plain dictionary when a stored
    connection exists.

    Example
    -------
    We simulate Postgres returning one stored connection row and confirm the
    helper returns that row unchanged as a plain dictionary.
    """

    stored_row = {
        "id": "11111111-1111-1111-1111-111111111111",
        "access_token": "dropbox-access-token",
        "refresh_token": "dropbox-refresh-token",
        "token_type": "bearer",
        "expires_in_seconds": 14400,
        "obtained_at": "2026-05-15T12:00:00+00:00",
        "scope": "account_info.read files.metadata.read",
        "dropbox_account_id": "dbid:AAExample",
        "created_at": "2026-05-15T12:00:00+00:00",
        "updated_at": "2026-05-15T12:00:00+00:00",
    }

    mock_cursor = MagicMock()
    mock_cursor.fetchone.return_value = stored_row

    mock_connection = MagicMock()
    mock_connection.cursor.return_value.__enter__.return_value = mock_cursor

    with patch(
        "backend.db.dropbox_oauth.postgres_connection",
    ) as mock_postgres_connection:
        mock_postgres_connection.return_value.__enter__.return_value = mock_connection

        result = get_dropbox_oauth_connection("dbid:AAExample")

    assert result == stored_row
    assert isinstance(result, dict)
    assert result["dropbox_account_id"] == "dbid:AAExample"
