"""
Integration tests for the API health endpoint.

This module verifies the smallest useful backend flow:

    FastAPI app
        -> API router
        -> version 1 health router
        -> health response schema

It gives the project a simple way to prove that:

- the FastAPI app can be imported
- route registration works
- `/api/v1/health` exists
- the endpoint returns the expected response shape
- the response model can be serialized as JSON

In plain language:

- this test answers the question:

    "Can the Python backend respond to its first API route?"

- it does not test Supabase
- it does not test LangChain or LangGraph
- it does not test deployment on Vercel directly

Notes
-----
- Fast API provides `TestClient` for calling the app in tests.
- `TestClient` avoids needing to start a real HTTP server.
- The test uses the same app object that Vercel imports through `api.index`.
"""

from fastapi.testclient import TestClient

from backend.main import app

client = TestClient(app)

def test_health_endpoint_returns_liveness_response() -> None:
    """
    Verify that the health endpoint returns the expected liveness payload.

    Notes
    -----
    - This test follows the same route path a real client will call:

        GET /api/v1/health

    - A passing result proves that the app, top-level router, versioned router,
      endpoint module, and response schema are connected correctly.
    """

    response = client.get("/api/v1/health")

    # The health endpoint should be reachable without any auth, database, model,
    # or working dependencies
    #   - If this fails, the backend foundation itself is not wired correctly yet.
    assert response.status_code == 200

    # Keep the first response contract deliberately strct
    #   - This endpoint is used as a deployment and test signal, so unexpected extra
    #     keys or changed values should be cause immediately.
    assert response.json() == {
        "status": "ok",
        "service": "james-joseph-associates-api",
        "version": "0.1.0",
    }
