"""
Share API error response schemas.

This module the standard error shape that future API endpoints should
return when something goes wrong.

It gives the rest of the repository a stable way to talk about:

- validation errors
- authentication and permission failures
- missing resources
- idempotency conflicts
- ingestion quarantine decisions
- matching and workflow failures

Keeping error schemas in one place makes the project easier to extend because:

- endpoint modules can reuse the same error response shape
- tests can assert one consistent contract
- Make.com can parse failures predictably
- future frontend clients can display errors without special-casing every route

In plain language:

- this module answers the question:

    "What should an API error look like?"

- it does not decide when an error should be raised
- it does not contain route handlers
- it does not log errors
- it does not expose internal exception details

Notes
-----
- These are Pydantic schemas, not exception classes.
- FastAPI can use these models in route response documentation later.
- The first version is intentionally small.
- Internal stack traces and secret values must never be returned in these
  response models.
"""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

ApiErrorCode = Literal[
    "validation_error",
    "unauthorized",
    "forbidden",
    "not_found",
    "conflict",
    "idempotency_conflict",
    "unsupported_source_system",
    "matching_failed",
    "approval_required",
    "internal_error",
]

class ApiError(BaseModel):
    """
    Structured description of one API error.

    Attributes
    ----------
    code : ApiErrorCode
        Stable machine-readable error code.

        Clients should use this for branching behaviour instead of parsing the
        human-readable message.

    message : str
        Human-readable error summary.

        This should be safe to show to operators or clients. It should not
        include secrets, stack traces, or raw sensitive data.

    details : list[dict[str, Any]]
        Optional structured details about the error.

        This can hold field-level validation messages, conflict metadata, or
        safe debugging context.

    Notes
    -----
    - `code` is intentionally constrained to know values.
    - `message` must not be empty.
    - `details` defaults to an empty list so clients can always treat it as a
      list without checking for null.
    """

    # Keep the error object strict
    #   - If a future endpoint accidentally returns extra fields, Pydantic should
    #     reject that shape during tests rather than silently changing the contract
    #     consumed by Make.com or frontend clients.
    model_config = ConfigDict(extra="forbid")

    # `code` is the stable value machines should care about
    #   - The message can change for clarity, but the code should remain stable
    #     enough for API clients and workflow tooks to branch on.
    code: ApiErrorCode = Field(
        description="Stable machine-readable error code."
    )

    # `message` is for humans
    #   - Keep it short, useful, and safe. Detailed internals belong in server logs,
    #     not in the API response body.
    message: str = Field(
        min_length=1,
        description="Safe human-readable error message."
    )

    # `details` is always a list
    #   - This avoids nullable response handling for clients. For simple errors,
    #     return an empty list. For validation errors, include safe field-level
    #     details.
    details: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Optional safe structured error details."
    )

class ApiErrorResponse(BaseModel):
    """
    Standard API error response wrapper.

    Attributes
    ----------
    error : ApiError
        Structured error payload.

    Notes
    -----
    - The response is wrapped under an `error` key so every failure response has
      the same top-level shape:

        {
            "error": {
                "code": "validation_error",
                "message": "Request body failed validation.",
                "details": []
            }
        }
      
    In plain language:

    - one top-level `error` object
    - one stable `code`
    - one safe human-readable `message`
    - optional structured `details`
    """

    # Keep the top-level response strict for the same reason as `ApiError`.
    #   - A stable top-level shape makes errors easier to parse in Make.com,
    #     scripts, tests, and future frontend components.
    model_config = ConfigDict(extra="forbid")

    error: ApiError = Field(
        description="Structured API error payload.",
    )

__all__ = ["ApiError", "ApiErrorCode", "ApiErrorResponse"]