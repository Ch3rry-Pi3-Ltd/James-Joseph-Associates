"""
Company read helpers for the intelligence backend.

This module contains small database query helpers for reading canonical company
data from Postgres.
"""

from typing import Any

from backend.db.connection import postgres_connection


def list_canonical_company_records() -> list[dict[str, Any]]:
    """Return canonical companies with bounded, content-free provenance."""

    query = """
        select
            c.id::text as company_id,
            trim(c.name) as name,
            c.domain,
            c.website_url,
            c.linkedin_url,
            coalesce(
                array_remove(array_agg(distinct sr.source_system), null),
                array[]::text[]
            ) as source_systems,
            coalesce(
                array_remove(array_agg(distinct sr.source_record_type), null),
                array[]::text[]
            ) as source_record_types,
            c.updated_at
        from companies c
        left join source_record_links srl
          on srl.company_id = c.id
        left join source_records sr
          on sr.id = srl.source_record_id
        where nullif(trim(c.name), '') is not null
        group by
            c.id,
            c.name,
            c.domain,
            c.website_url,
            c.linkedin_url,
            c.updated_at
        order by lower(trim(c.name)), trim(c.name), c.id
    """

    with postgres_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(query)
            rows = cursor.fetchall()

    return [dict(row) for row in rows]


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
        select company_name as name
        from (
            select distinct trim(c.name) as company_name
            from companies c
            where nullif(trim(c.name), '') is not null
        ) canonical_companies
        order by lower(company_name), company_name
    """

    with postgres_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(query)
            rows = cursor.fetchall()

    return [str(row["name"]) for row in rows]


__all__ = ["list_canonical_company_names", "list_canonical_company_records"]
