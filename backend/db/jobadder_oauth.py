"""
Database helpers for storing JobAdder OAuth connection details.

This module contains the first small persistence helpers for the JobAdder
integration.

It gives the rest of the repository a stable way to talk about:

- saving the current JobAdder OAuth connection
- reading the current JobAdder OAuth connection
- keeping JobAdder token persistence logic out of route handlers
- matching the same direct-SQL helper style already used elsewhere in the
  backend

Why this module exists
----------------------
We can already:

- build the JobAdder approval URL
- receive the callback
- exchange a one-time authorization code for tokens

But we cannot yet keep those tokens anywhere.

That means the next safe step is to add a database helper that can persist the
token response once the callback flow is fully wired.

Keeping this logic in `backend.db` is consistent with the rest of the backend,
where direct Postgres reads and writes already live in small helper modules.

Important note
--------------
This module assumes a table exists for storing one JobAdder OAuth connection.

For now, this code expects a table shaped roughly like:

    jobadder_oauth_connections
    - id
    - access_token
    - refresh_token
    - token_type
    - expires_in_seconds
    - obtained_at
    - api_url
    - jobadder_instance
    - jobadder_account
    - created_at
    - updated_at

In plain language:

- this module answers the question:

    "How does the backend save and fetch the current JobAdder OAuth connection?"

- it does not call JobAdder directly
- it does not build OAuth URLs
- it does not exchange codes for tokens
- it only reads and writes token data in Postgres
"""

from datetime import datetime, timezone

from backend.db.connection import postgres_connection
from backend.services.jobadder_oauth import JobAdderTokenSet

def save_jobadder_oauth_connection(token_set: JobAdderTokenSet) -> dict[str, object]:
    """
    Insert or replace the current JobAdder OAuth connection record.

    Parameters
    ----------
    token_set : JobAdderTokenSet
        Normalised token response returned by the JobAdder token-exchange step.

    Returns
    -------
    dict[str, object]
        Plain dictionary representing the saved connection row.

    Notes
    -----
    - This helper currently stores a single logical JobAdder connection record.
    - The `jobadder_account` field is treated as the stable natural key for the
      connected JobAdder account.
    - The SQL uses an upsert so reconnecting the same JobAdder account updates
      the existing record instead of creating duplicates.

    Stored timing fields
    --------------------
    We store both:

    - `expires_in_seconds`
    - `obtained_at`

    because `expires_in` alone is only a duration. To know when the token will
    expire, the backend also needs to know when the token was obtained.

    Provider fields
    ---------------
    This helper stores the fields JobAdder documents in its token response:

    - `access_token`
    - `refresh_token`
    - `token_type`
    - `expires_in`
    - `api`
    - `instance`
    - `account`

    In plain language:

    - save the latest tokens for this JobAdder account
    - update the existing record if this account already exists
    - return the saved row
    """

    obtained_at = datetime.now(timezone.utc)

    raw_api_url = token_set.raw_payload.get("api")
    raw_jobadder_instance = token_set.raw_payload.get("instance")
    raw_jobadder_account = token_set.raw_payload.get("account")

    api_url = raw_api_url if isinstance(raw_api_url, str) else None
    jobadder_instance = (
        raw_jobadder_instance if isinstance(raw_jobadder_instance, str) else None
    )

    # JobAdder documents `account` as a number in the token response.
    #   - Keep the value typed as `int | None` when possible so later matching
    #     and filtering code does not have to reverse engineer numeric IDs from
    #     strings.
    #   - Guard the conversion carefully because a non-empty string such as
    #     `"abc"` should become `None`, not raise an unhandled `ValueError`.
    jobadder_account: int | None = None

    if isinstance(raw_jobadder_account, (int, float, str)):
        cleaned_account = str(raw_jobadder_account).strip()

        if cleaned_account != "":
            try:
                jobadder_account = int(cleaned_account)
            except ValueError:
                jobadder_account = None

    if jobadder_account is None:
        raise ValueError(
            "JobAdder token set did not include a usable account identifier."
        )
    
    sql = """
        insert into jobadder_oauth_connections (
            access_token,
            refresh_token,
            token_type,
            expires_in_seconds,
            obtained_at,
            api_url,
            jobadder_instance,
            jobadder_account
        )
        values (
            %(access_token)s,
            %(refresh_token)s,
            %(token_type)s,
            %(expires_in_seconds)s,
            %(obtained_at)s,
            %(api_url)s,
            %(jobadder_instance)s,
            %(jobadder_account)s
        )
        on conflict (jobadder_account)
        do update set
            access_token = excluded.access_token,
            refresh_token = excluded.refresh_token,
            token_type = excluded.token_type,
            expires_in_seconds = excluded.expires_in_seconds,
            obtained_at = excluded.obtained_at,
            api_url = excluded.api_url,
            jobadder_instance = excluded.jobadder_instance,
            updated_at = now()
        returning
            id,
            access_token,
            refresh_token,
            token_type,
            expires_in_seconds,
            obtained_at,
            api_url,
            jobadder_instance,
            jobadder_account,
            created_at,
            updated_at
    """

    params = {
        "access_token": token_set.access_token,
        "refresh_token": token_set.refresh_token,
        "token_type": token_set.token_type,
        "expires_in_seconds": token_set.expires_in,
        "obtained_at": obtained_at,
        "api_url": api_url,
        "jobadder_instance": jobadder_instance,
        "jobadder_account": jobadder_account,
    }

    with postgres_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(sql, params)
            row = cursor.fetchone()

    if row is None:
        raise RuntimeError("Failed to save JobAdder OAuth connection.")
    
    return dict(row)

def get_jobadder_oauth_connection(jobadder_account: int) -> dict[str, object] | None:
    """
    Fetch the stored JobAdder OAuth connection for one JobAdder account.

    Parameters
    ----------
    jobadder_account : int
        Numeric JobAdder account identifier returned in the token response.

    Returns
    -------
    dict[str, object] | None
        Plain dictionary representing the stored connection row, or `None` if no
        record exists.

    Notes
    -----
    - This helper is intentionally narrow.
    - Later refresh-token and disconnect logic will need a reliable way to load
      the stored connection before updating or removing it.

    In plain language:

    - look up the stored JobAdder connection for one account
    - return it if found
    - otherwise return none
    """

    sql = """
        select
            id,
            access_token,
            refresh_token,
            token_type,
            expires_in_seconds,
            obtained_at,
            api_url,
            jobadder_instance,
            jobadder_account,
            created_at,
            updated_at
        from jobadder_oauth_connections
        where jobadder_account = %(jobadder_account)s
    """

    params = {
        "jobadder_account": jobadder_account,
    }

    with postgres_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(sql, params)
            row = cursor.fetchone()

    if row is None:
        return None

    return dict(row)

__all__ = [
    "get_jobadder_oauth_connection",
    "save_jobadder_oauth_connection",
]
