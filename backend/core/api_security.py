"""Privacy-safe application API rate limiting and cache policy."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from hashlib import sha256
import logging

from fastapi import Request, Response, status
from fastapi.responses import JSONResponse

from backend.db.api_security import consume_api_rate_limit
from backend.settings import get_settings


logger = logging.getLogger(__name__)
_API_PREFIX = "/api/v1/"
_RATE_LIMIT_EXEMPT_PATHS = {"/api/v1/health"}


def fingerprint_api_principal(request: Request) -> str:
    """Return a one-way identity without retaining user, token, or IP values."""

    workspace_user_id = request.headers.get("x-workspace-user-id", "").strip()
    authorization = request.headers.get("authorization", "").strip()
    client_host = request.client.host if request.client is not None else "unknown"
    if workspace_user_id:
        source = f"workspace:{workspace_user_id}"
    elif authorization:
        source = f"authorization:{authorization}"
    else:
        source = f"network:{client_host}"
    return sha256(source.encode("utf-8")).hexdigest()


def api_route_group(path: str) -> str:
    """Group dynamic endpoints without storing path parameters."""

    suffix = path.removeprefix(_API_PREFIX)
    first_segment = suffix.split("/", 1)[0] or "root"
    return first_segment[:64]


async def enforce_api_security(
    request: Request,
    call_next: Callable[[Request], Awaitable[Response]],
) -> Response:
    """Apply durable deployed rate limits and prevent private API caching."""

    path = request.url.path
    settings = get_settings()
    is_api_request = path.startswith(_API_PREFIX)
    should_rate_limit = (
        is_api_request
        and path not in _RATE_LIMIT_EXEMPT_PATHS
        and settings.environment in {"preview", "production"}
        and settings.api_rate_limit_enabled
    )

    decision = None
    if should_rate_limit:
        try:
            decision = consume_api_rate_limit(
                principal_hash=fingerprint_api_principal(request),
                route_group=api_route_group(path),
                limit=settings.api_rate_limit_per_minute,
            )
        except Exception as exc:
            logger.error(
                "api_rate_limit_unavailable path_group=%s error_type=%s",
                api_route_group(path),
                exc.__class__.__name__,
            )
            return _api_error_response(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                code="rate_limit_unavailable",
                message="API request controls are temporarily unavailable.",
            )

        if not decision.allowed:
            response = _api_error_response(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                code="rate_limit_exceeded",
                message="Too many requests. Please retry shortly.",
            )
            response.headers["Retry-After"] = str(decision.retry_after_seconds)
            _set_rate_limit_headers(response, decision.request_count, decision.limit)
            return response

    response = await call_next(request)
    if is_api_request:
        response.headers["Cache-Control"] = "private, no-store"
        response.headers["Pragma"] = "no-cache"
    if decision is not None:
        _set_rate_limit_headers(response, decision.request_count, decision.limit)
    return response


def _set_rate_limit_headers(response: Response, count: int, limit: int) -> None:
    response.headers["X-RateLimit-Limit"] = str(limit)
    response.headers["X-RateLimit-Remaining"] = str(max(0, limit - count))


def _api_error_response(*, status_code: int, code: str, message: str) -> JSONResponse:
    response = JSONResponse(
        status_code=status_code,
        content={"error": {"code": code, "message": message, "details": []}},
    )
    response.headers["Cache-Control"] = "private, no-store"
    response.headers["Pragma"] = "no-cache"
    return response


__all__ = [
    "api_route_group",
    "enforce_api_security",
    "fingerprint_api_principal",
]
