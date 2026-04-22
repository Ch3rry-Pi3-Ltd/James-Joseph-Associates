"""
Postgres connection helpers for the intelligence backend.

This module gives the backend a small explicit place to open direct database
connections to the Supabase-hosted Postgres database.

It gives the rest of the repository a stable way to talk about:

- opening a Postgres connection
- validating that a database URL has been configured
- using dictionary-like row results
- closing connections reliably

Keeping this logic in one small module makes the project easier to grow because:

- settings stay in `backend.settings`
- route handlers do not need to know how to build connections
- future query modules can depend on one shared connection helper
- tests can later patch or replace this module cleanly

In plain language:

- this module answers the question:

    "How does the backend open a database connection?"

- it does not define SQL tables
- it does not contain business logic
- it does not run queries by itself
- it only opens and closes connections safely

Notes
-----
- This module uses `psycopg`.
- The backend connects directly to Postgres rather than through the Supabase
  dashboard UI.
- The connection string should come from `POSTGRES_URL` in environment
  variables, typically provided by the Supabase/Vercel setup.
- Rows are returned with `dict_row` so later query code can read columns by
  name instead of tuple position.

Important boundaries
--------------------
This module should not contain:

- route handlers
- schema definitions
- domain-specific query logic
- candidate/job matching logic
- LangGraph workflows
- LLM calls

Those concerns belong in separate modules that depend on this one.
"""

from collections.abc import Iterator
from contextlib import contextmanager

import psycopg
from psycopg.rows import dict_row

from backend.settings import get_settings


def get_postgres_connection() -> psycopg.Connection:
    """
    Open a new Postgres connection using the configured database URL.

    Returns
    -------
    psycopg.Connection
        Open psycopg connection configured to return dictionary-like rows.

    Raises
    ------
    RuntimeError
        If `POSTGRES_URL` has not been configured.

    Notes
    -----
    - This function opens a fresh connection each time it is called.
    - It does not cache or pool connections yet.
    - That is acceptable for the current prototype stage.
    - If connection pooling becomes necessary later, this module is the right 
      place to add it.

    In plain language:

    - read the configured database URL
    - fail clearly if it is missing
    - open a connection to Postgres
    - return the live connection object

    Example
    -------
    Open a direct connection and run a simple query:

        from backend.db.connection import get_postgres_connection

        connection = get_postgres_connection()

        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1 AS ok")
                row = cursor.fetchone()

            assert row["ok"] == 1
        finally:
            connection.close()
    """

    settings = get_settings()

    # Fail early with a clear message if the database URL has not been set.
    #   - This is easier to debug than letting psycopg fail with a less helpful
    #     low-level connection error.
    if not settings.postgres_url:
        msg = (
            "POSTGRES_URL is not configured. "
            "Set the database connection string before opening Postgres "
            "connections."
        )
        raise RuntimeError(msg)
    
    # `dict_row` means later query code can access results like:
    #
    #   row["candidate_id"]
    #   row["full_name"]
    #
    # instead of relying on tuple positions such as `row[0]`.
    return psycopg.connect(
        conninfo=settings.postgres_url,
        row_factory=dict_row,
    )


@contextmanager
def postgres_connection() -> Iterator[psycopg.Connection]:
    """
    Yield a Postgres connection and close it reliably afterwards.

    Yields
    ------
    psycopg.Connection
        Live Postgres connection for the duration of the context manager block.

    Notes
    -----
    - This is the safest default way to use connections in the current backend.
    - The caller does not need to remember to close the connection manually.
    - If an exception is raised inside the block, the connection is still
      closed in `finally`.

    Example
    -------
    Read rows inside a managed connection block:

        from backend.db.connection import postgres_connection

        with postgres_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1 AS ok")
                row = cursor.fetchone()

        assert row["ok"] == 1

    In plain language:

    - open a connection
    - hand it to the caller
    - always close it afterwards
    """

    connection = get_postgres_connection()

    try:
        yield connection
    finally:
        connection.close()

__all__ = [
    "get_postgres_connection",
    "postgres_connection",
]
