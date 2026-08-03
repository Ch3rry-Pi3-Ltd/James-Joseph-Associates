"""Durable database operations used by the main API security middleware."""

from __future__ import annotations

from dataclasses import dataclass

from backend.db.connection import postgres_connection


@dataclass(frozen=True, slots=True)
class ApiRateLimitDecision:
    allowed: bool
    request_count: int
    limit: int
    retry_after_seconds: int


def consume_api_rate_limit(
    *,
    principal_hash: str,
    route_group: str,
    limit: int,
) -> ApiRateLimitDecision:
    """Atomically consume one request from a shared UTC-minute window."""

    with postgres_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO api_rate_limit_windows (
                    principal_hash,
                    route_group,
                    window_started_at,
                    request_count
                )
                VALUES (%s, %s, date_trunc('minute', NOW()), 1)
                ON CONFLICT (principal_hash, route_group, window_started_at)
                DO UPDATE
                SET request_count = api_rate_limit_windows.request_count + 1
                WHERE api_rate_limit_windows.request_count < %s
                RETURNING
                    request_count,
                    GREATEST(
                        1,
                        CEIL(EXTRACT(EPOCH FROM (
                            window_started_at + INTERVAL '1 minute' - NOW()
                        )))
                    )::integer AS retry_after_seconds
                """,
                (principal_hash, route_group, limit),
            )
            row = cursor.fetchone()
        connection.commit()

    if row is None:
        return ApiRateLimitDecision(
            allowed=False,
            request_count=limit,
            limit=limit,
            retry_after_seconds=60,
        )
    return ApiRateLimitDecision(
        allowed=True,
        request_count=int(row["request_count"]),
        limit=limit,
        retry_after_seconds=int(row["retry_after_seconds"]),
    )


__all__ = ["ApiRateLimitDecision", "consume_api_rate_limit"]
