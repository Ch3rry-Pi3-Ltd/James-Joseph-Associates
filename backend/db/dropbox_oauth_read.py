"""
Small read helpers for Dropbox OAuth connection selection.
"""

from backend.db.connection import postgres_connection


def get_latest_dropbox_oauth_connection() -> dict[str, object] | None:
    """
    Return the most recently updated stored Dropbox OAuth connection row.
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
            dropbox_account_id,
            created_at,
            updated_at
        from dropbox_oauth_connections
        order by updated_at desc nulls last, created_at desc nulls last, id desc
        limit 1
    """

    with postgres_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(sql)
            row = cursor.fetchone()

    if row is None:
        return None

    return dict(row)


__all__ = ["get_latest_dropbox_oauth_connection"]
