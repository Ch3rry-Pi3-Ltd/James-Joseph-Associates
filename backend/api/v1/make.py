"""
Make.com integration test endpoints for version 1 of the intelligence API.

This module defines a small protected endpoint that Make.com can call before the
real source-record ingestion endpoint exists.

It gives the rest of the repository a stable way to test:

- Make.com can call the deployed backend
- Make.com can send bearer-token authentication
- Make.com can send an `Idempotency-Key`
- Make.com request metadata can be read by the backend
- the backend can return a controlled JSON response

Keeping this endpoint separate from real business ingestion makes the project
easier to extend because:

- we can prove the Make.com-to-backend connection safely
- we do not need real recruitment data yet
- we do not need Supabase writes yet
- we do not pretend test payloads are real source records
- future source-record endpoints can reuse the same security and idempotency
  helpers

In plain language:

- this module answers the question:

    "Can Make.com securely send a test event to our backend?"

- it does not store data
- it does not create candidates
- it does not create jobs
- it does not call LangChain
- it does not call LangGraph
- it does not run a real workflow yet

Notes
-----
- This is a temporary integration proving endpoint.
- The real ingestion endpoint should come later, probably as:

    POST /api/v1/source-records

- This endpoint should still use real security and idempotency checks because it
  is testing the same request pattern that Make.com will use later.
- The expected Make.com bearer token should come from settings.
- Until `make_api_token` is added to the `backend.settings.Settings`, this endpoint
  will reject protected calls as not configured.
"""

from typing import Any, Literal

from fastapi import APIRouter, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from backend.core.http import IDEMPOTENCY_KEY_HEADER, get_request_metadata
from backend.core.idempotency import (
    IdempotencyFailureReason,
    build_idempotency_metadata,
    get_request_idempotency_key,
)
from backend.core.security import check_request_bearer_token
from backend.schemas.errors import ApiError, ApiErrorResponse
from backend.settings import get_settings


class MakeTestEventRequest(BaseModel):
    """
    Request body accepted by the Make.com test endpoint.

    Attributes
    ----------
    event_type : str
        Name of the test event being sent.

        This helps distinguish one test payload from another when looking at
        Make.com run history or backend logs later.

    payload : dict[str, Any]
        Small JSON object sent by Make.com.

        This should be test-only data. It should not contain real candidate,
        client, or sensitive recruitment data.

    Notes
    -----
    - This schema is intentionally generic.
    - It is not the future source-record schema.
    - It exists only to prove the Make.com request path.
    - Once real ingestion starts, source-record payloads should use a dedicated
      schema in a separate module.

    Example
    -------
    Make.com could send:

        {
            "event_type": "manual_make_test",
            "payload": {
                "message": "Hello from Make.com"
            }
        }

    In plain language:

    - identify the test event
    - carry a small test payload
    """

    # Keep request bodies strict.
    #   - If Make.com sends unexpected top-level fields, tests and endpoint
    #     behaviour should make that obvious.
    model_config = ConfigDict(extra="forbid")

    # `event_type` gives the test request a short label.
    #   - This is useful when Make.com scenarios evolve and we want to know which
    #     test event was sent.
    event_type: str = Field(
        default="make_test_event",
        min_length=1,
        description="Name of the Make.com test event.",
    )

    # `payload` is deliberately generic for this temporary endpoint.
    #   - It lets Make.com prove it can send JSON without committing us to the
    #     future source-record schema yet.
    payload: dict[str, Any] = Field(
        default_factory=dict,
        description="Small test payload sent by Make.com.",
    )


class MakeTestEventResponse(BaseModel):
    """
    Response returned when a Make.com test event is accepted.

    Attributes
    ----------
    status : Literal["accepted"]
        Fixed status confirming the test request passed the foundation checks.

    message : str
        Short human-readable explanation.

    event_type : str
        Event type received from the request body.

    idempotency_key : str
        Normalised idempotency key received from the request.

    payload_hash : str
        Stable hash of the received request payload.

        This proves the backend can fingerprint the request body for future
        duplicate/retry handling.

    request_metadata : dict[str, str]
        Safe request metadata read from recognised headers.

        This can include values such as:

        - `source_system`
        - `make_run_id`
        - `request_id`

    Notes
    -----
    - This response does not mean a real business workflow has run.
    - It only means the protected Make.com test request was accepted.
    - The payload hash is returned for visibility during early testing.
    """

    # Keep the response strict so clients see a predictable shape.
    model_config = ConfigDict(extra="forbid")

    status: Literal["accepted"] = Field(
        description="Fixed status for accepted Make.com test events.",
    )

    message: str = Field(
        min_length=1,
        description="Human-readable test acceptance message.",
    )

    event_type: str = Field(
        min_length=1,
        description="Event type received from Make.com.",
    )

    idempotency_key: str = Field(
        min_length=1,
        description="Normalised idempotency key supplied with the request.",
    )

    payload_hash: str = Field(
        min_length=1,
        description="Stable hash of the received request body.",
    )

    request_metadata: dict[str, str] = Field(
        default_factory=dict,
        description="Safe request metadata extracted from recognised headers.",
    )


