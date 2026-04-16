"""
Unit tests for shaped API error schemas.

These tests verify the standard error response contract before future endpoints
start returning errors.

They focus on:

- the standard top-level error shape
- default empty error details
- strict rejection of unexpected fields
- constrained error codes

In plain language:

- this module answers the question:

    "Can clients rely on one predictable API error response shape?"
"""

import pytest
from pydantic import ValidationError

from backend.schemas.errors import ApiError, ApiErrorResponse

def test_api_error_response_serialises_to_standard_shape() -> None:
    """
    Verify that the standard error response serialises as expected.

    Notes
    -----
    - Future routes should be able to return this shape consistently.
    - Make.com and future frontend clients can then parse `error.code` and
      `error.message` without route-specific handling.
    """

    response = ApiErrorResponse(
        error=ApiError(
            code="validation_error",
            message="Request body failed validation."
        )
    )

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

    Notes
    -----
    - Details are useful for validation errors and idempotency conflicts.
    - Details should stay safe to return to clients.
    - Secrets, stack traces, and raw sensitive source data do not belong here.
    """

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

    assert response.error.details == [
        {
            "field": "Idempotency-Key",
            "reason": "Key was reused with a different payload.",
        }
    ]

def test_api_error_rejects_unknown_error_codes() -> None:
    """
    Verify that unsupported error codes fail validation.

    Notes
    -----
    - Error codes are intentionally constrained.
    - This prevents accidental one-off codes from leaking into the API contract.
    """

    with pytest.raises(ValidationError):
        ApiError(
            code="surprise_error",
            message="This code is not part of the public contract.",
        )

def test_api_error_response_rejects_unexpected_fields() -> None:
    """
    Verify that error responses do not silently accept unexpected fields.

    Notes
    -----
    - The error contract should change deliberately.
    - If future endpoints need more fields, the schema and tests should be
      updated explicitly.
    """

    with pytest.raises(ValidationError):
        ApiErrorResponse(
            error=ApiError(
                code="not found",
                message="The requested entity was not found.",
            ),
            debug="this should not be returned",
        )