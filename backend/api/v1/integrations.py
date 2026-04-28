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
- the backend can make a first authenticated read against the JobAdder API

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
- it can perform a first authenticated JobAdder candidate-list preview read
- it does not create candidates or jobs
- it handles the approval-link, OAuth callback, and first preview-read HTTP steps
"""

from typing import Any

from fastapi import APIRouter, Query, status
from fastapi.responses import JSONResponse

from backend.db.jobadder_oauth import (
    get_jobadder_oauth_connection,
    save_jobadder_oauth_connection,
)
from backend.schemas.errors import ApiError, ApiErrorResponse
from backend.schemas.integrations import (
    JobAdderAuthorizationUrlResponse,
    JobAdderCandidatesPreviewResponse,
    JobAdderOAuthConnectionSavedResponse,
)
from backend.services.jobadder_api import (
    JobAdderApiError,
    fetch_jobadder_candidates_preview,
)
from backend.services.jobadder_oauth import (
    JobAdderOAuthExchangeError,
    build_jobadder_authorization_url,
    exchange_jobadder_authorization_code,
    has_jobadder_oauth_configuration,
    has_jobadder_token_exchange_configuration,
    is_jobadder_access_token_expired,
    refresh_jobadder_access_token,
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


@router.get(
    "/jobadder/accounts/{jobadder_account}/candidates-preview",
    response_model=JobAdderCandidatesPreviewResponse,
    responses={
        404: {
            "model": ApiErrorResponse,
            "description": "Stored JobAdder OAuth connection was not found.",
        },
        500: {
            "model": ApiErrorResponse,
            "description": "Stored JobAdder connection is missing required fields.",
        },
        502: {
            "model": ApiErrorResponse,
            "description": "JobAdder candidate read failed.",
        },
    },
)
def get_jobadder_candidates_preview_route(
    jobadder_account: int,
    item_limit: int = Query(
        default=10,
        ge=1,
        le=25,
        description=(
            "Maximum number of candidate items to return from the first page of "
            "the JobAdder response."
        ),
    ),
) -> JobAdderCandidatesPreviewResponse | JSONResponse:
    """
    Return a small first-page preview of candidates from the connected JobAdder
    account.

    Parameters
    ----------
    jobadder_account : int
        JobAdder account identifier used to locate the stored OAuth connection.

    item_limit : int
        Maximum number of candidate items to return from the first page of the
        JobAdder response.

    Returns
    -------
    JobAdderCandidatesPreviewResponse | JSONResponse
        First-page candidate preview when the stored connection exists and the
        JobAdder API call succeeds.

        Standard API error response when the stored connection cannot be found,
        is missing required fields, the token refresh fails, or the provider
        read fails.

    Route
    -----
    This module contributes:

        GET /api/v1/integrations/jobadder/accounts/{jobadder_account}/candidates-preview

    Notes
    -----
    - This is the first authenticated JobAdder API read endpoint.
    - It is intentionally read-only.
    - It uses the stored OAuth connection row to retrieve:
        - `access_token`
        - `refresh_token`
        - `api_url`
        - `jobadder_instance`
        - `obtained_at`
        - `expires_in_seconds`
    - If the stored access token is already expired, the route refreshes it
      before making the provider call.
    - If the stored access token looked valid but JobAdder still returns 401,
      the route performs one refresh-and-retry attempt.
    - That second path covers edge cases such as token clock drift, stale
      stored access tokens, or provider-side timing mismatches.

    In plain language:

    - load the stored JobAdder connection from the database
    - refresh the token first if needed
    - use the working token to call JobAdder
    - retry once with a refreshed token if JobAdder rejects the first attempt
    - return a small preview of candidate data
    """

    stored_connection = get_jobadder_oauth_connection(jobadder_account)

    # If no stored JobAdder connection exists for this account, there is no
    # safe way to build an authenticated provider request.
    #   - Return 404 rather than attempting a provider call with invented or
    #     missing credentials.
    if stored_connection is None:
        return build_error_response(
            status_code=status.HTTP_404_NOT_FOUND,
            code="not_found",
            message="Stored JobAdder connection was not found.",
            details=[{"jobadder_account": jobadder_account}],
        )

    raw_access_token = stored_connection.get("access_token")
    raw_refresh_token = stored_connection.get("refresh_token")
    raw_api_url = stored_connection.get("api_url")
    raw_jobadder_instance = stored_connection.get("jobadder_instance")
    raw_obtained_at = stored_connection.get("obtained_at")
    raw_expires_in_seconds = stored_connection.get("expires_in_seconds")

    # Fail clearly if the database row exists but is missing the fields required
    # for an authenticated API read.
    #   - That would indicate a persistence bug or an incomplete stored
    #     connection rather than a provider-side problem.
    if not isinstance(raw_access_token, str) or raw_access_token.strip() == "":
        return build_error_response(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            code="internal_error",
            message="The stored JobAdder connection is missing an access token.",
            details=[{"jobadder_account": jobadder_account}],
        )

    if not isinstance(raw_api_url, str) or raw_api_url.strip() == "":
        return build_error_response(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            code="internal_error",
            message="The stored JobAdder connection is missing an API URL.",
            details=[{"jobadder_account": jobadder_account}],
        )

    def refresh_stored_connection(
        *,
        refresh_token_value: Any,
    ) -> dict[str, Any] | JSONResponse:
        """
        Refresh the stored JobAdder token set and persist the replacement row.

        Parameters
        ----------
        refresh_token_value : Any
            Raw refresh-token value read from the current stored connection row.

        Returns
        -------
        dict[str, Any] | JSONResponse
            Updated stored connection row on success.

            Standard API error response when the refresh token is missing, the
            JobAdder refresh request fails, or the refreshed token set could
            not be saved.

        Notes
        -----
        - The preview route may need refresh logic in two different places:
            - proactively before the provider call when the token is already
              expired
            - reactively after a 401 response when the token looked valid but
              was rejected upstream
        - Keeping that work in one local helper avoids duplicating the refresh,
          save, and error-shaping logic in both branches.

        In plain language:

        - take the stored refresh token
        - ask JobAdder for a new access token
        - save the refreshed token set back to Postgres
        - return the updated stored connection row
        """

        if (
            not isinstance(refresh_token_value, str)
            or refresh_token_value.strip() == ""
        ):
            return build_error_response(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                code="internal_error",
                message="The stored JobAdder connection is missing a refresh token.",
                details=[{"jobadder_account": jobadder_account}],
            )

        try:
            refreshed_token_set = refresh_jobadder_access_token(
                refresh_token=refresh_token_value,
            )
        except JobAdderOAuthExchangeError as exc:
            details: list[dict[str, Any]] = [{"jobadder_account": jobadder_account}]

            if exc.status_code is not None:
                details.append({"provider_status_code": exc.status_code})

            if exc.provider_error is not None:
                details.append({"provider_error": exc.provider_error})

            if exc.provider_error_description is not None:
                details.append(
                    {"provider_error_description": exc.provider_error_description}
                )

            return build_error_response(
                status_code=status.HTTP_502_BAD_GATEWAY,
                code="approval_required",
                message="JobAdder token refresh failed.",
                details=details,
            )

        try:
            return save_jobadder_oauth_connection(refreshed_token_set)
        except (RuntimeError, ValueError) as exc:
            return build_error_response(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                code="internal_error",
                message="JobAdder token refresh succeeded, but the refreshed connection could not be saved.",
                details=[
                    {"jobadder_account": jobadder_account},
                    {"reason": str(exc)},
                ],
            )

    # Refresh proactively when the stored timing fields indicate the access
    # token is already expired or too close to expiry.
    #   - This avoids spending one doomed provider request on a token we
    #     already know is stale.
    #   - The expiry helper fails closed: if the stored timing data is missing
    #     or cannot be parsed safely, it tells us to refresh first.
    if is_jobadder_access_token_expired(
        obtained_at=raw_obtained_at,
        expires_in_seconds=raw_expires_in_seconds,
    ):
        refreshed_connection = refresh_stored_connection(
            refresh_token_value=raw_refresh_token
        )

        if isinstance(refreshed_connection, JSONResponse):
            return refreshed_connection

        stored_connection = refreshed_connection
        raw_access_token = stored_connection.get("access_token")
        raw_refresh_token = stored_connection.get("refresh_token")
        raw_api_url = stored_connection.get("api_url")
        raw_jobadder_instance = stored_connection.get("jobadder_instance")

        # A successful refresh should have produced a complete replacement
        # connection row.
        #   - Re-check the required fields explicitly rather than assuming the
        #     database row is complete.
        if not isinstance(raw_access_token, str) or raw_access_token.strip() == "":
            return build_error_response(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                code="internal_error",
                message="The refreshed JobAdder connection is missing an access token.",
                details=[{"jobadder_account": jobadder_account}],
            )

        if not isinstance(raw_api_url, str) or raw_api_url.strip() == "":
            return build_error_response(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                code="internal_error",
                message="The refreshed JobAdder connection is missing an API URL.",
                details=[{"jobadder_account": jobadder_account}],
            )

    try:
        preview = fetch_jobadder_candidates_preview(
            api_url=raw_api_url,
            access_token=raw_access_token,
            item_limit=item_limit,
        )
    except JobAdderApiError as exc:
        # If JobAdder responds with 401 even after the proactive expiry check,
        # try one refresh-and-retry cycle.
        #   - This catches edge cases where the local expiry calculation looked
        #     fine but the upstream provider still considers the token stale.
        #   - We retry once only. If the refreshed token is also rejected, the
        #     route should fail clearly rather than looping.
        if exc.status_code == 401:
            refreshed_connection = refresh_stored_connection(
                refresh_token_value=raw_refresh_token
            )

            if isinstance(refreshed_connection, JSONResponse):
                return refreshed_connection

            refreshed_access_token = refreshed_connection.get("access_token")
            refreshed_api_url = refreshed_connection.get("api_url")
            refreshed_jobadder_instance = refreshed_connection.get(
                "jobadder_instance"
            )

            if (
                not isinstance(refreshed_access_token, str)
                or refreshed_access_token.strip() == ""
            ):
                return build_error_response(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    code="internal_error",
                    message="The refreshed JobAdder connection is missing an access token.",
                    details=[{"jobadder_account": jobadder_account}],
                )

            if (
                not isinstance(refreshed_api_url, str)
                or refreshed_api_url.strip() == ""
            ):
                return build_error_response(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    code="internal_error",
                    message="The refreshed JobAdder connection is missing an API URL.",
                    details=[{"jobadder_account": jobadder_account}],
                )

            try:
                preview = fetch_jobadder_candidates_preview(
                    api_url=refreshed_api_url,
                    access_token=refreshed_access_token,
                    item_limit=item_limit,
                )
            except JobAdderApiError as retry_exc:
                details: list[dict[str, Any]] = [
                    {"jobadder_account": jobadder_account}
                ]

                if retry_exc.status_code is not None:
                    details.append({"provider_status_code": retry_exc.status_code})

                if retry_exc.retry_after is not None:
                    details.append({"retry_after_seconds": retry_exc.retry_after})

                if retry_exc.endpoint_url is not None:
                    details.append({"endpoint_url": retry_exc.endpoint_url})

                return build_error_response(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    code="internal_error",
                    message="JobAdder candidate read failed.",
                    details=details,
                )

            raw_api_url = refreshed_api_url
            raw_jobadder_instance = (
                refreshed_jobadder_instance
                if isinstance(refreshed_jobadder_instance, str)
                else None
            )
        else:
            # Keep other provider-read failures distinct from local persistence
            # or configuration problems.
            #   - At this point we have already proved the stored connection
            #     exists and contains the fields needed to attempt the read.
            #   - So a non-401 failure here is an upstream JobAdder read
            #     problem, not a local OAuth-storage issue.
            details: list[dict[str, Any]] = [{"jobadder_account": jobadder_account}]

            if exc.status_code is not None:
                details.append({"provider_status_code": exc.status_code})

            if exc.retry_after is not None:
                details.append({"retry_after_seconds": exc.retry_after})

            if exc.endpoint_url is not None:
                details.append({"endpoint_url": exc.endpoint_url})

            return build_error_response(
                status_code=status.HTTP_502_BAD_GATEWAY,
                code="internal_error",
                message="JobAdder candidate read failed.",
                details=details,
            )

    # The preview helper already normalises the provider response into a small
    # local dictionary.
    #   - This route's job is simply to expose that preview through the API in
    #     one explicit typed response shape.
    return JobAdderCandidatesPreviewResponse(
        jobadder_account=jobadder_account,
        jobadder_instance=(
            raw_jobadder_instance if isinstance(raw_jobadder_instance, str) else None
        ),
        api_url=raw_api_url,
        item_count=preview["item_count"],
        total_count=preview["total_count"],
        links=preview["links"],
        candidates=preview["items"],
    )


__all__ = ["router"]
