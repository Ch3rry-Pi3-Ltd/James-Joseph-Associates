"""
FastAPI exception handlers for the intelligence API.

This module converts framework-level exceptions into the project's standard API
error response shape.

It gives the rest of the repository a stable way to talk about:

- request validation failures
- safe error response formatting
- converting FastAPI exceptions into `ApiErrorResponse`
- keeping framework error details away from endpoint modules

Keeping exception handling in one place makes the backend easier to extend
because:

- `backend.main` can register handlers during app setup
- endpoint modules can focus on business behaviour
- tests can verify one consistent error contract
- future clients and Make.com workflows can parse failures predictably

In plain language:

- this module answers the question:

    "How should FastAPI errors be shaped before they leave the API?"

- it does not define Pydantic schemas
- it does not define route handlers
- it does not log errors yet
- it does not expose stack traces or secret values

Notes
-----
- FastAPI raises `RequestValidationError` when request input fails validation.
- FastAPI's default response shape is useful, but it is not our API contract.
- This module maps validation failures into `ApiErrorResponse`.
- More handlers can be added later for auth, not-found errors, domain errors,
  and unexpected internal errors.
"""

from typing import Any

from fastapi import Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from backend.schemas.errors import ApiError, ApiErrorResponse

def serialise_validation_errors(
    exc: RequestValidationError,
) -> list[dict[str, Any]]:
    """
    Convert FastAPI validation errors into JSON-safe dictionaries.

    Parameters
    ----------
    exc : RequestValidationError
        FastAPI validation exception raised when request input is invalid.

    Returns
    -------
    list[dict[str, Any]]
        List of safe validation error details.

    Notes
    -----
    - `exc.errors()` returns structured validation details from Pydantic.
    - Those details are usually already JSON-compatible.
    - This helper keeps the conversion in one place so the exception handler
      stays focused on building the API response.
    - The output should remain safe to return to clients.

    Example
    -------
    A missing required field might produce a detail object like:

        {
            "type": "missing",
            "loc": ["body", "source_record_id],
            "msg": "Field required",
            "input": {}
        }

    This is saying:

        "I expected a required field called `source_record_id` in the request 
        body, but the body you sent did not contain it."

    In plain language:

    - take FastAPI's validation details
    - convert each detail to a plain dictionary
    - return the list for the standard API error response
    """

    # FastAPI/Pydantic already provide validation details as dictionaries.
    #   - We copy each item into a plain `dict` so callers receive a normal mutable
    #     JSON-style structure rather than depending on the exact object type
    #     returned by the framework.
    return [dict(error) for error in exc.errors()]

async def request_validation_exception_handler(
        request: Request,
        exc: RequestValidationError,
) -> JSONResponse:
    """
    Return the standard API error response for request validation failures.

    Parameters
    ----------
    request : Request
        FastAPI request object.

        The request is accepted because FastAPI exception handlers receive it,
        even though this first implementation does not need to read from it.

    exc : RequestValidationError
        Validation exception raised by FastAPI/pydantic.

    Notes
    -----
    - This handler is intended for invalid request input.
    - It should not expose stack traces.
    - It should not expose secrets.
    - It should preserve enough validation detail for clients to fix the request.
    - It should return the samme top-level error shape as future API errors.

    Response shape
    --------------
    The returned body should look like:

        {
            "error": {
                "code": "validation_error",
                "message": "Request validation failed.",
                "details": [...]
            }
        
        }

    In plain language:

    - catch FastAPI's validation failure
    - translate it into our API error format
    - return HTTP 422
    """

    # The request object is part of FastAPI's handler signature.
    #   - This first handler does not need it yet, but keeping the parameter makes
    #     the function compatible with `app.add_exception_handler(...)`.
    _ = request

    error_response = ApiErrorResponse(
        error=ApiError(
            code="validation_error",
            message="Request validation failed.",
            details=serialise_validation_errors(exc),
        )
    )

    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        content=error_response.model_dump(),
    )

__all__ = [
    "request_validation_exception_handler",
    "serialise_validation_errors",
]