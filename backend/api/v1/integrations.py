"""
Integration endpoints for version 1 of the intelligence API.

This module contains small endpoints that sit at the boundary between the
backend and external systems such as JobAdder.

It gives the rest of the repository a stable way to verify:

- the backend has a real JobAdder OAuth callback path
- the registered redirect URI points at a live backend route
- provider callback query parameters are handled safely
- configuration readiness can be reported clearly during setup

Keeping integration endpoints in their own module makes the project easier to
extend because:

- `backend.api.router` stays focused on route registration
- JobAdder-specific HTTP handling stays separate from candidate and Make.com
  endpoints
- future provider callbacks can follow the same local pattern
- later token exchange and token storage can be added without mixing concerns

In plain language:

- this module answers the question:

    "Does the backend have a real JobAdder OAuth callback route?"

- it does not call the JobAdder token endpoint yet
- it does not store access tokens yet
- it does not create candidates or jobs
- it only handles the callback request itself
"""

from typing import Any

from fastapi import APIRouter, Query, status
from fastapi.responses import JSONResponse

from backend.schemas.errors import ApiError, ApiErrorResponse
from backend.schemas.integrations import JobAdderOAuthCallbackResponse
from backend.settings import get_settings


router = APIRouter(prefix="/integrations", tags=["integrations"])


def build_error_response(
    *,
    status_code: int,
    code: str,
    message: str,
    details: list[dict[str, Any]] | None = None,
) -> JSONResponse:
    """
    Build a standard API error response for integration endpoints.

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
    - This local helper keeps the route logic focused on callback handling.
    - The response body uses the project's normal top-level error contract.
    - The helper builds the response shape only. It does not decide when an
      error should be returned.
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


@router.get(
    "/jobadder/callback",
    response_model=JobAdderOAuthCallbackResponse,
    responses={
        400: {
            "model": ApiErrorResponse,
            "description": "JobAdder returned an OAuth error.",
        },
        422: {
            "model": ApiErrorResponse,
            "description": "Required callback query values were missing.",
        },
    },
)
def get_jobadder_oauth_callback(
    code: str | None = Query(
        default=None,
        description="One-time JobAdder authorization code.",
    ),
    state: str | None = Query(
        default=None,
        description="Optional opaque state value returned by JobAdder.",
    ),
    error: str | None = Query(
        default=None,
        description="OAuth error code returned by JobAdder, if any.",
    ),
    error_description: str | None = Query(
        default=None,
        description="Optional OAuth error description returned by JobAdder.",
    ),
) -> JobAdderOAuthCallbackResponse | JSONResponse:
    """
    Receive the JobAdder OAuth redirect callback.

    Parameters
    ----------
    code : str | None
        One-time authorization code returned by JobAdder after the user grants
        access.

    state : str | None
        Optional opaque state value returned unchanged by JobAdder.

    error : str | None
        OAuth error code returned by JobAdder when the authorization step was
        not completed successfully.

    error_description : str | None
        Optional human-readable provider error description.

    Returns
    -------
    JobAdderOAuthCallbackResponse | JSONResponse
        Success response confirming the callback route was reached.

        Standard API error response when the provider returned an OAuth error or
        when the callback is missing the expected query parameters.

    Route
    -----
    This module contributes:

        GET /api/v1/integrations/jobadder/callback

    Notes
    -----
    - This route is intentionally the first safe OAuth callback step.
    - It exists so the JobAdder developer portal can point at a real backend
      redirect URI right now.
    - It does not exchange the authorization code yet because that would spend
      the one-time code before token storage is in place.
    - It does report whether the backend has the minimum OAuth settings already
      configured for the later token-exchange step.

    Example
    -------
    A successful provider redirect would look like:

        GET /api/v1/integrations/jobadder/callback?code=abc123&state=connect-dev

    In plain language:

    - receive the provider redirect
    - reject explicit provider-side OAuth errors clearly
    - confirm whether we received an authorization code
    - report whether the backend is ready for the next OAuth step
    """

    # If JobAdder returns `error=...` in the callback query, the provider is
    # telling us the authorization step did not complete successfully.
    #   - Handle that before looking for a code.
    #   - The details are kept small and safe for debugging.
    if error is not None:
        details: list[dict[str, Any]] = [{"provider": "jobadder", "error": error}]

        if error_description:
            details.append({"provider_error_description": error_description})

        if state:
            details.append({"state": state})

        return build_error_response(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="unauthorized",
            message="JobAdder authorization was not completed.",
            details=details,
        )

    # A successful callback should include a one-time `code`.
    #   - We do not expose the raw code back to the caller.
    #   - We do make it explicit when the callback reached the backend without
    #     the expected value.
    if code is None or code.strip() == "":
        return build_error_response(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            code="validation_error",
            message="JobAdder authorization code is required.",
            details=[{"query_param": "code", "reason": "missing_or_empty"}],
        )

    settings = get_settings()

    # The later token exchange will need all three values:
    # - client ID
    # - client secret
    # - exact redirect URI
    #
    # If any of these are missing, the route is still useful because the
    # redirect URI is now real and testable, but the backend is not yet ready to
    # complete the full OAuth flow.
    oauth_configuration_ready = all(
        [
            settings.jobadder_client_id.strip() != "",
            settings.jobadder_client_secret.strip() != "",
            settings.jobadder_redirect_uri.strip() != "",
        ]
    )

    next_step = (
        "The callback route is live and the OAuth settings are present. The next "
        "step is to add the server-side token exchange and token storage."
        if oauth_configuration_ready
        else (
            "The callback route is live. The next step is to set "
            "JOBADDER_CLIENT_ID, JOBADDER_CLIENT_SECRET, and "
            "JOBADDER_REDIRECT_URI, then add the server-side token exchange and "
            "token storage."
        )
    )

    return JobAdderOAuthCallbackResponse(
        status="received",
        message="JobAdder authorization callback received.",
        authorization_code_received=True,
        oauth_configuration_ready=oauth_configuration_ready,
        state=state,
        next_step=next_step,
    )


__all__ = ["router"]
