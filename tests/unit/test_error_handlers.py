"""
Unit tests for FastAPI exception handlers.

These tests verify that framework-level validation errors are converted into the
project's standard API error response shape.

They focus on:

- serialising FastAPI validation details
- returning HTTP 422 for request validation failures
- returning the shared `ApiErrorResponse` shape
- preserving safe validation details for clients

In plain language:

- this module answers the question:

    "When FastAPI rejects a bad request, do we translate that failure into our
    API error format?"
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

    Returns
    -------
    Request
        Request object with enough ASGI scope datafor the exception handler.

    Notes
    -----
    - The current validation handler does not inspect the request.
    - FastAPI still passes a request object to exception handlers.
    - This helper keeps the test setup explicit and reusable.

    In plain language:

    - create the smallest fake request needed to call the handler directly
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

    Returns
    -------
    RequestValidationError
        Validation exception with one missing body field.

    Notes
    -----
    - This mimics the kind of error FastAPI raises when request input fails
      validation.
    - The example says that `source_record_id` was expected in the JSON body but
      was missing.

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

    Notes
    -----
    - FastAPI/Pydantic already provide structured error details.
    - The helper copies those details into plain dictionaries.
    - This gives the response builder a predictable list of error detail objects.
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

    Notes
    -----
    - HTTP 422 means the request was syntactically valid but semantically
      invalid for this endpoint.
    - In FastAPI, this is the normal status code for request validation errors.
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

    Notes
    -----
    - FastAPI's default validation response uses a top-level `detail` key.
    - This project uses a top-level `error` object instead.
    - That keeps future Make.com and frontend error handling consistent.
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

    Notes
    -----
    - The default FastAPI validation response usually contains `detail`.
    - Out public API contract should expose `error` instead.
    """

    response = await request_validation_exception_handler(
        request=make_request(),
        exc=make_validation_exception(),
    )

    payload = json.loads(response.body)

    assert "error" in payload
    assert "detail" not in payload