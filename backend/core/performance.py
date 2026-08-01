"""Lightweight, privacy-safe request performance instrumentation."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from contextvars import ContextVar, Token
import logging
from time import perf_counter
from uuid import uuid4

from fastapi import Request, Response


logger = logging.getLogger(__name__)

_request_id: ContextVar[str | None] = ContextVar(
    "performance_request_id",
    default=None,
)


def current_request_id() -> str | None:
    """Return the request correlation identifier in the current context."""

    return _request_id.get()


def bind_request_id(request_id: str) -> Token[str | None]:
    """Bind one generated request identifier until its middleware resets it."""

    return _request_id.set(request_id)


def reset_request_id(token: Token[str | None]) -> None:
    """Restore the request context that existed before instrumentation."""

    _request_id.reset(token)


async def record_request_performance(
    request: Request,
    call_next: Callable[[Request], Awaitable[Response]],
) -> Response:
    """Measure an HTTP request without recording its query string or body."""

    request_id = uuid4().hex
    request_id_token = bind_request_id(request_id)
    started_at = perf_counter()

    try:
        response = await call_next(request)
    except Exception:
        duration_ms = max(0.0, (perf_counter() - started_at) * 1000)
        # FastAPI records the exception separately. Keep the timing event free
        # of exception text because provider and database errors can echo user
        # input or retrieved evidence.
        logger.warning(
            "request_performance request_id=%s method=%s path=%s "
            "status_code=500 duration_ms=%.2f",
            request_id,
            request.method,
            request.url.path,
            duration_ms,
        )
        raise
    else:
        duration_ms = max(0.0, (perf_counter() - started_at) * 1000)
        timing_value = f"app;dur={duration_ms:.2f}"
        existing_timing = response.headers.get("Server-Timing")
        response.headers["Server-Timing"] = (
            f"{existing_timing}, {timing_value}" if existing_timing else timing_value
        )
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Response-Time-Ms"] = f"{duration_ms:.2f}"

        logger.info(
            "request_performance request_id=%s method=%s path=%s "
            "status_code=%s duration_ms=%.2f",
            request_id,
            request.method,
            request.url.path,
            response.status_code,
            duration_ms,
        )
        return response
    finally:
        reset_request_id(request_id_token)


__all__ = [
    "bind_request_id",
    "current_request_id",
    "record_request_performance",
    "reset_request_id",
]
