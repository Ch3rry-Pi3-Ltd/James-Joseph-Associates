"""
Job read helpers for the intelligence backend.

This module contains small database query helpers for reading job data from the
prototype Supabase/Postgres schema.

It gives the rest of the repository a stable way to talk about:

- fetching one canonical job profile
- joining the job record to the linked company record
- joining the job record to the linked hiring-manage contact
- joining the contact record to the linked person record
- returning a predictable dictionary-like result shape

Keeping this logic in its own module makes the project easier to grow because:

- route handlers do not need to embed raw SQL
- job-specific queries stay near each other
- tests can target one small read module at a time
- future repository/service code can build on top of these helpers

In plain language:

- this module answers the question:

    "How does the backend read a job profile from Postgres?"

- it does not define database tables
- it does not create routes
- it does not write data
- it only reads job-related records

Notes
-----
- This module currently targets the prototype schema.
- The query shape may evolve once we inspect real source-system payloads.
- The helper returns a simple dictionary-like object so later layers can decide
  how to serialise it for APIs or workflows.

Important boundaries
--------------------
This module should not contain:

- FastAPI route handlers
- request/response models
- write/update logic
- LLM calls
- LangGraph workflow steps
- business decisions about matching or ranking
"""

from typing import Any

from backend.db.connection import postgres_connection

def get_job_profile(job_id: str) -> dict[str, Any] | None:
    """
    Return one job profile joined to company, contact, and person details.

    Parameters
    ----------
    job_id : str
        Canonical job UUID to look up.

    Returns
    -------
    dict[str, Any] | None
        Dictionary-like row containing the joined job profile fields.

        Return `None` if no job exists for the supplied ID.

    Notes
    -----
    - This reads from the prototype canonical schema, not directly from JobAdder.
    - The query joins:

        - `jobs`
        - `companies`
        - `contacts`
        - `people`

    - Left joins are used for related records because a job may not always have:

        - a linked company
        - a linked hiring-manager contact
        - a linked contact person record

    Returned fields
    ---------------
    The row currently includes:

        - `job_id`
        - `title`
        - `description`
        - `location`
        - `workplace_type`
        - `employment_type`
        - `work_type`
        - `source`
        - `owner_name`
        - `salary_min`
        - `salary_max`
        - `currency`
        - `status`
        - `opened_at`
        - `closed_at`
        - `updated_from_source_at`
        - `company_id`
        - `company_name`
        - `company_location`
        - `company_status`
        - `hiring_manager_contact_id`
        - `hiring_manager_person_id`
        - `hiring_manager_name`
        - `hiring_manager_email`
        - `hiring_manager_phone`
        - `hiring_manager_role_title`

    In plain language:

    - find one job by canonical ID
    - include the linked company details if present
    - include the linked hiring-manager details if present
    - return one row or nothing

    Example
    -------
    Read one job profile by canonical job ID:

        from backend.db.jobs import get_job_profile

        profile = get_job_profile(
            "55555555-5555-5555-5555-555555555551",
        )

        if profile is not None:
        
            print(profile["title"])
            print(profile["company_name"])
            print(profile["hiring_manager_name])
    """

    query = """
        SELECT
            j.id AS job_id,
            j.title,
            j.description,
            j.location,
            j.workplace_type,
            j.employment_type,
            j.work_type,
            j.source,
            j.owner_name,
            j.salary_min,
            j.salary_max,
            j.currency,
            j.status,
            j.opened_at,
            j.closed_at,
            j.updated_from_source_at,
            co.id AS company_id,
            co.name AS company_name,
            co.location AS company_location,
            co.status AS company_status,
            ct.id AS hiring_manager_contact_id,
            p.id AS hiring_manager_person_id,
            p.full_name AS hiring_manager_name,
            p.primary_email AS hiring_manager_email,
            p.primary_phone AS hiring_manager_phone,
            ct.role_title AS hiring_manager_role_title
        FROM jobs j
        LEFT JOIN companies co
            ON co.id = j.company_id
        LEFT JOIN contacts ct
            ON ct.id = j.hiring_manager_contact_id
        LEFT JOIN people p
            ON p.id = ct.person_id
        WHERE j.id = %(job_id)s
        LIMIT 1
    """

    with postgres_connection() as connection:
        with connection.cursor() as cursor:
            # Execute the SQL using a named parameter dictionary
            #   - This keeps the query clear and avoids manually stitching the
            #     ID into the SQL string.
            cursor.execute(
                query,
                {"job_id": job_id}
            )
            row = cursor.fetchone()

    # `fetchone()` returns `None` when no row matches the job ID
    #   - Returning `None` keeps the calling code simple and explicit.
    if row is None:
        return None
    
    # Convert the dictionary-like psycopg row into a plain Python `dict`.
    #   - That gives later services, routes, and tests a predictable result type.
    return dict(row)

__all__ = [
    "get_job_profile",
]