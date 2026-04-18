"""
Integration tests for the protected Make.com test endpoint.

These tests verify the real FastAPI route wiring for:

    POST /api/v1/make/test-event

The important question is:

    "Can the deployed-style backend accept a protected Make.com request and
    reject unsafe requests?"

This is different from the smaller unit tests for security and idempotency.

The unit tests check helpers directly:

    Authorization header
        -> security helper
        -> authorised or rejected

    Idempotency-Key header
        -> idempotency helper
        -> key or failure reason

These integration tests check the full API route flow:

    TestClient
        -> FastAPI app
        -> /api/v1/make/test-event
        -> bearer-token check
        -> idempotency-key check
        -> Make metadata extraction
        -> {"status": "accepted", ...}

The successfull request should look like a real Make.com request:

    Authorization: Bearer <MAKE_API_TOKEN>
    Idempotency-Key: make-<execution-id>
    X-Source-System: make
    X-Make-Run-Id: <execution-id>
    X-Request-Id: make-<execution-id>

The expected successful response shape is:

    {
        "status": "accepted",
        "message": "Make.com test event accepted.",
        "event_type": "manual_make_test",
        "idempotency_key": "make-...",
        "payload_hash": "...",
        "request_metadata": {
            "idempotency_key": "make-...",
            "source_system": "make",
            "make_run_id": "...",
            "request_id": "make-..."
        }
    }

In plain language:

- prove Make.com-style requests work
- prove missing or wrong tokens are rejected
- prove POST requests require an idempotency key
- prove useful Make.com metadata reaches the backend
"""

from collections.abc import Iterator

import pytest
from fastapi import status
from fastapi.testclient import TestClient

from backend.main import create_app
from backend.settings import get_settings

MAKE_TEST_EVENT_PATH = "/api/v1/make/test-event"
TEST_MAKE_API_TOKEN = "test-make-api-token"
TEST_EXECUTION_ID = "test-execution-001"

@pytest.fixture(autouse=True)
def clear_settings_cache() -> Iterator[None]:
    """
    Clear cached settings before and after each test.

    The backend settings are cached with `get_settings`.

    That is good for the real app because settings should not be repeatedly
    parsed during every request.

    In these tests, though, we deliberately change environment variables with
    `monkeypatch`.

    Returns
    -------
    Iterator[None]
        Pytest fixture iterator.

    Notes
    -----
    - Each test should get a fresh settings object.
    - This prevents one test's `MAKE_API_TOKEN` value from leaking into another
      test.
    - The fixture runs automatically for every test in this file.

    In plain language:

    - before the test: forget old settings
    - run the test
    - after the test: forget settings again
    """

    # Clear settings before the test starts
    #   - This makes sure environment changes made by `monkeypatch` are visible
    #     when the endpoint calls `get_settings()`.
    get_settings.cache_clear()

    yield

    # Clear settings after the test finishes
    #   - This avoids carrying this test's fake token into later tests.
    get_settings.cache_clear()

def create_test_client(
    monkeypatch: pytest.MonkeyPatch,
    *,
    make_api_token: str = TEST_MAKE_API_TOKEN,
) -> TestClient:
    """
    Create a TestClient with a controlled Make.com API token.

    Parameters
    ----------
    monkeypath : pytest.MonkeyPatch
        Pytest helper used to temporarily set environment variables.

    make_api_token : str
        Fake Make.com API token for this test.

        This value is not a real secret. It exists only inside the test process.

    Returns
    -------
    TestClient
        In-memory HTTP client for the FastAPI application.

    Notes
    -----
    - `TestClient` lets the test call the FastAPI app without starting Uvicorn
      or deploying to Vercel.
    - Setting `MAKE_API_TOKEN` here makes the protected endpoint behave as if
      Vercel had that environment variable configured.
    - `create_app()` builds the same app shape used by the real backend.

    In plain language:

    - set a fake backend token
    - create the app
    - return a fake HTTP client that can call the app directly
    """

    # Set the token the backend should expect
    #   - The request must send this same value as:
    #
    #       Authorization: Bearer <token>
    #
    #   - Environment variables override `.env.local`, which keeps tests
    #     independent from your real local secrets.
    monkeypatch.setenv("MAKE_API_TOKEN", make_api_token)

    return TestClient(create_app())

def make_request_body() -> dict[str, object]:
    """
    Build the standard Make.com test request body.

    Returns
    -------
    dict[str, object]
        JSON-like request body sent to the Make.com test endpoint.

    Notes
    -----
    - This mirrors the manual Make.com request that can be tested through the UI.
    - It is deliberately small and safe.
    - It does not contain real candidate, client, or recruitment data.

    Example
    -------
    The returned body is:

        {
            "event_type": "manual_make_test",
            "payload": {
                "message": "Hello from Make.com"
            }
        }

    In plain language:

    - send a labelled test event
    - include one small test payload
    """

    return {
        "event_type": "manual_make_test",
        "payload": {
            "message": "Hello from Make.com"
        },
    }

