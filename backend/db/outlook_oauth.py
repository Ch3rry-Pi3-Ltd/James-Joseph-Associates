"""
Database helpers for storing Outlook OAuth connection details.

This module contains the first small persistence helpers for the Outlook /
Microsoft Graph integration.

It gives the rest of the repository a stable way to talk about:

- saving the current Outlook OAuth connection
- reading the current Outlook OAuth connection
- keeping Microsoft token persistence logic out of route handlers

Example
-------
Typical usage in the rest of the backend looks like:

    saved_connection = save_outlook_oauth_connection(token_set)
    stored_connection = get_outlook_oauth_connection(
        saved_connection["microsoft_user_id"]
    )
"""

from datetime import datetime, timezone

from backend.db.connection import postgres_connection
from backend.services.outlook_oauth import OutlookTokenSet


def save_outlook_oauth_connection(token_set: OutlookTokenSet) -> dict[str, object]:
    """
    Insert or replace the current Outlook OAuth connection record.

    Example
    -------
    Reconnecting the same Microsoft user updates the stored tokens rather than
    creating duplicates.
    """

    obtained_at = datetime.now(timezone.utc)
    microsoft_user_id = token_set.microsoft_user_id

    if not isinstance(microsoft_user_id, str) or microsoft_user_id.strip() == "":
        raise ValueError(
            "Outlook token set did not include a usable Microsoft user identifier."
        )

    sql = """
        insert into outlook_oauth_connections (
            access_token,
            refresh_token,
            token_type,
            expires_in_seconds,
            obtained_at,
            scope,
            microsoft_user_id,
            tenant_id,
            user_principal_name
        )
        values (
            %(access_token)s,
            %(refresh_token)s,
            %(token_type)s,
            %(expires_in_seconds)s,
            %(obtained_at)s,
            %(scope)s,
            %(microsoft_user_id)s,
            %(tenant_id)s,
            %(user_principal_name)s
        )
        on conflict (microsoft_user_id)
        do update set
            access_token = excluded.access_token,
            refresh_token = excluded.refresh_token,
            token_type = excluded.token_type,
            expires_in_seconds = excluded.expires_in_seconds,
            obtained_at = excluded.obtained_at,
            scope = excluded.scope,
            tenant_id = excluded.tenant_id,
            user_principal_name = excluded.user_principal_name,
            updated_at = now()
        returning
            id,
            access_token,
            refresh_token,
            token_type,
            expires_in_seconds,
            obtained_at,
            scope,
            microsoft_user_id,
            tenant_id,
            user_principal_name,
            created_at,
            updated_at
    """

    params = {
        "access_token": token_set.access_token,
        "refresh_token": token_set.refresh_token,
        "token_type": token_set.token_type,
        "expires_in_seconds": token_set.expires_in,
        "obtained_at": obtained_at,
        "scope": token_set.scope,
        "microsoft_user_id": microsoft_user_id,
        "tenant_id": token_set.tenant_id,
        "user_principal_name": token_set.user_principal_name,
    }

    with postgres_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(sql, params)
            row = cursor.fetchone()

        connection.commit()

    if row is None:
        raise RuntimeError("Failed to save Outlook OAuth connection.")

    return dict(row)


def get_outlook_oauth_connection(
    microsoft_user_id: str,
) -> dict[str, object] | None:
    """
    Fetch the stored Outlook OAuth connection for one Microsoft user.

    Example
    -------
    Calling:

        get_outlook_oauth_connection("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")

    returns either the stored row or `None`.
    """

    sql = """
        select
            id,
            access_token,
            refresh_token,
            token_type,
            expires_in_seconds,
            obtained_at,
            scope,
            microsoft_user_id,
            tenant_id,
            user_principal_name,
            created_at,
            updated_at
        from outlook_oauth_connections
        where microsoft_user_id = %(microsoft_user_id)s
    """

    params = {"microsoft_user_id": microsoft_user_id}

    with postgres_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(sql, params)
            row = cursor.fetchone()

    if row is None:
        return None

    return dict(row)


__all__ = [
    "get_outlook_oauth_connection",
    "save_outlook_oauth_connection",
]
