"""
Health endpoints for version 1 of the intelligence API.

This module defines the smallest useful API endpoint in the backend: a health
check.

It gives the rest of the repository a stable way to verify:

- the FastAPI application can start
- the route registration path works
- the `/api/v1` prefix is attached correctly
- tests can call the backend without needing Supabase, LangChain, or LangGraph
- Vercel can serve the Python API entrypoint

Keeping the health endpoint in its own modules makes the project easier to
extend because:

- `backend.main` can focus on application assembly
- `backend.api.router` can focus on route registration
- future endpoint modules can follow the same pattern
- tests can verify the API foundation before business logic is added

In plain language:

- this module answers the question:

    "Is the backend API alive?"

- it does not check the whole system
- it does not prove Supabase, embeddings, retrieval, or workflows are working

Notes
-----
- This endpoint is intentionally lightweight.
- It should not connect to external services.
- It should not require secrets.
- It should be safe to call in development, preview, production, and CI.
- Deeper readiness checks can be added later as separate endpoints.

Route
-----
This module contributes:

    GET /api/v1/health

The `api/v1` prefix is applied by `backend.api.router`.

Important boundaries
--------------------
This module should not contain:

- Supabase queries
- model provider calls
- LangChain logic
- LangGraph workflows
- Make.com integration logic
- document parsing or embedding logic

If the health check becomes more than a lightweight application liveness check,
split deeper checks into a separate readiness endpoint.
"""

from fastapi import APIRouter

from backend.schemas.common import HealthResponse

router = APIRouter(tags=["health"])

@router.get("/health", response_model=HealthResponse)
def get_health() -> HealthResponse:
    """
    Return a lightweight API liveness response.

    Returns
    -------
    HealthResponse
        Simple response configuration that the FastAPI application is reachable.

    Notes
    -----
    - This function should stay fast and dependency-free.
    - It does not check Supabase connectivity.
    - It does not check model provider connectivity.
    - It does not check Make.com integration status.
    - It only confirms that the Python API app route registration works.

    Example
    -------
    A successful response should look like:

        {
            "status": "ok",
            "service": "james-joseph-associates-api",
            "version": "0.1.0"
        }
    """

    return HealthResponse(
        status="ok",
        service="james-joseph-associates-api",
        version="0.1.0",
    )

__all__ = ["router"]