def make_authorised_headers(
    *,
    token: str = TEST_MAKE_API_TOKEN,
    execution_id: str = TEST_EXECUTION_ID,
) -> dict[str, str]:
    """
    Build headers that mimic the saved Make.com HTTP module.

    Parameters
    ----------
    token : str
        Bearer token sent by Make.com.

    execution_id : str
        Make.com execution ID used to make request metadata traceable.

    Returns
    -------
    dict[str, str]
        Headers for a valid protected Make.com request.

    Notes
    -----
    - `Authorization` proves the caller knows the shared Make.com API token.
    - `Idempotency-Key` gives the backend a retry-safe key for this run.
    - `X-Source-System` records where the request came from.
    - `X-Make-Run-Id` records Make.com's execution ID directly.
    - `X-Request-Id` gives the backend a readable request trace ID.

    In plain language:

    - authenticate the request
    - give the request a unique retry key
    - attach enough metadata to debug the Make.com run later
    """

    # This mirrors the Make.com keychain output
    #   - In Vercel and `.env.local`, the backend stores only the raw token.
    #   - In the HTTP request, Make.com sends `Bearer <token>`.
    authorization_value = f"Bearer {token}"

    # This mirrors the final Make.com setup:
    #
    #   Idempotency-Key: make-[Execution id]
    #   X-Make-Run-Id: [Execution id]
    #   X-Request-Id: make-[Execution id]
    idempotency_key = f"make-{execution_id}"

    return {
        "Authorization": authorization_value,
        "Idempotency-Key": idempotency_key,
        "X-Source-System": "make",
        "X-Make-Run-Id": execution_id,
        "X-Request-Id": idempotency_key,
    }

def test_make_test_event_rejects_unconfigured_backend_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    Verify that the endpoint fails closed when `MAKE_API_TOKEN` is empty.

    Notes
    -----
    - Protected endpoints should not accidentally accept requests when secrets
      are missing.
    - An empty `MAKE_API_TOKEN` means the backend has not been configured yet.
    - The endpoint should return a standard API error response.

    Expected result
    ---------------
    The response should be:

        HTTP 401

    with:

        error.code = "unauthorized"
    """

    # Force the backend into the "not configured" state
    #   - This overrides any real `.env.local` token for the duration of this
    #     test.
    monkeypatch.setenv("MAKE_API_TOKEN", "")

    client = TestClient(create_app())

    response = client.post(
        MAKE_TEST_EVENT_PATH,
        json=make_request_body(),
        headers=make_authorised_headers(),
    )

    assert response.status_code == status.HTTP_401_UNAUTHORIZED

    payload = response.json()

    assert payload["error"]["code"] == "unauthorized"
    assert payload["error"]["message"] == "Make.com API access is not configured."
    assert payload["error"]["details"] == [
        {
            "setting": "MAKE_API_TOKEN",
            "reason": "missing_or_empty",
        }
    ]

def test_make_test_event_rejects_missing_authorization_header(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    Verify that the endpoint rejects requests without `Authorization`.

    Notes
    -----
    - Make.com protected requests must send the API token.
    - Without the token, the backend cannot trust the request.
    - The endpoint should reject the request before accepting the event.

    In plain language:

    - no auth header
    - no access
    """

    client = create_test_client(monkeypatch)

    headers = make_authorised_headers()

    # Remove the auth header on purpose
    #   - This mimics a Make.com module that has not selected the API key
    #     keychain.
    headers.pop("Authorization")

    response = client.post(
        MAKE_TEST_EVENT_PATH,
        json=make_request_body(),
        headers=headers,
    )

    assert response.status_code == status.HTTP_401_UNAUTHORIZED

    payload = response.json()

    assert payload["error"]["code"] == "unauthorized"
    assert payload["error"]["message"] == "Request is not authorised."
    assert payload["error"]["details"] == [
        {
            "reason": "missing_authorization_header",
        }
    ]

