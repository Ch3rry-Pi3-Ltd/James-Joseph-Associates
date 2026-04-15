"""
Top-level API router for the James Joseph Associates Intelligence API.

This module collects the backend's API route groups and exposes them as one
router that can be attached to the FastAPI application.

It gives the rest of the repository a stable way to talk about:

- API versioning
- route group registration
- the public API prefix
- keeping endpoint modules separate from application assembly

Keeping route registration in one place makes the project easier to understand
because:

- `backend.main` can focus on creating the FastAPI app
- `backend.api.router` can focus on collecting route groups
- `backend.api.v1.health` can focus on only health endpoints
- future endpoint modules can be added without changing application setup logic

In plain language:

- this module answers the question:

    "Which API routes belong to the app?"

- it gathers versioned routers and exposes them as one `api_router`

Notes
-----
- This module should not define endpoint handler functions directly.
- Endpoint handlers should live in versioned modules such as:

    backend.api.v1.health
    backend.api.v1.ingestion
    backend.api.v1.entities
    backend.api.v1.matching

- This keeps API versioning explicit.

Route structure
---------------
The intended route shape is:

    /api/v1/health
    /api/v1/entities
    /api/v1/documents
    /api/v1/retrieval
    /api/v1/matches
    /api/v1/feedback
    /api/v1/actions
    /api/v1/approvals

Important boundaries
--------------------
This module should not contain:

- Supabase queries
- request validation models
- service logic
- LangChain calls
- LangGraph workflow definitions
- Make.com payload transformation logic

If this file becomes more than route registration, the logic probably belongs in
a specific endpoint module or service module.
"""

from fastapi import APIRouter

from backend.api.v1.health import router as health_router

# Group all public v1 API routes under the shared `api/v1` prefix
api_router = APIRouter(prefix="/api/v1")

# Register versioned endpoint groups here as the API surface grows.
api_router.include_router(health_router)

__all__ = ["api_router"]