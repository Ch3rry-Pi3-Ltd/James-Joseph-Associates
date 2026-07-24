"""
Persistent operational controls for the remote MCP endpoint.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from psycopg.types.json import Jsonb

from backend.db.connection import postgres_connection


@dataclass(frozen=True)
class McpRateLimitDecision:
    allowed: bool
    request_count: int
    limit: int
    retry_after_seconds: int


def consume_mcp_rate_limit(
    *,
    principal_hash: str,
    limit: int,
) -> McpRateLimitDecision:
    """
    Atomically consume one request from the current UTC minute.
    """

    with postgres_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO mcp_rate_limit_windows (
                    principal_hash,
                    window_started_at,
                    request_count
                )
                VALUES (
                    %s,
                    date_trunc('minute', NOW()),
                    1
                )
                ON CONFLICT (principal_hash, window_started_at)
                DO UPDATE
                SET request_count = mcp_rate_limit_windows.request_count + 1
                WHERE mcp_rate_limit_windows.request_count < %s
                RETURNING
                    request_count,
                    GREATEST(
                        1,
                        CEIL(
                            EXTRACT(
                                EPOCH FROM (
                                    window_started_at
                                    + INTERVAL '1 minute'
                                    - NOW()
                                )
                            )
                        )
                    )::integer AS retry_after_seconds
                """,
                (principal_hash, limit),
            )
            row = cursor.fetchone()
        connection.commit()

    if row is None:
        return McpRateLimitDecision(
            allowed=False,
            request_count=limit,
            limit=limit,
            retry_after_seconds=60,
        )

    return McpRateLimitDecision(
        allowed=True,
        request_count=int(row["request_count"]),
        limit=limit,
        retry_after_seconds=int(row["retry_after_seconds"]),
    )


def record_mcp_audit_event(
    *,
    principal_hash: str | None,
    request_id: str | None,
    event_type: str,
    tool_name: str | None,
    outcome: str,
    duration_ms: int | None = None,
    error_code: str | None = None,
    client_name: str | None = None,
    client_version: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    """
    Persist non-sensitive MCP execution metadata.

    Prompts, tool arguments, candidate payloads, answers, and credentials are
    intentionally excluded from this table.
    """

    with postgres_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO mcp_audit_events (
                    principal_hash,
                    request_id,
                    event_type,
                    tool_name,
                    outcome,
                    duration_ms,
                    error_code,
                    client_name,
                    client_version,
                    metadata
                )
                VALUES (
                    %s,
                    %s,
                    %s,
                    %s,
                    %s,
                    %s,
                    %s,
                    %s,
                    %s,
                    %s::jsonb
                )
                """,
                (
                    principal_hash,
                    request_id,
                    event_type,
                    tool_name,
                    outcome,
                    duration_ms,
                    error_code,
                    client_name,
                    client_version,
                    Jsonb(metadata or {}),
                ),
            )
        connection.commit()


__all__ = [
    "McpRateLimitDecision",
    "consume_mcp_rate_limit",
    "record_mcp_audit_event",
]