# Create a router for Make.com-related endpoints.
#   - The `/make` prefix means this module contributes routes such as:
#
#       /api/v1/make/test-event
#
#   - The `/api/v1` part is added by `backend.api.router`.
router = APIRouter(prefix="/make", tags=["make"])


def build_error_response(
    *,
    status_code: int,
    code: str,
    message: str,
    details: list[dict[str, Any]] | None = None,
) -> JSONResponse:
    """
    Build a standard API error response for this endpoint.

    Parameters
    ----------
    status_code : int
        HTTP status code to return.

    code : str
        Public API error code.

    message : str
        Safe human-readable error message.

    details : list[dict[str, Any]] | None
        Optional safe structured error details.

    Returns
    -------
    JSONResponse
        FastAPI response containing the standard `{"error": ...}` shape.

    Notes
    -----
    - This local helper avoids repeating the error response construction several
      times in the endpoint.
    - A shared response helper can be moved to `backend.core.responses` later if
      more endpoints need the same pattern.
    - Details must stay safe to return to Make.com.

    In plain language:

    - choose the HTTP status
    - choose the API error code
    - return the project's normal error shape
    """

    error_response = ApiErrorResponse(
        error=ApiError(
            code=code,
            message=message,
            details=details or [],
        )
    )

    return JSONResponse(
        status_code=status_code,
        content=error_response.model_dump(),
    )


@router.post("/test-event", response_model=MakeTestEventResponse)
def receive_make_test_event(
    request: Request,
    body: MakeTestEventRequest,
) -> MakeTestEventResponse | JSONResponse:
    """
    Accept a protected test event from Make.com.

    Parameters
    ----------
    request : Request
        FastAPI request object.

        This is needed so the endpoint can read headers such as:

        - `Authorization`
        - `Idempotency-Key`
        - `X-Source-System`
        - `X-Make-Run-Id`
        - `X-Request-Id`

    body : MakeTestEventRequest
        Test JSON payload sent by Make.com.

    Returns
    -------
    MakeTestEventResponse | JSONResponse
        Success response when the request passes security and idempotency checks.

        Standard API error response when a required check fails.

    Required headers
    ----------------
    Make.com should eventually send:

        Authorization: Bearer <MAKE_API_TOKEN>
        Idempotency-Key: <stable-test-event-key>

    Useful optional headers
    -----------------------
    Make.com can also send:

        X-Source-System: make
        X-Make-Run-Id: <make-run-id>
        X-Request-Id: <request-id>

    Notes
    -----
    - This endpoint does not store anything.
    - This endpoint does not run a real workflow.
    - If this endpoint works from Make.com, the next step is a real
      source-record endpoint.

    In plain language:

    - check the caller has the right token
    - check the request has a retry key
    - fingerprint the payload
    - return a clear accepted response
    """

    settings = get_settings()

    # Read the expected Make.com token from settings.
    #   - `getattr` keeps this endpoint import-safe before the setting is added.
    #   - Until `make_api_token` exists and is configured, protected calls should
    #     fail closed instead of accidentally accepting requests.
    expected_token = getattr(settings, "make_api_token", "")

    if expected_token == "":
        return build_error_response(
            status_code=status.HTTP_401_UNAUTHORIZED,
            code="unauthorized",
            message="Make.com API access is not configured.",
            details=[
                {
                    "setting": "MAKE_API_TOKEN",
                    "reason": "missing_or_empty",
                }
            ],
        )

    # Check the bearer token sent by Make.com.
    #   - This validates the `Authorization: Bearer ...` header shape and token.
    #   - If the token is missing, malformed, or wrong, reject the request before
    #     looking at the body as a real event.
    security_result = check_request_bearer_token(
        request=request,
        expected_token=expected_token,
    )

    if not security_result.is_authorised:
        return build_error_response(
            status_code=status.HTTP_401_UNAUTHORIZED,
            code="unauthorized",
            message="Request is not authorised.",
            details=[
                {
                    "reason": str(security_result.reason),
                }
            ],
        )

    # Require an idempotency key.
    #   - This mirrors how future Make.com write requests should behave.
    #   - A retry key is needed before we accept POST-style workflow calls.
    idempotency_key_or_reason = get_request_idempotency_key(request)

    if isinstance(idempotency_key_or_reason, IdempotencyFailureReason):
        return build_error_response(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            code="validation_error",
            message="Idempotency key is required for this request.",
            details=[
                {
                    "header": IDEMPOTENCY_KEY_HEADER,
                    "reason": str(idempotency_key_or_reason),
                }
            ],
        )

    # Collect safe request metadata.
    #   - This lets us confirm Make.com can send useful operational context.
    #   - Missing optional headers are simply omitted.
    request_metadata = get_request_metadata(request)

    # Build local idempotency metadata.
    #   - This does not store anything yet.
    #   - It proves we can normalise the key and fingerprint the incoming body.
    idempotency_metadata = build_idempotency_metadata(
        key=idempotency_key_or_reason,
        payload=body.model_dump(),
    )

    return MakeTestEventResponse(
        status="accepted",
        message="Make.com test event accepted.",
        event_type=body.event_type,
        idempotency_key=idempotency_metadata.key,
        payload_hash=idempotency_metadata.payload_hash,
        request_metadata=request_metadata,
    )


__all__ = ["router"]