def test_make_test_event_rejects_wrong_bearer_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    Verify that the endpoint rejects an incorrect bearer token.

    Notes
    -----
    - The request has the correct `Authorization` shape.
    - The token value is wrong.
    - The endpoint should still reject the request.

    In plain language:

    - the caller sent a token
    - but it was not the token the backend expected
    """

    client = create_test_client(monkeypatch)

    response = client.post(
        MAKE_TEST_EVENT_PATH,
        json=make_request_body(),
        headers=make_authorised_headers(token="wrong-token"),
    )

    assert response.status_code == status.HTTP_401_UNAUTHORIZED

    payload = response.json()

    assert payload["error"]["code"] == "unauthorized"
    assert payload["error"]["message"] == "Request is not authorised."
    assert payload["error"]["details"] == [
        {
            "reason": "invalid_bearer_token",
        }
    ]

def test_make_test_event_requires_idempotency_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    Verify that protected Make.com POST requests require an idempotency key.

    Notes
    -----
    - This endpoint represents the request pattern future Make.com write routes
      should use.
    - Write-style requests should send an `Idempotency-Key`.
    - The key lets the backend safely handle retries later.

    In plain language:

    - Make.com can retry failed requests
    - the backend needs a retry key before accepting POST-style work
    """

    client = create_test_client(monkeypatch)

    headers = make_authorised_headers()

    # Remove the idempotency key on purpose
    #   - Auth should pass.
    #   - Idempotency validation should fail.
    headers.pop("Idempotency-Key")

    response = client.post(
        MAKE_TEST_EVENT_PATH,
        json=make_request_body(),
        headers=headers,
    )

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT

    payload = response.json()

    assert payload["error"]["code"] == "validation_error"
    assert payload["error"]["message"] == (
        "Idempotency key is required for this request."
    )
    assert payload["error"]["details"] == [
        {
            "header": "Idempotency-Key",
            "reason": "missing_idempotency_key",
        }
    ]

def test_make_test_event_accepts_valid_make_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    Verify that a valid Make.com-style request is accepted.

    This test is the automated version of the successful Make.com manual test.

    Notes
    -----
    - The backend has a configured token.
    - The request sends the matching bearer token.
    - The request sends an `Idempotency-Key`.
    - The body matches the expected test-event schema.
    - The endpoint should return HTTP 200 with `status = accepted`.

    Expected response
    -----------------
    The response should include:

        status: accepted
        event_type: manual_make_test
        idempotency_key: make-test-execution-001
        payload_hash: <64-character sha256 hash>

    In plain language:

    - Make.com sent the request properly
    - the backend accepted it
    """

    client = create_test_client(monkeypatch)

    response = client.post(
        MAKE_TEST_EVENT_PATH,
        json=make_request_body(),
        headers=make_authorised_headers(),
    )

    assert response.status_code == status.HTTP_200_OK

    payload = response.json()

    assert payload["status"] == "accepted"
    assert payload["message"] == "Make.com test event accepted."
    assert payload["event_type"] == "manual_make_test"
    assert payload["idempotency_key"] == "make-test-execution-001"

    # The payload hash should be a SHA-256 hex digest
    #   - SHA-256 hex strings are 64 characters long.
    #   - We do not hard-code the exact hash here because the important contract
    #     is that the backend returns a stable fingerprint.
    assert isinstance(payload["payload_hash"], str)
    assert len(payload["payload_hash"]) == 64

def test_make_test_event_returns_make_request_metadata(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    Verify that Make.com request metadata is returned in the response.

    Notes
    -----
    - These metadata fields help trace a backend request back to a Make.com run.
    - The endpoint does not need this metadata to accept the request.
    - Returning it during the foundation stage makes testing and debugging easy.

    Expected metadata
    -----------------
    The response should contain:

        request_metadata.idempotency_key
        request_metadata.source_system
        request_metadata.make_run_id
        request_metadata.request_id

    In plain language:

    - the backend received the Make.com headers
    - the backend copied the safe metadata into the response
    """

    client = create_test_client(monkeypatch)

    response = client.post(
        MAKE_TEST_EVENT_PATH,
        json=make_request_body(),
        headers=make_authorised_headers(),
    )

    assert response.status_code == status.HTTP_200_OK

    payload = response.json()

    assert payload["request_metadata"] == {
        "idempotency_key": "make-test-execution-001",
        "source_system": "make",
        "make_run_id": "test-execution-001",
        "request_id": "make-test-execution-001",
    }

def test_make_test_event_rejects_unexpected_request_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    Verify that the Make.com test body rejects unexpected top-level fields.

    Notes
    -----
    - The request schema uses `extra="forbid"`.
    - That means Make.com should not silently send random top-level fields.
    - FastAPI should convert the validation failure into the shared API error
      response shape.

    In plain language:

    - if the request shape changes by accident
    - the backend should reject it clearly
    """

    client = create_test_client(monkeypatch)

    body = {
        "event_type": "manual_make_test",
        "payload": {
            "message": "Hello from Make.com",
        },
        "unexpected_field": "this should not be accepted",
    }

    response = client.post(
        MAKE_TEST_EVENT_PATH,
        json=body,
        headers=make_authorised_headers(),
    )

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT

    payload = response.json()

    assert payload["error"]["code"] == "validation_error"
    assert payload["error"]["message"] == "Request validation failed."

    # The validation details should point at the unexpected field.
    #   - This proves the endpoint is rejecting accidental top-level schema drift.
    assert payload["error"]["details"][0]["type"] == "extra_forbidden"
    assert payload["error"]["details"][0]["loc"] == [
        "body",
        "unexpected_field",
    ]