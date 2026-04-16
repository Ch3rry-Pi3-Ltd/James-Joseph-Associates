"""
Integration tests for the real FastAPI application routes.

These tests call the actual FastAPI app defined in `backend.main`.

The important question is:

    "When the application is assembled for real, are the expected routes attached
    in the right place?"

These integration tests check the assembled app:

    backend.main.app
        -> backend.api.router
        -> backend.api.v1.health
        -> GET /api/v1/health

That matters because a route can be correct inside its own file but still fail
if it is not included in the main application router.

The expected route structure is:

    /api/v1/health

That path comes from two pieces being joined together:

    api_router = APIRouter(prefix="/api/v1")
    health route = @router.get("/health")

Together, they produce:

    /api/v1/health

In plain language:

- this file checks that the app has been plugged together correctly
- it does not test Supabase
- it does not test LangChain
- it does not test LangGraph
- it does not require any real data
"""

from fastapi import status
from fastapi.testclient import TestClient

from backend.main import app

def make_client() -> TestClient:
    """
    Create a test client for the real FastAPI application.

    The test client lets the tests send fake HTTP requests to the app without
    starting a real server.

    Returns
    -------
    TestClient
        In-memory HTTP client connected to `backend.main.app`.

    Notes
    -----
    - This does not run Uvicorn.
    - This does not deploy to Vercel.
    - This does not use the network.
    - It calls the FastAPI app directly inside the test process.
    - That makes it useful for checking route registration and response shapes.

    Request flow
    ------------
    A request made with this client moves through the app like this:

        TestClient
            -> backend.main.app
            -> backend.api.router
            -> backend.api.v1.health
            -> response

    In plain language:

    - build a fake browser/API client
    - point it at the real app
    - use it to check that routes work
    """

    return TestClient(app)

def test_health_route_is_registered_under_api_v1() -> None:
    """
    Verify that the health route exists at `/api/v1/health`.

    This test proves that the main app, shared API router, and health router are
    connected correctly.

    Notes
    -----
    - The health route is defined in `backend.api.v1.health`.
    - The `/api/v1` prefix is defined in `backend.api.router`.
    - The router is attached to the app in `backend.main`.
    - If any of those pieces are disconnected, this request will return 404.

    Expected response
    -----------------
    The route should return HTTP 200 with a small JSON body like:

        {
            "status": "ok",
            "service": "james-joseph-associates-api",
            "version": "0.1.0"
        }
    """

    # Create an in-memory client for the real assembled FastAPI app
    #   - This is the same `app` object that Vercel ultimately imports through
    #     `api.index`.
    #   - The test is checking app wiring, not a single isolated function.
    client = make_client()

    # Call the full public API path
    #   - `/api/v1` comes from the shared API router.
    #   - `/health` comes from the health endpoint router.
    response = client.get("/api/v1/health")

    assert response.status_code == status.HTTP_200_OK

    payload = response.json()

    assert payload["status"] == "ok"
    assert payload["service"] == "james-joseph-associates-api"
    assert payload["version"] == "0.1.0"

def test_health_route_is_not_registered_at_root_health() -> None:
    """
    Verify that `/health` is not the public health endpoint.

    The intended public backend path is:

        /api/v1/health
    
    not:

        /health

    This matters because the API is versioned. Make.com, future frontend code,
    and future MCP tools should use versioned paths so the backend can evolv
    without breaking clients unexpectedly.

    Notes
    -----
    - This test protects the route prefix.
    - It confirms that routes are grouped under `/api/v1`.
    - It also helps catch accidental direct registration of endpoint routers on
      the main app.
    """

    client = make_client()

    # Call the unversioned route on purpose
    #   - This should not exist.
    #   - If this returns 200, the health router has probably been attached in
    #     the wrong place as well as, or instead of, the versioned API router.
    response = client.get("/health")

    assert response.status_code == status.HTTP_404_NOT_FOUND

def test_unknown_api_route_returns_404() -> None:
    """
    Verify that an unknown API route returns HTTP 404.

    This test checks the basic behaviour for a path that does not exist.

    Notes
    -----
    - We have not created a custom 404 error handler yet.
    - For now, FastAPI's default 404 response is acceptable.
    - The important thing here is that unknown routes do not accidentally resolve
      to an existing endpoint.

    In plain language:

    - ask for an API route that does not exist
    - confirm the app says "not found"
    """

    client = make_client()

    # This route is intentionally fake
    #   - It sits under the real `/api/v1` prefix.
    #   - But there is no endpoint called `/does-not-exist`.
    response = client.get("/api/v1/does-not-exist")

    assert response.status_code == status.HTTP_404_NOT_FOUND

def test_openai_schema_includes_health_route() -> None:
    """
    Verify that the generated OpenAI schema includes the health route.

    FastAPI automatically creates an OpenAPI schema from the registered routes.
    That schema powers the local API docs and gives us a useful way to inspect
    the public API surface.

    Notes
    -----
    - This does not test the visual `/docs` page.
    - It checks the machine-readable `/openapi.json` schema.
    - If `/api/v1/health` is missing from this schema, the route is probably not
      registered on the real app.
    - Later, this same idea can help protect the API contract as more endpoints
      are added.

    Expected route entry
    --------------------
    The schema should contain:

        /api/v1/health

    with a GET operation.
    """

    client = make_client()

    # Ask FastAPI for the generated API schema.
    #   - This schema is built from the app's actual registered routes.
    #   - It is a useful app-level check because it sees the assembled route map.
    response = client.get("/openapi.json")

    assert response.status_code == status.HTTP_200_OK

    payload = response.json()
    paths = payload["paths"]

    assert "/api/v1/health" in paths
    assert "get" in paths ["/api/v1/health"]