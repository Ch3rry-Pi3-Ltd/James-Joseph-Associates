"""
Company read helpers for the intelligence backend.

This module contains small database query helpers for reading canonical company
data from Postgres.
"""

from backend.db.connection import postgres_connection


def list_canonical_company_names() -> list[str]:
    """
    Return canonical company names in alphabetical order.

    Notes
    -----
    - Blank names are excluded.
    - The ordering is case-insensitive so the frontend can show one clean
      dropdown-style list.
    """

    query = """
        select distinct c.name
        from companies c
        where nullif(trim(c.name), '') is not null
        order by lower(c.name), c.name
    """

    with postgres_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(query)
            rows = cursor.fetchall()

    return [str(row["name"]) for row in rows]


__all__ = ["list_canonical_company_names"]
