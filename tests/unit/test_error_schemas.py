"""
Unit tests for shaped API error schemas.

These tests check the Pydantic models that define the project's standard API
error response contract.

The important question is:

    "Can clients rely on one predictable API error response shape?"

That matters because future clients should not need to understand the internal
details of FastAPI, Supabase, LangChain, LangGraph, or any individual route.

They should be able to look for one top-level key:

    error

and then read predictable fields inside it:

    code
    message
    details

The expected output shape is:

    {
        "error": {
            "code": "validation_error",
            "message": "Request body failed validation.",
            "details": []
        }
    }

These tests focus on:

- the standard top-level error shape
- default empty error details
- safe structured error details
- strict rejection of unexpected fields
- constrained public error codes

In plain language:

- this file tests the error response template
- it does not test FastAPI route handling
- it does not test exception handlers
- it does not send HTTP requests
- it only tests the schema objects directly
"""

import pytest
from pydantic import ValidationError

from backend.schemas.errors import ApiError, ApiErrorResponse

def test_api_error_response_serialises_to_standard_shape() -> None:
    """
    Verify that the standard error response serialises as expected.

    This test builds the smallest normal API error response and checks the exact
    dictionary shape produced by Pydantic.

    Notes
    -----
    - Future routes should be able to return this shape consistently.
    - Make.com and future frontend clients can parse `error.code` and
      `error.message` without route-specific handling.
    - `details` should default to an empty list when there is no extra context.
    - This test protects the public response contract from accidental shape
      changes.

    Expected response shape
    -----------------------
    The response should serialise to:

        {
            "error": {
                "code": "validation_error",
                "message": "Request body failed validation.",
                "details": []
            }
        }

    In plain language:

    - create one API error
    - wrap it in the standard API error response
    - confirm it turns into the JSON-ready shape clients expect
    """

    # Build the inner error object
    #   - `code` gives clients a stable machine-readable reason.
    #   - `message` gives humans a short explanation.
    #   - `details` is not passed here, so it should use its default value.
    response = ApiErrorResponse(
        error=ApiError(
            code="validation_error",
            message="Request body failed validation."
        )
    )

    # `model_dump()` converts the Pydantic model into a plain Python dictionary
    #   - This is close to the structure FastAPI would later serialise as JSON.
    #   - The important point is that `details` appears as an empty list by
    #     default, not as `None` and not omitted.
    assert response.model_dump() == {
        "error": {
            "code": "validation_error",
            "message": "Request body failed validation.",
            "details": [],
        }
    }

def test_api_error_details_can_hold_safe_structured_context() -> None:
    """
    Verify that error details can carry safe structured metadata.

    Some errors need more context than a short code and message.

    For example, an idempotency conflict may need to explain which request header
    caused the conflict and why.

    Notes
    -----
    - Details are useful for validation errors and idempotency conflicts.
    - Details should stay safe to return to clients.
    - Secrets, stack traces, and raw sensitive source data do not belong here.
    - The schema allows a list of dictionaries so future handlers can include
      structured context without inventing a new response shape.

    Example detail
    --------------
    A safe detail object might look like:

        {
            "field": "Idempotency-Key",
            "reason": "Key was reused with a different payload."
        }

    In plain language:

    - keep the public error shape the same
    - add safe extra information inside `details`
    """

    # Build an error with one structured detail object
    #   - This mirrors the kind of extra context we may return later for
    #     validation errors, duplicate requests, or unsupported source systems.
    response = ApiErrorResponse(
        error=ApiError(
            code="idempotency_conflict",
            message="Request conflicts with an existing idempotency key.",
            details=[
                {
                    "field": "Idempotency-Key",
                    "reason": "Key was reused with a different payload.",
                }
            ],
        )
    )

    # The detail should be preserved exactly
    #   - The schema should not flatten it.
    #   - The schema should not discard it.
    assert response.error.details == [
        {
            "field": "Idempotency-Key",
            "reason": "Key was reused with a different payload.",
        }
    ]

def test_api_error_rejects_unknown_error_codes() -> None:
    """
    Verify that unsupported error codes fail validation.

    Error codes are part of the public API contract.

    That means we should not accidentally return one-off values such as:

        surprise_error
        random_failure
        database_went_boom

    Instead, handlers should choose from the supported list defined in the
    schema.

    Notes
    -----
    - Error codes are intentionally constrained.
    - This prevents accidental one-off codes from leaking into the API contract.
    - If a new error code is genuinely needed, it should be added deliberately
      to the schema and documented in the API contract.
    - Stable error codes are useful for Make.com scenarios and future frontend
      logic because clients can branch on them safely.

    In plain language:

    - unknown error names should fail loudly during development
    - they should not silently become part of the API
    """

    # `surprise_error` is not part of the allowed public error code list
    #   - Pydantic should reject it when the model is created.
    #   - That tells us the schema is enforcing the contract.
    with pytest.raises(ValidationError):
        ApiError(
            code="surprise_error",
            message="This code is not part of the public contract.",
        )

def test_api_error_response_rejects_unexpected_fields() -> None:
    """
    Verify that error responses do not silently accept unexpected fields.

    The public error response should stay small and predictable.

    For example, this should not be allowed:

        {
            "error": {...},
            "debug": "this should not be returned"
        }

    Notes
    -----
    - The error contract should change deliberately.
    - If future endpoints need more fields, the schema and tests should be
      updated explicitly.
    - This protects against accidentally exposing debug data.
    - This also protects clients from receiving inconsistent response shapes.

    In plain language:

    - only the fields defined by the schema should be accepted
    - accidental extra fields should raise a validation error
    """

    # Try to add a top-level `debug` field that is not part of the response schema
    #   - This should fail if the model is correctly configured.
    #   - That is useful because debug fields can accidentally expose internal
    #     implementation details.
    with pytest.raises(ValidationError):
        ApiErrorResponse(
            error=ApiError(
                code="not found",
                message="The requested entity was not found.",
            ),
            debug="this should not be returned",
        )