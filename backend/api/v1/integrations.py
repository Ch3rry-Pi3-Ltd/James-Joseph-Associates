"""
Integration endpoints for version 1 of the intelligence API.

This module contains small endpoints that sit at the boundary between the
backend and external systems such as JobAdder.

It gives the rest of the repository a stable way to verify:

- the backend has a real JobAdder OAuth callback path
- the backend can build a real JobAdder approval URL
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

    "Does the backend have the pieces needed to start the JobAdder OAuth flow?"

- it exchanges the returned JobAdder authorization code server-side
- it saves the returned JobAdder token set in Postgres
- it does not create candidates or jobs
- it only handles the approval-link and OAuth callback HTTP steps
"""

from typing import Any

from fastapi import APIRouter, Query, status
from fastapi.responses import JSONResponse

from backend.db.jobadder_oauth import save_jobadder_oauth_connection
from backend.schemas.errors import ApiError, ApiErrorResponse
from backend.schemas.integrations import (
    JobAdderAuthorizationUrlResponse,
    JobAdderOAuthConnectionSavedResponse,
)
from backend.services.jobadder_oauth import (
    JobAdderOAuthExchangeError,
    build_jobadder_authorization_url,
    exchange_jobadder_authorization_code,
    has_jobadder_oauth_configuration,
    has_jobadder_token_exchange_configuration,
)


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
    "/jobadder/authorize",
    response_model=JobAdderAuthorizationUrlResponse,
    responses={
        401: {
            "model": ApiErrorResponse,
            "description": "JobAdder OAuth settings are not configured.",
        }
    },
)
def get_jobadder_authorization_url(
    state: str | None = Query(
        default="connect-jobadder-dev",
        description="Optional opaque state value to include in the approval URL.",
    ),
) -> JobAdderAuthorizationUrlResponse | JSONResponse:
    """
    Return a ready-to-use JobAdder approval URL.

    Parameters
    ----------
    state : str | None
        Optional opaque value that JobAdder should return unchanged in the
        callback later.

    Returns
    -------
    JobAdderAuthorizationUrlResponse | JSONResponse
        Success response containing the approval URL.

        Standard API error response if the minimum JobAdder OAuth settings are
        not configured.

    Route
    -----
    This module contributes:

        GET /api/v1/integrations/jobadder/authorize

    Notes
    -----
    - This route does not redirect automatically.
    - It returns the URL so it can be copied, inspected, logged, or surfaced in
      a future UI.
    - This is the first step in the OAuth flow.
    - The client-side approver still needs to open the returned URL and approve
      the app inside JobAdder.

    Example
    -------
    A request might look like:

        GET /api/v1/integrations/jobadder/authorize?state=connect-jobadder-dev

    In plain language:

    - build the approval link
    - return it as JSON
    - let the authorised JobAdder user open it
    """

    if not has_jobadder_oauth_configuration():
        return build_error_response(
            status_code=status.HTTP_401_UNAUTHORIZED,
            code="unauthorized",
            message="JobAdder OAuth is not configured.",
            details=[
                {
                    "required_settings": [
                        "JOBADDER_CLIENT_ID",
                        "JOBADDER_REDIRECT_URI",
                    ]
                }
            ],
        )

    authorization_url = build_jobadder_authorization_url(state=state)

    return JobAdderAuthorizationUrlResponse(
        authorization_url=authorization_url,
        oauth_configuration_ready=True,
        state=state,
    )


@router.get(
    "/jobadder/callback",
    response_model=JobAdderOAuthConnectionSavedResponse,
    responses={
        401: {
            "model": ApiErrorResponse,
            "description": "JobAdder token-exchange settings are not configured.",
        },
        400: {
            "model": ApiErrorResponse,
            "description": "JobAdder returned an OAuth error.",
        },
        422: {
            "model": ApiErrorResponse,
            "description": "Required callback query values were missing.",
        },
        502: {
            "model": ApiErrorResponse,
            "description": "JobAdder token exchange failed.",
        },
        500: {
            "model": ApiErrorResponse,
            "description": "The JobAdder token set could not be saved.",
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
) -> JobAdderOAuthConnectionSavedResponse | JSONResponse:
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
    JobAdderOAuthConnectionSavedResponse | JSONResponse
        Success response confirming that the callback completed, the code was
        exchanged, and the returned token set was saved.

        Standard API error response when the provider returned an OAuth error or
        when the callback is missing the expected query parameters.

    Route
    -----
    This module contributes:

        GET /api/v1/integrations/jobadder/callback

    Notes
    -----
    - This route is the server-side completion step of the OAuth flow.
    - It receives the provider redirect, exchanges the one-time code for
      tokens, and then saves the returned token set in Postgres.
    - The response deliberately avoids exposing the raw authorization code or
      any token values.

    Example
    -------
    A successful provider redirect would look like:

        GET /api/v1/integrations/jobadder/callback?code=abc123&state=connect-dev

    In plain language:

    - receive the provider redirect
    - reject explicit provider-side OAuth errors clearly
    - exchange the one-time code for tokens
    - save the returned token set
    - return a clean summary of the successful connection
    """

    # If JobAdder returns `error=...` in the callback query, the provider is
    # telling us the authorisation step did not complete successfully.
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

    # The token exchange needs:
    # - client ID
    # - client secret
    # - exact redirect URI
    #
    # Without these, the backend cannot safely complete the OAuth flow even if
    # the callback route itself is reachable.
    if not has_jobadder_token_exchange_configuration():
        return build_error_response(
            status_code=status.HTTP_401_UNAUTHORIZED,
            code="unauthorized",
            message="JobAdder token exchange is not configured.",
            details=[
                {
                    "required_settings": [
                        "JOBADDER_CLIENT_ID",
                        "JOBADDER_CLIENT_SECRET",
                        "JOBADDER_REDIRECT_URI",
                    ]
                }
            ],
        )

    try:
        token_set = exchange_jobadder_authorization_code(code=code)
    except JobAdderOAuthExchangeError as exc:
        details: list[dict[str, Any]] = []

        if exc.status_code is not None:
            details.append({"provider_status_code": exc.status_code})

        if exc.provider_error is not None:
            details.append({"provider_error": exc.provider_error})

        if exc.provider_error_description is not None:
            details.append(
                {"provider_error_description": exc.provider_error_description}
            )

        if state:
            details.append({"state": state})

        return build_error_response(
            status_code=status.HTTP_502_BAD_GATEWAY,
            code="approval_required",
            message="JobAdder token exchange failed.",
            details=details,
        )

    try:
        saved_connection = save_jobadder_oauth_connection(token_set)
    except (RuntimeError, ValueError) as exc:
        details: list[dict[str, Any]] = [{"reason": str(exc)}]

        if state:
            details.append({"state": state})

        return build_error_response(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            code="internal_error",
            message="JobAdder token exchange succeeded, but the connection could not be saved.",
            details=details,
        )

    return JobAdderOAuthConnectionSavedResponse(
        status="connected",
        message="JobAdder connection completed successfully.",
        oauth_connection_id=str(saved_connection["id"]),
        jobadder_account=int(saved_connection["jobadder_account"]),
        jobadder_instance=saved_connection.get("jobadder_instance"),
        state=state,
        next_step=(
            "The JobAdder tokens were saved successfully. The next step is to "
            "make the first authenticated JobAdder API read."
        ),
    )


__all__ = ["router"]
