"""
Database helpers for storing Dropbox OAuth connection details.

This module contains the first small persistence helpers for the Dropbox
integration.

It gives the rest of the repository a stable way to talk about:

- saving the current Dropbox OAuth connection
- reading the current Dropbox OAuth connection
- keeping Dropbox token persistence logic out of route handlers
- matching the same direct-SQL helper style already used for JobAdder

Why this module exists
----------------------
We can build the Dropbox approval URL, receive the callback, exchange a
one-time authorization code for tokens, and refresh short-lived access tokens.
But without persistence, those tokens would be lost as soon as the process
ended or the app restarted.

Keeping this logic in `backend.db` is consistent with the rest of the backend,
where direct Postgres reads and writes already live in small helper modules.

Example
-------
Typical usage in the rest of the backend looks like:

    saved_connection = save_dropbox_oauth_connection(token_set)
    stored_connection = get_dropbox_oauth_connection(
        saved_connection["dropbox_account_id"]
    )

Important note
--------------
This module assumes a table exists for storing one Dropbox OAuth connection per
connected Dropbox account.

For now, this code expects a table shaped roughly like:

    dropbox_oauth_connections
    - id
    - access_token
    - refresh_token
    - token_type
    - expires_in_seconds
    - obtained_at
    - scope
    - dropbox_account_id
    - created_at
    - updated_at
"""

from datetime import datetime, timezone

from backend.db.connection import postgres_connection
from backend.services.dropbox_oauth import DropboxTokenSet


def save_dropbox_oauth_connection(token_set: DropboxTokenSet) -> dict[str, object]:
    """
    Insert or replace the current Dropbox OAuth connection record.

    Parameters
    ----------
    token_set : DropboxTokenSet
        Normalized token response returned by the Dropbox token-exchange step.

    Returns
    -------
    dict[str, object]
        Plain dictionary representing the saved connection row.

    Notes
    -----
    - This helper currently stores one logical Dropbox connection record per
      Dropbox account.
    - The `dropbox_account_id` field is treated as the stable natural key for
      the connected Dropbox account.
    - The SQL uses an upsert so reconnecting the same Dropbox account updates
      the existing record instead of creating duplicates.

    Example
    -------
    Calling:

        save_dropbox_oauth_connection(token_set)

    saves the latest short-lived access token and long-lived refresh token for
    the connected Dropbox account.
    """
    # Capture the moment this token set became "our current stored truth".
    #
    # This timestamp matters because `expires_in` is only a duration. Without
    # also storing when the token was obtained, later code would have no way to
    # decide whether the short-lived access token is still safe to use.
    obtained_at = datetime.now(timezone.utc)
    dropbox_account_id = token_set.account_id

    if not isinstance(dropbox_account_id, str) or dropbox_account_id.strip() == "":
        raise ValueError(
            "Dropbox token set did not include a usable account identifier."
        )

    # Use one upsert statement rather than separate "select then insert/update"
    # logic.
    #
    # The intuition is the same as the JobAdder path:
    # - one Dropbox account should map to one active stored OAuth connection row
    # - reconnecting that same Dropbox account should refresh the stored tokens
    #   rather than creating duplicates
    # - one SQL statement keeps the behaviour atomic and easier to reason about
    sql = """
        insert into dropbox_oauth_connections (
            access_token,
            refresh_token,
            token_type,
            expires_in_seconds,
            obtained_at,
            scope,
            dropbox_account_id
        )
        values (
            %(access_token)s,
            %(refresh_token)s,
            %(token_type)s,
            %(expires_in_seconds)s,
            %(obtained_at)s,
            %(scope)s,
            %(dropbox_account_id)s
        )
        on conflict (dropbox_account_id)
        do update set
            access_token = excluded.access_token,
            refresh_token = excluded.refresh_token,
            token_type = excluded.token_type,
            expires_in_seconds = excluded.expires_in_seconds,
            obtained_at = excluded.obtained_at,
            scope = excluded.scope,
            updated_at = now()
        returning
            id,
            access_token,
            refresh_token,
            token_type,
            expires_in_seconds,
            obtained_at,
            scope,
            dropbox_account_id,
            created_at,
            updated_at
    """

    # Keep the SQL parameter mapping explicit so each stored column is easy to
    # trace back to its Python source.
    #
    # This slight verbosity is intentional. It makes later debugging much
    # easier because the storage contract is obvious at a glance.
    params = {
        "access_token": token_set.access_token,
        "refresh_token": token_set.refresh_token,
        "token_type": token_set.token_type,
        "expires_in_seconds": token_set.expires_in,
        "obtained_at": obtained_at,
        "scope": token_set.scope,
        "dropbox_account_id": dropbox_account_id,
    }

    # Execute the write in one transaction and fetch the returned row so callers
    # immediately receive the exact persisted shape, including database-managed
    # fields such as `id`, `created_at`, and `updated_at`.
    with postgres_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(sql, params)
            row = cursor.fetchone()

        connection.commit()

    # A missing returned row here indicates a write-path problem, not a
    # "connection not found" situation. Treat it as a real runtime failure so
    # callers do not mistake a broken persistence path for a successful save.
    if row is None:
        raise RuntimeError("Failed to save Dropbox OAuth connection.")

    return dict(row)


def get_dropbox_oauth_connection(
    dropbox_account_id: str,
) -> dict[str, object] | None:
    """
    Fetch the stored Dropbox OAuth connection for one Dropbox account.

    Parameters
    ----------
    dropbox_account_id : str
        Dropbox account identifier returned by the token response.

    Returns
    -------
    dict[str, object] | None
        Plain dictionary representing the stored connection row, or `None` if
        no record exists.

    Example
    -------
    Calling:

        get_dropbox_oauth_connection("dbid:AAExample")

    returns either:

    - a plain dictionary containing the stored row for that Dropbox account
    - or `None` when no such connection has been saved yet
    """
    # Keep the read query intentionally small and explicit.
    #
    # This helper is not trying to be a general Dropbox query surface. Its job
    # is simply to fetch the one stored connection row for a known Dropbox
    # account ID.
    sql = """
        select
            id,
            access_token,
            refresh_token,
            token_type,
            expires_in_seconds,
            obtained_at,
            scope,
            dropbox_account_id,
            created_at,
            updated_at
        from dropbox_oauth_connections
        where dropbox_account_id = %(dropbox_account_id)s
    """

    params = {
        "dropbox_account_id": dropbox_account_id,
    }

    # Execute one simple lookup and fetch at most one row.
    #
    # Because `dropbox_account_id` is treated as a natural key, callers expect
    # either:
    # - one row
    # - or no row
    with postgres_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(sql, params)
            row = cursor.fetchone()

    # Return `None` rather than raising when nothing is found.
    #
    # That keeps the helper easy to compose with higher layers that may want to
    # decide for themselves whether "missing connection" should become:
    # - a 404 response
    # - a reconnect prompt
    # - or some other flow
    if row is None:
        return None

    return dict(row)


__all__ = [
    "get_dropbox_oauth_connection",
    "save_dropbox_oauth_connection",
]
