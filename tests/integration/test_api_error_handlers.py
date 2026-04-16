"""
Integration tests for API validation error handling.

These tests verify that FastAPI request flow, not just the helper function.

The important question is:

    "If a real HTTP request is invalid, does the API return our standard error
    response shape?"

To test that without building a real data endpoint yet, this file creates a tiny
test-only FastAPI app with one fake route:

    POST /example

That fake route requires a JSON body containing:

    source_record_id

The test deliberately sends an empty JSON body:

    {}

That should make FastAPI reject the request before the route handler runs.

The expected flow is:

    invalid request
        -> FastAPI validates request body
        -> required field is missing
        -> FastAPI raises RequestValidationError
        -> our custom handler catches it
        -> response is returned as {"error": {...}}

This proves that the exception handler is correctly wired into FastAPI.
"""

from fastapi import FastAPI, status
from fastapi.exceptions import RequestValidationError
from fastapi.testclient import TestClient
from pydantic import BaseModel, Field

from backend.core.errors import request_validation_exception_handler

class ExampleRequest(BaseModel):
    """
    Minimal request body used only for validation error integration tests.

    This model creates a controlled validation failure. It gives the test app one
    required request-body field so we can deliberately send an invalid payload
    and confirm that FastAPI routes the failure through our custom exception
    handler.

    Attributes
    ----------
    source_record_id: str
        Required field used to trigger validation when missing.

        In the test, we send an empty JSON body:

            {}

        Because `source_record_id` is required, FastAPI should reject that body
        before the route handler runs.

    Notes
    -----
    - This is not a production API schema.
    - It exists only inside the test module.
    - It should not be imported by application code.
    - The real source-record schema can be designed later when ingestion begins.
    - The field name is intentionally realistic because future ingestion routes
      will likely need a source-system record identifier.
    - The purpose here is not to test source-record ingestion. The purpose is to
      test validation error formatting.

    Example
    -------
    A valid payload for this test-only model would be:

        {
            "source_record_id": "example-123
        }

    The tests deliberately send an invalid payload instead:

        {}

    That invalid payload should produce a validation error shape like:

        {
            "error": {
                "code": "validation_error",
                "message": "Request validation failed.",
                "details": [...]
            }
        }
    """

    # This field is required on purpose.
    #   - The test sends `{}` as the request body.
    #   - Because `{}` does not contain `source_record_id`, FastAPI raises
    #     `RequestValidationError` before the endpoint function runs.
    source_record_id: str = Field(min_length=1)

def create_test_app() -> FastAPI:
    """
    Create a minimal FastAPI app with the project validation handler registered.

    This app exists only for integration testing the error-handling path. It is
    deliberately smaller than the real application so the test can focus on one
    behaviour:

        invalid request body -> custom validation error response

    Returns
    -------
    FastAPI
        Test app with one route that requires a validated request body.

        The route is:

            POST /example

        It expects a body matching `ExampleRequest`.

    Notes
    -----
    - This avoids depending on a real production POST endpoint.
    - It proves the exception handler works end-to-end through FastAPI itself.
    - It uses the same validation handler registered in `backend.main`.
    - Once real POST endpoints exist, we can add route-specific integration tests.
    - This app should stay local to the test file and should not be imported by
      application code.

    Request flow
    ------------
    The test request moves through this path:

        TestClient
            -> POST /example
            -> FastAPI request validation
            -> RequestValidationError
            -> request_validation_exception_handler
            -> {"error": {...}}

    Example
    -------
    The test sends:

        {}

    The route expects:

        {
            "source_record_id": "example-123"
        }

    Because the required field is missing, FastAPI should call our custom
    exception handler before the endpoint function runs.
    """

    app = FastAPI()

    # Register the same validation handler used by the real application
    #   - This is the key behaviour under test
    #   - If this registration is missing, FastAPI will return its default
    #     validation error shape:
    #
    #   {"detail": [...]}
    #
    # With this registration, validation errors should return our API contract:
    #
    #   {"error": {...}}
    app.add_exception_handler(
        RequestValidationError,
        request_validation_exception_handler
    )

    @app.post("/example")
    def example_endpoint(payload: ExampleRequest) -> dict[str, str]:
        """
        Return a success response for valid requests.

        Parameters
        ----------
        payload : ExampleRequest
            Validated request body.

            In these tests, invalid requests should fail before this parameter is
            ever passed into the function.

        Returns
        -------
        dict[str, str]
            Echo response containing the validated `source_record_id`.

        Notes
        -----
        - This is a test-only endpoint
        - Invalid requests should never reach this function.
        - The test sends `{}`, so FastAPI should reject the request before this
          route handler executes.
        - If this function runs for the invalid test case, validation did not
          happen as expected.
        """

        return {"source_record_id": payload.source_record_id}
    
    return app

def test_validation_error_uses_standard_error_response_shape() -> None:
    """
    Verify that invalid request bodies return the standard error response shape.

    This test proves that FastAPI's request validation failure is translated into
    the project's public API error contract.

    Notes
    -----
    - The request body is empty.
    - `source_record_id` is required.
    - FastAPI should raise `RequestValidationError`.
    - Our handler should convert that into an `error` response.
    - The response should use HTTP 422 because the request body is structurally
      valid JSON but semantically invalid for the endpoint.

    Expected response shape
    -----------------------
    The response should look like:

        {
            "error": {
                "code": "validation_error",
                "message": "Request validation failed.",
                "details": [...]
            }
        }
    """
    # Create a fake HTTP client that can send requests to our fake FastAPI app
    #   - TestClient is a FastAPI testing tool
    #   - TestClient skips the real server and lets the test call the app directly
    #     in memory
    #   - `create_test_app()` builds a tiny FastAPI app just for this test.
    client = TestClient(create_test_app())

    # Send an intentionally invalid body
    #   - The body is valid JSON, but it is missing the required `source_record_id`
    #     field. That should trigger FastAPI request validation.
    response = client.post("/example", json={})

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT

    payload = response.json()

    assert payload["error"]["code"] == "validation_error"
    assert payload["error"]["message"] == "Request validation failed."

    # The first validation detail should identify the missing body field
    #   - FastAPI reports location as a path. Here, the error location means:
    #
    #       body -> source_record_id
    #
    #   - In plain language:
    #
    #       "The request body was missing `source_record_id`."
    assert payload["error"]["details"][0]["type"] == "missing"
    assert payload["error"]["details"][0]["loc"] == ["body", "source_record_id"]

def test_validation_error_does_not_use_fastapi_default_detail_envelope() -> None:
    """
    Verify that the public response does not use FastAPI's default `detail` key.

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
    - Make.com and future frontend clients should be able to look for `error`.
    - They should not need to know FastAPI's internal default error format.
    """

    # Create a fake HTTP client that can send requests to our fake FastAPI app
    #   - TestClient is a FastAPI testing tool
    #   - TestClient skips the real server and lets the test call the app directly
    #     in memory
    #   - `create_test_app()` builds a tiny FastAPI app just for this test.
    client = TestClient(create_test_app())

    # Send an intentionally invalid body
    #   - The body is valid JSON, but it is missing the required `source_record_id`
    #     field. That should trigger FastAPI request validation.
    response = client.post("/example", json={})

    payload = response.json()

    # The custom handler should expose the project-level error envelope
    assert "error" in payload

    # The default FastAPI validation envelope should not leak through
    assert "detail" not in payload
    