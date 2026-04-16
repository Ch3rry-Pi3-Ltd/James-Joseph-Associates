"""
Unit tests for FastAPI exception handlers.

These tests call the exception handler functions directly.

The important question is:

    "If FastAPI gives us a validation error object, do our helper functions turn
    it into the API error format we expect?"

This is different from the integration test.

The integration test checks the full request flow:

    TestClient
        -> FastAPI route
        -> validation fails
        -> custom handler runs
        -> {"error": {...}}

This unit test checks the smaller pieces directly:

    RequestValidationError
        -> serialise_validation_errors(...)
        -> request_validation_exception_handler(...)
        -> JSONResponse

The expected output shape is:

    {
        "error": {
            "code": "validation_error",
            "message": "Request validation failed.",
            "details": [...]
        }
    }
"""

import json

import pytest
from fastapi import Request, status
from fastapi.exceptions import RequestValidationError

from backend.core.errors import (
    request_validation_exception_handler,
    serialise_validation_errors,
)

def make_request() -> Request:
    """
    Build a minimal FastAPI request object for handler tests.

    The validation handler accepts a `Request` because FastAPI exception handlers
    are always called with both:

        request
        exception

    Our current handler does not inspect the request, but the object still needs
    to exist so the handler can be called with the same shape FastAPI uses.

    Returns
    -------
    Request
        Minimal request object with enough ASGI scope data for the exception
        handler.

        The fake request represents:

            POST /api/v1/example

    Notes
    -----
    - This does not start a server.
    - This does not call a real route.
    - This only builds the request object needed to call the handler directly.
    - The handler currently ignores the request, but future handlers may use it
      for request IDs, paths, logging, or tracing.

    Example
    -------
    The returned object is used like this:

        response = await request_validation_exception_handler(
            request=make_request(),
            exc=make_validation_exception(),
        )
    """

    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/api/v1/example",
            "headers":[],
        }
    )

def make_validation_exception() -> RequestValidationError:
    """
    Build a representative FastAPI request validation exception.

    The exception describes a missing request-body field:

        source_record_id

    This mimics the kind of exception FastAPI raises when a client sends a JSON
    body that does not match a Pydantic request model.

    Returns
    -------
    RequestValidationError
        Validation exception with one missing body field.

    Notes
    -----
    - This does not come from a real HTTP request.
    - It is built directly so the unit test can focus on the handler.
    - The integration test separately proves that FastAPI can produce this kind
      of error during real request handling.
    - The example is intentionally realistic because future ingestion routes
      will likely require a source-system record identifier.

    Error meaning
    -------------
    This detail:

        {
            "type": "missing",
            "loc": ("body", "source_record_id"),
            "msg": "Field required",
            "input": {}
        }

    means:

        "The request body was missing the required field `source_record_id`."

    In plain language:

    - pretend a client sent a bad request body
    - create the same kind of exception FastAPI would raise
    """

    return RequestValidationError(
        [
            {
                "type": "missing",
                "loc": ("body", "source_record_id"),
                "msg": "Field required",
                "input": {},
            }
        ]
    )

def test_serialise_validation_errors_returns_plain_error_details() -> None:
    """
    Verify that FastAPI validation details are converted into dictionaries.

    This test checks the small helper function that extracts safe validation
    details from a `RequestValidationError`.

    Notes
    -----
    - FastAPI/Pydantic already provide structured error details.
    - The helper copies those details into plain dictionaries.
    - This gives the response builder a predictable list of error detail objects.
    - The location remains a tuple at this helper stage because this test is
      checking the direct Python structure, not the final JSON response.

    Expected result
    ---------------
    The helper should return:

        [
            {
                "type": "missing",
                "loc": ("body", "source_record_id"),
                "msg": "Field required",
                "input": {}
            }
        ]
    """

    exc = make_validation_exception()
    
    details = serialise_validation_errors(exc)

    assert details == [
        {
            "type": "missing",
            "loc": ("body", "source_record_id"),
            "msg": "Field required",
            "input": {},
        }
    ]

@pytest.mark.anyio
async def test_request_validation_handler_returns_http_422() -> None:
    """
    Verify that request validation failures return HTTP 422.

    HTTP 422 means:

        "The request was understood, but the content was invalid for this route."

    That is the correct status for a JSON body that is syntactically valid but
    missing required fields.

    Notes
    -----
    - The handler is async, so the test is async.
    - `pytest.mark.anyio` lets pytest run the async test.
    - This test checks only the response status code.
    - The response body is checked in a separate test.
    """

    response = await request_validation_exception_handler(
        request=make_request(),
        exc=make_validation_exception(),
    )

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT

@pytest.mark.anyio
async def test_request_validation_handler_returns_standard_error_shape() -> None:
    """
    Verify that validation failures use the shared API error response shape.

    This test checks the final JSON body returned by the handler.

    Notes
    -----
    - FastAPI's default validation response uses a top-level `detail` key.
    - This project uses a top-level `error` object instead.
    - That keeps future Make.com and frontend error handling consistent.
    - JSON turns the Python tuple location into a JSON list.

    Expected response shape
    -----------------------
    The response should look like:

        {
            "error": {
                "code": "validation_error",
                "message": "Request validation failed.",
                "details": [
                    {
                        "type": "missing",
                        "loc": ["body", "source_record_id"],
                        "msg": "Field required",
                        "input": {}
                    }
                ]
            }
        }
    """

    response = await request_validation_exception_handler(
        request=make_request(),
        exc=make_validation_exception(),
    )

    payload = json.loads(response.body)

    assert payload["error"]["code"] == "validation_error"
    assert payload["error"]["message"] == "Request validation failed."
    assert payload["error"]["details"] == [
        {
            "type": "missing",
            "loc": ["body", "source_record_id"],
            "msg": "Field required",
            "input": {},   
        }
    ]

@pytest.mark.anyio
async def test_request_validation_handler_does_not_return_fastapi_detail_shape() -> None:
    """
    Verify that the handler does not expose FastAPI's default error envelope.

    FastAPI normally returns validation errors with this top-level shape:

        {
            "detail": [...]
        }

    The project API contract uses this shape instead:

        {
            "error": {...}
        }

    Notes
    -----
    - This test protects the public API contract.
    - Make.com and future frontend clients should look for `error`.
    - They should not need to know FastAPI's internal default error format.
    """

    response = await request_validation_exception_handler(
        request=make_request(),
        exc=make_validation_exception(),
    )

    payload = json.loads(response.body)

    assert "error" in payload
    assert "detail" not in payload