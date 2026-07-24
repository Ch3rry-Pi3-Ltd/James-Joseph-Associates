"""
Authentication and operational controls for the remote MCP transport.
"""

from __future__ import annotations

import secrets
from typing import Any
from uuid import uuid4

from fastapi.concurrency import run_in_threadpool
from starlette.datastructures import Headers
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from backend.services.mcp_operations import (
    audit_mcp_event_best_effort,
    enforce_mcp_rate_limit,
    fingerprint_mcp_principal,
)
from backend.settings import get_settings


class McpSecurityMiddleware:
    """
    Fail-closed bearer authentication plus a shared request-rate ceiling.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(
        self,
        scope: Scope,
        receive: Receive,
        send: Send,
    ) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        settings = get_settings()
        request_id = Headers(scope=scope).get("x-request-id") or str(uuid4())
        expected_token = settings.mcp_api_token.strip()
        supplied_token = _extract_bearer_token(Headers(scope=scope))

        if (
            expected_token == ""
            or supplied_token is None
            or not secrets.compare_digest(supplied_token, expected_token)
        ):
            await _audit_transport_event(
                principal_hash=None,
                request_id=request_id,
                event_type="authentication",
                outcome="rejected",
                error_code=(
                    "credential_not_configured"
                    if expected_token == ""
                    else "invalid_credential"
                ),
            )
            await _send_json(
                scope=scope,
                receive=receive,
                send=send,
                status_code=401,
                payload={
                    "error": {
                        "code": "unauthorized",
                        "message": "A valid MCP bearer credential is required.",
                    }
                },
                headers={"WWW-Authenticate": "Bearer"},
            )
            return

        principal_hash = fingerprint_mcp_principal(supplied_token)
        try:
            decision = await run_in_threadpool(
                enforce_mcp_rate_limit,
                principal_hash=principal_hash,
                limit=settings.mcp_rate_limit_per_minute,
            )
        except Exception:
            await _audit_transport_event(
                principal_hash=principal_hash,
                request_id=request_id,
                event_type="rate_limit",
                outcome="error",
                error_code="rate_limit_unavailable",
            )
            await _send_json(
                scope=scope,
                receive=receive,
                send=send,
                status_code=503,
                payload={
                    "error": {
                        "code": "service_unavailable",
                        "message": "MCP request controls are temporarily unavailable.",
                    }
                },
            )
            return

        rate_headers = {
            "X-RateLimit-Limit": str(decision.limit),
            "X-RateLimit-Remaining": str(
                max(0, decision.limit - decision.request_count)
            ),
        }
        if not decision.allowed:
            await _audit_transport_event(
                principal_hash=principal_hash,
                request_id=request_id,
                event_type="rate_limit",
                outcome="rejected",
                error_code="rate_limit_exceeded",
            )
            await _send_json(
                scope=scope,
                receive=receive,
                send=send,
                status_code=429,
                payload={
                    "error": {
                        "code": "rate_limit_exceeded",
                        "message": "The MCP request limit has been reached.",
                    }
                },
                headers={
                    **rate_headers,
                    "Retry-After": str(decision.retry_after_seconds),
                },
            )
            return

        scope.setdefault("state", {})
        scope["state"]["mcp_principal_hash"] = principal_hash
        scope["state"]["mcp_transport_request_id"] = request_id

        async def send_with_operational_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                headers.extend(
                    (key.lower().encode("ascii"), value.encode("ascii"))
                    for key, value in rate_headers.items()
                )
                message["headers"] = headers
            await send(message)

        await self.app(scope, receive, send_with_operational_headers)


def _extract_bearer_token(headers: Headers) -> str | None:
    authorization = headers.get("authorization")
    if authorization is None:
        return None
    scheme, separator, credential = authorization.partition(" ")
    if (
        separator == ""
        or scheme.lower() != "bearer"
        or credential.strip() == ""
    ):
        return None
    return credential.strip()


async def _audit_transport_event(**event: Any) -> None:
    await run_in_threadpool(
        audit_mcp_event_best_effort,
        tool_name=None,
        duration_ms=None,
        client_name=None,
        client_version=None,
        metadata={},
        **event,
    )


async def _send_json(
    *,
    scope: Scope,
    receive: Receive,
    send: Send,
    status_code: int,
    payload: dict[str, Any],
    headers: dict[str, str] | None = None,
) -> None:
    response = JSONResponse(
        status_code=status_code,
        content=payload,
        headers=headers,
    )
    await response(scope, receive, send)


__all__ = ["McpSecurityMiddleware"]
