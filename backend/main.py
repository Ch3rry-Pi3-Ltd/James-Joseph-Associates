"""
FastAPI application factory for the James Joseph Associates intelligence API.

This module is intentionally small, but it plays an important role in the
backend architecture. It gives the rest of the repository a stable way to talk
about:

- creating the FastAPI application
- attaching the project API router
- exposing the ASGI app used by Vercel
- keeping deployment wiring separate from business logic

Keeping application creation in its own module makes the project easier to
extend because:

- `api.index` can stay as a thin Vercel deployment adapter
- `backend.api.router` can focus on route registration
- `backend.api.v1.*` modules can focus on endpoint groups
- `backend.settings` can focus on environment configuration
- tests can import the app directly without going through Vercel

In plain language:

- this module answers the question:

    "How is the backend web app put together?"

- it does not define business endpoints
- it does not contain Supabase queries
- it does not contain LangChain or LangGraph workflows
- it should remain focused on application wiring

Notes
-----
- FastAPI applications are ASGI applications.
- ASGI is the interface that lets servers such as Vercel or Uvicorn run the app.
- Vercel imports the module-level `app` through `api.index`.
- Tests can also import `app` through this module.
- The `create_app` function is useful because it lets tests create a fresh app
  instance later if needed.
- Route registration is delegated to `backend.api.router`.

Request flow
------------
A typical request should move through the project like this:

    client
        -> Vercel or local ASGI server
        -> api.index.app
        -> backend.main.app
        -> backend.api.router
        -> backend.api.v1.<endpoint_group>

Later, individual endpoint modules will call into service modules such as:

        backend.services.<service>

Those service modules can then coordinate database repositories, retrieval code,
LangChain calls, LangGraph workflows, audit logging, and other business logic.

Important boundaries
--------------------
This module should not contain:

- route handler functions
- Supabase queries
- source-record ingestion logic
- document chunking logic
- embedding generation logic
- retrieval or ranking logic
- LangChain prompts
- LangGraph workflow definitions

If any of that logic appears here, it probably belongs in a more specific module.
"""

from contextlib import asynccontextmanager
from collections.abc import AsyncIterator

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError

from backend.api.router import api_router
from backend.core.api_security import enforce_api_security
from backend.core.errors import request_validation_exception_handler
from backend.core.performance import record_request_performance
from backend.services.mcp_server import mcp_server
from backend.services.mcp_transport import McpSecurityMiddleware
from backend.settings import get_settings


@asynccontextmanager
async def _application_lifespan(_: FastAPI) -> AsyncIterator[None]:
    """
    Keep the stateless MCP session manager alive with the parent ASGI app.
    """

    async with mcp_server.session_manager.run():
        yield


def create_app() -> FastAPI:
    """
    Create and configure the FastAPI application.

    Returns
    -------
    FastAPI
        Configured FastAPI application with the project API router attached.

    Notes
    -----
    - This function intentionally performs only lightweight application wiring.
    - It does not connect to Supabase.
    - It does not initialise model clients.
    - It does not build vector indexes.
    - It does not compile LangGraph workflows.

    Keeping this function lightweight matters because:

    - tests can create or import the app quickly
    - local development starts faster
    - Vercel cold starts stay simpler
    - expensive clients can be initialised lazily only when needed

    In plain language:

    - create the web app
    - attach the routes
    - return the configured app

    Example
    -------
    Tests can import the app directly:

        from backend.main import app

    Or create a fresh app instance later if needed:

        from backend.main import create_app

        test_app = create_app()
    """

    settings = get_settings()

    app = FastAPI(
        title=settings.app_name,
        version=settings.api_version,
        description=("Backend API for the GraphRAG recruitment intelligence system."),
        debug=settings.debug,
        lifespan=_application_lifespan,
    )

    # Route validation failures through our standard API error shape.
    #   - FastAPI normally returns validation errors as {"detail": [...]}. This
    #     project exposes errors as {"error": {...}} so clients and Make.com can
    #     parse failures consistently.
    app.add_exception_handler(
        RequestValidationError,
        request_validation_exception_handler,
    )

    # Emit one privacy-safe timing record for every HTTP request. The standard
    # Server-Timing header also makes Review, Company, search, and shortlist
    # latency visible in browser developer tools without changing API payloads.
    app.middleware("http")(record_request_performance)
    app.middleware("http")(enforce_api_security)

    # Register all project API routes in one place
    app.include_router(api_router)

    # Keep the MCP transport on an exact, slashless path. Mounting it directly
    # at /mcp would make Starlette append a slash while Vercel removes it,
    # creating a redirect loop. This root fallback is registered after the API
    # router, so existing API routes still take precedence.
    app.mount(
        "/",
        McpSecurityMiddleware(mcp_server.streamable_http_app()),
        name="read-only-mcp",
    )

    return app


# Vercel imports this module-level ASGI app through `api.index`.
#   - Keeping the app at module scope is the normal deployment pattern
#     for ASGI applications.
#   - The app itself is lightweight; expensive clients should be created
#     lazily in their own modules when a request actually needs them.
app = create_app()

__all__ = ["app", "create_app"]
