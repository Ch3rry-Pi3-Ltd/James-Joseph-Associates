"""Read-only database usage metrics for controlled bulk operations."""

from __future__ import annotations

from backend.db.connection import postgres_connection


def get_database_size_bytes() -> int:
    """Return the allocated size of the current Postgres database."""

    with postgres_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                "select pg_database_size(current_database()) as size_bytes"
            )
            row = cursor.fetchone()
    return int(row["size_bytes"])


__all__ = ["get_database_size_bytes"]
