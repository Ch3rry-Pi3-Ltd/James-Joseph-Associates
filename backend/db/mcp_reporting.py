"""Privacy-safe operational reporting over metadata-only MCP audit events."""

from __future__ import annotations

from typing import Any

from backend.db.connection import postgres_connection


def get_mcp_operational_summary(*, hours: int = 24) -> dict[str, Any]:
    """Return bounded tool reliability and latency metrics for a recent window."""

    bounded_hours = max(1, min(int(hours), 24 * 31))
    query = """
        select
            coalesce(tool_name, 'transport') as tool_name,
            count(*)::int as call_count,
            count(*) filter (where outcome = 'success')::int as success_count,
            count(*) filter (where outcome <> 'success')::int as failure_count,
            round(percentile_cont(0.5) within group (order by duration_ms))::int
                as p50_duration_ms,
            round(percentile_cont(0.95) within group (order by duration_ms))::int
                as p95_duration_ms,
            count(*) filter (
                where metadata->>'semantic_fallback_used' = 'true'
            )::int as semantic_fallback_count,
            round(avg(nullif(metadata->>'response_character_count', '')::numeric))::int
                as average_response_characters
        from mcp_audit_events
        where occurred_at >= now() - make_interval(hours => %(hours)s)
          and event_type = 'tool_call'
        group by coalesce(tool_name, 'transport')
        order by call_count desc, tool_name
    """

    with postgres_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(query, {"hours": bounded_hours})
            rows = [dict(row) for row in cursor.fetchall()]

    counts = {str(row["tool_name"]): int(row["call_count"]) for row in rows}
    search_count = counts.get("search_candidates_for_role", 0)
    profile_count = counts.get("get_candidate_profile", 0)
    return {
        "window_hours": bounded_hours,
        "tool_metrics": rows,
        "profile_calls_per_candidate_search": (
            round(profile_count / search_count, 3) if search_count else None
        ),
    }


__all__ = ["get_mcp_operational_summary"]
