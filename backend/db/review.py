"""
Review overview read helpers for the intelligence backend.

This module collects a small cross-entity snapshot from the canonical Postgres
schema so operators can inspect what has already landed in Supabase.

It gives the rest of the repository a stable way to talk about:

- headline entity counts
- recent candidates
- recent jobs
- recent applications
- recent documents
- recent source records

Keeping this logic in one DB helper matters because:

- the API route can stay focused on HTTP concerns
- the frontend can read one compact overview payload
- future dashboard work can extend one place instead of scattering ad hoc SQL

In plain language:

- this module answers the question:

    "What is currently in the canonical database?"

- it does not write data
- it does not run matching logic
- it does not decide duplicate resolution
- it only returns a compact operator-facing snapshot
"""

from typing import Any

from backend.db.connection import postgres_connection


def get_review_overview(limit: int = 10) -> dict[str, Any]:
    """
    Return one compact operator overview of the canonical database.

    Parameters
    ----------
    limit : int, default=10
        Maximum number of rows to return in each recent-activity list.

    Returns
    -------
    dict[str, Any]
        Overview payload containing:

        - `counts`
        - `recent_candidates`
        - `recent_jobs`
        - `recent_applications`
        - `recent_documents`
        - `recent_source_records`
        - `document_type_counts`
        - `source_system_counts`

    Notes
    -----
    - The overview intentionally returns small slices rather than full tables.
    - This keeps the first review page fast and readable.
    - Each recent list is ordered by the most recently changed rows first.
    - This helper is deliberately broad but shallow.
    - It is meant for operator inspection, not for full-table export.

    Example
    -------
    Read the first overview slice for the UI:

        from backend.db.review import get_review_overview

        overview = get_review_overview(limit=5)
        print(overview["counts"]["jobs"])
        print(overview["recent_jobs"][0]["title"])

    A typical result shape looks like:

        {
            "counts": {
                "people": 5,
                "candidates": 5,
                "jobs": 2,
                "applications": 1,
                "documents": 6,
                "source_records": 19
            },
            "recent_candidates": [...],
            "recent_jobs": [...],
            "recent_applications": [...],
            "recent_documents": [...],
            "recent_source_records": [...],
            "document_type_counts": [...],
            "source_system_counts": [...]
        }
    """

    counts_query = """
        SELECT
            (SELECT COUNT(*)::int FROM people) AS people,
            (SELECT COUNT(*)::int FROM candidates) AS candidates,
            (SELECT COUNT(*)::int FROM jobs) AS jobs,
            (SELECT COUNT(*)::int FROM applications) AS applications,
            (SELECT COUNT(*)::int FROM documents) AS documents,
            (SELECT COUNT(*)::int FROM source_records) AS source_records
    """

    recent_candidates_query = """
        SELECT
            c.id AS candidate_id,
            p.full_name,
            c.current_title,
            c.candidate_status,
            co.name AS current_company_name,
            c.resume_updated_at,
            c.updated_at
        FROM candidates c
        JOIN people p
            ON p.id = c.person_id
        LEFT JOIN companies co
            ON co.id = c.current_company_id
        ORDER BY COALESCE(c.updated_at, c.created_at) DESC
        LIMIT %(limit)s
    """

    recent_jobs_query = """
        SELECT
            j.id AS job_id,
            j.title,
            j.status,
            j.source,
            j.owner_name,
            co.name AS company_name,
            j.updated_from_source_at,
            j.updated_at
        FROM jobs j
        LEFT JOIN companies co
            ON co.id = j.company_id
        ORDER BY COALESCE(j.updated_at, j.created_at) DESC
        LIMIT %(limit)s
    """

    recent_applications_query = """
        SELECT
            a.id AS application_id,
            a.application_status,
            a.source,
            p.full_name AS candidate_name,
            j.title AS job_title,
            a.updated_at
        FROM applications a
        LEFT JOIN candidates c
            ON c.id = a.candidate_id
        LEFT JOIN people p
            ON p.id = c.person_id
        LEFT JOIN jobs j
            ON j.id = a.job_id
        ORDER BY COALESCE(a.updated_at, a.created_at) DESC
        LIMIT %(limit)s
    """

    recent_documents_query = """
        SELECT
            d.id AS document_id,
            d.document_type,
            d.title,
            d.mime_type,
            d.source_uri,
            d.updated_at
        FROM documents d
        ORDER BY COALESCE(d.updated_at, d.created_at) DESC
        LIMIT %(limit)s
    """

    recent_source_records_query = """
        SELECT
            sr.id AS source_record_uuid,
            sr.source_system,
            sr.source_record_type,
            sr.source_record_id,
            sr.sync_status,
            sr.received_at,
            sr.processed_at,
            sr.created_at
        FROM source_records sr
        ORDER BY COALESCE(sr.processed_at, sr.received_at, sr.created_at) DESC
        LIMIT %(limit)s
    """

    document_type_counts_query = """
        SELECT
            document_type,
            COUNT(*)::int AS document_count
        FROM documents
        GROUP BY document_type
        ORDER BY document_count DESC, document_type ASC
        LIMIT %(limit)s
    """

    source_system_counts_query = """
        SELECT
            source_system,
            COUNT(*)::int AS source_record_count
        FROM source_records
        GROUP BY source_system
        ORDER BY source_record_count DESC, source_system ASC
        LIMIT %(limit)s
    """

    with postgres_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(counts_query)
            counts_row = cursor.fetchone()

            # Each list stays intentionally small.
            # The first review surface needs a quick cross-entity snapshot, not
            # deep pagination for one table at a time.
            cursor.execute(recent_candidates_query, {"limit": limit})
            recent_candidates = [dict(row) for row in cursor.fetchall()]

            cursor.execute(recent_jobs_query, {"limit": limit})
            recent_jobs = [dict(row) for row in cursor.fetchall()]

            cursor.execute(recent_applications_query, {"limit": limit})
            recent_applications = [dict(row) for row in cursor.fetchall()]

            cursor.execute(recent_documents_query, {"limit": limit})
            recent_documents = [dict(row) for row in cursor.fetchall()]

            cursor.execute(recent_source_records_query, {"limit": limit})
            recent_source_records = [dict(row) for row in cursor.fetchall()]

            cursor.execute(document_type_counts_query, {"limit": limit})
            document_type_counts = [dict(row) for row in cursor.fetchall()]

            cursor.execute(source_system_counts_query, {"limit": limit})
            source_system_counts = [dict(row) for row in cursor.fetchall()]

    # Convert the rows into plain Python dictionaries before leaving the DB
    # layer so the service, route, and UI all consume one predictable shape.
    return {
        "counts": dict(counts_row) if counts_row is not None else {},
        "recent_candidates": recent_candidates,
        "recent_jobs": recent_jobs,
        "recent_applications": recent_applications,
        "recent_documents": recent_documents,
        "recent_source_records": recent_source_records,
        "document_type_counts": document_type_counts,
        "source_system_counts": source_system_counts,
    }


__all__ = ["get_review_overview"]
