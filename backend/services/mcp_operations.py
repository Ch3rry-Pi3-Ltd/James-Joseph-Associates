"""
Security and audit helpers for remote MCP requests.
"""

from __future__ import annotations

import hashlib
import json
import logging
from typing import Any

from backend.db.mcp_operations import (
    McpRateLimitDecision,
    consume_mcp_rate_limit,
    record_mcp_audit_event,
)

logger = logging.getLogger(__name__)


def fingerprint_mcp_principal(token: str) -> str:
    """
    Return a stable one-way identifier without retaining the bearer token.
    """

    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def enforce_mcp_rate_limit(
    *,
    principal_hash: str,
    limit: int,
) -> McpRateLimitDecision:
    """
    Apply the shared database-backed MCP request limit.
    """

    return consume_mcp_rate_limit(
        principal_hash=principal_hash,
        limit=limit,
    )


def build_mcp_argument_metadata(arguments: dict[str, Any]) -> dict[str, Any]:
    """
    Describe tool input shape without retaining the input values.
    """

    serialized_size = len(
        json.dumps(arguments, default=str, separators=(",", ":"))
    )
    return {
        "argument_fields": sorted(arguments),
        "serialized_character_count": serialized_size,
    }


def audit_mcp_event_best_effort(**event: Any) -> None:
    """
    Persist audit metadata, falling back to structured application logging.
    """

    try:
        record_mcp_audit_event(**event)
    except Exception:
        logger.exception(
            "MCP audit persistence failed",
            extra={
                "mcp_event_type": event.get("event_type"),
                "mcp_tool_name": event.get("tool_name"),
                "mcp_outcome": event.get("outcome"),
                "mcp_request_id": event.get("request_id"),
            },
        )


__all__ = [
    "audit_mcp_event_best_effort",
    "build_mcp_argument_metadata",
    "enforce_mcp_rate_limit",
    "fingerprint_mcp_principal",
]
