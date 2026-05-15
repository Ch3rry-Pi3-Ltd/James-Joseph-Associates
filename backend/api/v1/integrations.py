"""
Integration endpoints for version 1 of the intelligence API.

This module contains small endpoints that sit at the boundary between the
backend and external systems such as JobAdder and Dropbox.

It gives the rest of the repository a stable way to verify:

- the backend has a real JobAdder OAuth callback path
- the backend can build a real JobAdder approval URL
- the registered redirect URI points at a live backend route
- provider callback query parameters are handled safely
- configuration readiness can be reported clearly during setup
- the backend can make a first authenticated read against the JobAdder API
- the backend can make the same first authenticated reads against Dropbox

Keeping integration endpoints in their own module makes the project easier to
extend because:

- `backend.api.router` stays focused on route registration
- provider-specific HTTP handling stays separate from candidate and Make.com
  endpoints
- future provider callbacks can follow the same local pattern
- Dropbox integration can grow without inventing a second route style
- later token exchange and token storage can be added without mixing concerns

Example
-------
This module now covers the first few live integration steps for both JobAdder
and Dropbox:

- `GET /api/v1/integrations/jobadder/authorize`
- `GET /api/v1/integrations/jobadder/callback`
- `GET /api/v1/integrations/jobadder/accounts/{jobadder_account}/candidates-preview`
- `GET /api/v1/integrations/jobadder/accounts/{jobadder_account}/candidates/{candidate_id}`
- `GET /api/v1/integrations/jobadder/accounts/{jobadder_account}/candidates/{candidate_id}/notes`
- `GET /api/v1/integrations/jobadder/accounts/{jobadder_account}/candidates/{candidate_id}/skills`
- `GET /api/v1/integrations/dropbox/authorize`
- `GET /api/v1/integrations/dropbox/callback`
- `GET /api/v1/integrations/dropbox/accounts/{dropbox_account_id}/current-account`
- `GET /api/v1/integrations/dropbox/accounts/{dropbox_account_id}/files/list-folder`

In plain language:

- this module answers the question:

    "Does the backend have the pieces needed to start the JobAdder and Dropbox OAuth flows?"

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
from backend.db.dropbox_oauth import (
    get_dropbox_oauth_connection,
    save_dropbox_oauth_connection,
)
from backend.schemas.errors import ApiError, ApiErrorResponse
from backend.schemas.integrations import (
    DropboxAuthorizationUrlResponse,
    DropboxCurrentAccountResponse,
    DropboxFolderPreviewResponse,
    DropboxOAuthConnectionSavedResponse,
    JobAdderAuthorizationUrlResponse,
    JobAdderCandidateDetailResponse,
    JobAdderCandidateNotesResponse,
    JobAdderCandidateSkillsResponse,
    JobAdderCandidatesPreviewResponse,
    JobAdderOAuthConnectionSavedResponse,
)
from backend.services.dropbox_api import (
    DropboxApiError,
    fetch_dropbox_current_account,
    fetch_dropbox_list_folder,
)
from backend.services.dropbox_oauth import (
    DropboxOAuthExchangeError,
    DropboxTokenSet,
    build_dropbox_authorization_url,
    exchange_dropbox_authorization_code,
    has_dropbox_oauth_configuration,
    has_dropbox_token_exchange_configuration,
    is_dropbox_access_token_expired,
    refresh_dropbox_access_token,
)
from backend.services.jobadder_api import (
    JobAdderApiError,
    fetch_jobadder_candidate_detail,
    fetch_jobadder_candidate_notes,
    fetch_jobadder_candidate_skills,
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

    Example
    -------
    A call such as:

        build_error_response(
            status_code=404,
            code="not_found",
            message="Stored JobAdder connection was not found.",
            details=[{"jobadder_account": 2236}],
        )

    produces the standard API error envelope instead of making each route hand-
    build its own JSON response.
    """
    # Build the typed error payload first so the response shape stays aligned
    # with the rest of the project's schema layer.
    #
    # That keeps the route code free from ad hoc dictionary-building and makes
    # later test assertions more consistent.
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


def _refresh_jobadder_stored_connection(
    *,
    jobadder_account: int,
    refresh_token_value: Any,
) -> dict[str, Any] | JSONResponse:
    """
    Refresh the stored JobAdder token set and persist the replacement row.

    Parameters
    ----------
    jobadder_account : int
        JobAdder account identifier used as the natural key for the stored
        connection row.

    refresh_token_value : Any
        Raw refresh-token value read from the current stored connection row.

    Returns
    -------
    dict[str, Any] | JSONResponse
        Updated stored connection row on success.

        Standard API error response when the refresh token is missing, the
        JobAdder refresh request fails, or the refreshed token set could not be
        saved.

    Notes
    -----
    - Every authenticated JobAdder read may need a token refresh in one of two
      situations:
        - proactively before the provider call when the token is already
          expired
        - reactively after a 401 response when the token looked valid but was
          rejected upstream
    - Keeping the refresh-and-save sequence in one helper prevents the read
      routes from drifting apart in how they handle refresh failures.

    Example
    -------
    This helper is used when:

    - a stored token is already expired before the first provider read
    - a provider read comes back with `401` and a refresh/retry is needed
    """
    # Validate the local refresh token first so a missing stored credential is
    # reported as a local persistence problem, not blurred together with a
    # provider-side OAuth failure.
    if not isinstance(refresh_token_value, str) or refresh_token_value.strip() == "":
        return build_error_response(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            code="internal_error",
            message="The stored JobAdder connection is missing a refresh token.",
            details=[{"jobadder_account": jobadder_account}],
        )

    # Ask JobAdder for a fresh token set, then persist it immediately if the
    # provider call succeeds.
    #
    # Saving right away matters because the goal is not just to rescue the
    # current request. The goal is also to leave the stored connection in a
    # better state for the next request.
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


def _prepare_jobadder_connection_for_api_read(
    *,
    jobadder_account: int,
) -> dict[str, Any] | JSONResponse:
    """
    Load one stored JobAdder connection row and ensure it is ready for an API read.

    Parameters
    ----------
    jobadder_account : int
        JobAdder account identifier used to locate the stored OAuth connection.

    Returns
    -------
    dict[str, Any] | JSONResponse
        Stored connection row that contains at least a usable `access_token`
        and `api_url`.

        Standard API error response when the stored connection is missing,
        incomplete, or requires a refresh that fails.

    Notes
    -----
    - This helper centralises the common pre-read checks used by every
      authenticated JobAdder route.
    - It also performs the proactive refresh step when the stored timing fields
      indicate the access token is expired or too close to expiry.

    Example
    -------
    A route that needs to read from JobAdder can call:

        stored_connection = _prepare_jobadder_connection_for_api_read(
            jobadder_account=2236,
        )

    and either receive:

    - a usable stored connection row
    - or a ready-to-return `JSONResponse` error
    """
    # Start by loading the one stored connection row for this JobAdder account.
    #
    # Every later decision in this helper depends on that row:
    # - whether the account has been connected at all
    # - whether the required local fields exist
    # - whether the token should be refreshed before the provider read
    stored_connection = get_jobadder_oauth_connection(jobadder_account)

    if stored_connection is None:
        return build_error_response(
            status_code=status.HTTP_404_NOT_FOUND,
            code="not_found",
            message="Stored JobAdder connection was not found.",
            details=[{"jobadder_account": jobadder_account}],
        )

    raw_access_token = stored_connection.get("access_token")
    raw_api_url = stored_connection.get("api_url")
    raw_refresh_token = stored_connection.get("refresh_token")
    raw_obtained_at = stored_connection.get("obtained_at")
    raw_expires_in_seconds = stored_connection.get("expires_in_seconds")

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

    # Refresh proactively when the stored token timing data says the access
    # token is already expired or too close to expiry.
    #
    # That reduces avoidable 401s and makes the later route logic easier to
    # reason about because the "normal first attempt" starts from the best
    # available credential state.
    if is_jobadder_access_token_expired(
        obtained_at=raw_obtained_at,
        expires_in_seconds=raw_expires_in_seconds,
    ):
        refreshed_connection = _refresh_jobadder_stored_connection(
            jobadder_account=jobadder_account,
            refresh_token_value=raw_refresh_token,
        )

        if isinstance(refreshed_connection, JSONResponse):
            return refreshed_connection

        refreshed_access_token = refreshed_connection.get("access_token")
        refreshed_api_url = refreshed_connection.get("api_url")

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

        if not isinstance(refreshed_api_url, str) or refreshed_api_url.strip() == "":
            return build_error_response(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                code="internal_error",
                message="The refreshed JobAdder connection is missing an API URL.",
                details=[{"jobadder_account": jobadder_account}],
            )

        # Return the freshly saved row rather than the pre-refresh row so later
        # code uses the same successful credential set the refresh step just
        # produced.
        return refreshed_connection

    return stored_connection


def _perform_jobadder_read_with_refresh_retry(
    *,
    jobadder_account: int,
    stored_connection: dict[str, Any],
    read_callable,
    provider_failure_message: str,
) -> tuple[dict[str, Any], str, str | None] | JSONResponse:
    """
    Perform one JobAdder read and retry once with a refreshed token after 401.

    Parameters
    ----------
    jobadder_account : int
        JobAdder account identifier used for error reporting and refresh saves.

    stored_connection : dict[str, Any]
        Stored JobAdder connection row that already passed the initial local
        validation checks.

    read_callable : callable
        Small function that accepts keyword arguments `api_url` and
        `access_token` and performs one provider read.

    provider_failure_message : str
        Safe route-level error message to use when the provider read fails.

    Returns
    -------
    tuple[dict[str, Any], str, str | None] | JSONResponse
        Tuple containing:

        - the normalised read result returned by the service helper
        - the API base URL used for the successful provider call
        - the JobAdder instance value associated with the successful call

        Standard API error response when the provider read fails definitively
        or the refresh-and-retry path cannot recover.

    Notes
    -----
    - This helper is intentionally route-agnostic. It does not care whether
      the caller is asking for a preview list, a candidate detail, or a skills
      hierarchy.
    - The only special provider case it handles is 401, because that can often
      be resolved by refreshing the access token once and retrying.

    Example
    -------
    Routes can pass small resource-specific lambdas such as:

        lambda *, api_url, access_token: fetch_jobadder_candidates_preview(...)

    or:

        lambda *, api_url, access_token: fetch_jobadder_candidate_detail(...)

    and let this helper own the shared:

    - first read attempt
    - one-time refresh-and-retry on 401
    - standardised error response building
    """
    # Pull the relevant stored fields into local names once so the retry logic
    # below reads clearly and does not repeatedly index into the connection
    # dictionary.
    raw_access_token = stored_connection.get("access_token")
    raw_api_url = stored_connection.get("api_url")
    raw_refresh_token = stored_connection.get("refresh_token")
    raw_jobadder_instance = stored_connection.get("jobadder_instance")

    try:
        # First attempt: use the connection exactly as prepared by the shared
        # pre-read helper.
        read_result = read_callable(
            api_url=raw_api_url,
            access_token=raw_access_token,
        )
    except JobAdderApiError as exc:
        if exc.status_code == 401:
            # `401` is the one provider failure we treat as potentially
            # recoverable here.
            #
            # The intent is narrow and deliberate:
            # - refresh once
            # - retry once
            # - if that still fails, surface the failure clearly
            refreshed_connection = _refresh_jobadder_stored_connection(
                jobadder_account=jobadder_account,
                refresh_token_value=raw_refresh_token,
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

            # Retry exactly once with the refreshed token set.
            #
            # More than one retry would start hiding genuine provider or data
            # problems behind repeated automatic behaviour.
            try:
                read_result = read_callable(
                    api_url=refreshed_api_url,
                    access_token=refreshed_access_token,
                )
            except JobAdderApiError as retry_exc:
                details: list[dict[str, Any]] = [{"jobadder_account": jobadder_account}]

                if retry_exc.status_code is not None:
                    details.append({"provider_status_code": retry_exc.status_code})

                if retry_exc.retry_after is not None:
                    details.append({"retry_after_seconds": retry_exc.retry_after})

                if retry_exc.endpoint_url is not None:
                    details.append({"endpoint_url": retry_exc.endpoint_url})

                return build_error_response(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    code="internal_error",
                    message=provider_failure_message,
                    details=details,
                )

            # Return not just the successful read result, but also the API URL
            # and JobAdder instance associated with the successful call so the
            # route can echo the correct connection context back to the client.
            return (
                read_result,
                refreshed_api_url,
                (
                    refreshed_jobadder_instance
                    if isinstance(refreshed_jobadder_instance, str)
                    else None
                ),
            )

        # Any non-401 provider failure is treated as final at this layer.
        #
        # Examples:
        # - `404` usually means the resource does not exist
        # - `429` means throttling
        # - `500` likely means an upstream provider problem
        #
        # A token refresh does not meaningfully improve those cases, so we
        # surface them directly with as much safe context as we can.
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
            message=provider_failure_message,
            details=details,
        )

    return (
        read_result,
        raw_api_url,
        raw_jobadder_instance if isinstance(raw_jobadder_instance, str) else None,
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
    # Check configuration before trying to build the URL so setup problems are
    # reported clearly and predictably.
    #
    # This route is often used very early in integration setup, so clean
    # readiness feedback is part of its job.
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

    # Build the URL only after the readiness check succeeds.
    #
    # Keeping the readiness check and URL construction as separate steps makes
    # the control flow easy to follow for anyone still learning the OAuth flow.
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
    # Provider-declared OAuth errors take precedence over everything else.
    #
    # If JobAdder says the authorisation step failed, there is no point trying
    # to continue into the code-exchange flow.
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

    # Exchange the one-time authorisation code for a token set before touching
    # local persistence.
    #
    # This keeps the stages conceptually clean:
    # - first obtain a valid provider token set
    # - then save it locally
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

    # Persist the successful token set immediately so the connection becomes
    # usable for later authenticated API reads.
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
    # Start by loading or refreshing the stored connection into a read-ready
    # shape.
    #
    # This keeps the route body focused on the resource being fetched rather
    # than duplicating OAuth storage and refresh logic inline.
    stored_connection = _prepare_jobadder_connection_for_api_read(
        jobadder_account=jobadder_account
    )

    if isinstance(stored_connection, JSONResponse):
        return stored_connection

    # Delegate the shared "read, maybe refresh, maybe retry" mechanics to the
    # common helper so this route only needs to define the concrete resource
    # read it wants.
    preview_result = _perform_jobadder_read_with_refresh_retry(
        jobadder_account=jobadder_account,
        stored_connection=stored_connection,
        read_callable=lambda *, api_url, access_token: fetch_jobadder_candidates_preview(
            api_url=api_url,
            access_token=access_token,
            item_limit=item_limit,
        ),
        provider_failure_message="JobAdder candidate read failed.",
    )

    if isinstance(preview_result, JSONResponse):
        return preview_result

    preview, api_url, jobadder_instance = preview_result

    # Build the typed response model last, after all provider interaction and
    # refresh handling has already succeeded.
    return JobAdderCandidatesPreviewResponse(
        jobadder_account=jobadder_account,
        jobadder_instance=jobadder_instance,
        api_url=api_url,
        item_count=preview["item_count"],
        total_count=preview["total_count"],
        links=preview["links"],
        candidates=preview["items"],
    )


@router.get(
    "/jobadder/accounts/{jobadder_account}/candidates/{candidate_id}",
    response_model=JobAdderCandidateDetailResponse,
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
            "description": "JobAdder candidate detail read failed.",
        },
    },
)
def get_jobadder_candidate_detail_route(
    jobadder_account: int,
    candidate_id: int,
) -> JobAdderCandidateDetailResponse | JSONResponse:
    """
    Return one full candidate record from the connected JobAdder account.

    Parameters
    ----------
    jobadder_account : int
        JobAdder account identifier used to locate the stored OAuth connection.

    candidate_id : int
        JobAdder candidate identifier to fetch.

    Returns
    -------
    JobAdderCandidateDetailResponse | JSONResponse
        Full candidate response when the stored connection exists and the
        JobAdder API call succeeds.

        Standard API error response when the stored connection cannot be found,
        is missing required fields, the token refresh fails, or the provider
        read fails.

    Notes
    -----
    - This route exists for inspection and schema-mapping work.
    - It exposes the full candidate object returned by JobAdder so the backend
      can compare the real source payload with the canonical tables before
      building ingestion logic.

    Example
    -------
    A request looks like:

        GET /api/v1/integrations/jobadder/accounts/2236/candidates/16496678

    and returns:

    - the JobAdder account context
    - the API URL used
    - the requested candidate ID
    - the full candidate object
    """
    # Reuse the same shared connection-preparation helper as the preview route
    # so all authenticated JobAdder reads start from the same credential rules.
    stored_connection = _prepare_jobadder_connection_for_api_read(
        jobadder_account=jobadder_account
    )

    if isinstance(stored_connection, JSONResponse):
        return stored_connection

    # This route's only resource-specific concern is "fetch one candidate
    # detail". The shared retry helper owns the common token-recovery behaviour.
    detail_result = _perform_jobadder_read_with_refresh_retry(
        jobadder_account=jobadder_account,
        stored_connection=stored_connection,
        read_callable=lambda *, api_url, access_token: fetch_jobadder_candidate_detail(
            api_url=api_url,
            access_token=access_token,
            candidate_id=candidate_id,
        ),
        provider_failure_message="JobAdder candidate detail read failed.",
    )

    if isinstance(detail_result, JSONResponse):
        return detail_result

    candidate_detail, api_url, jobadder_instance = detail_result

    return JobAdderCandidateDetailResponse(
        jobadder_account=jobadder_account,
        jobadder_instance=jobadder_instance,
        api_url=api_url,
        candidate_id=candidate_id,
        candidate=candidate_detail["candidate"],
    )


@router.get(
    "/jobadder/accounts/{jobadder_account}/candidates/{candidate_id}/notes",
    response_model=JobAdderCandidateNotesResponse,
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
            "description": "JobAdder candidate notes read failed.",
        },
    },
)
def get_jobadder_candidate_notes_route(
    jobadder_account: int,
    candidate_id: int,
    item_limit: int = Query(
        default=25,
        ge=1,
        le=100,
        description=(
            "Maximum number of candidate note items to request from the first "
            "JobAdder notes read."
        ),
    ),
) -> JobAdderCandidateNotesResponse | JSONResponse:
    """
    Return candidate notes from the connected JobAdder account.

    Parameters
    ----------
    jobadder_account : int
        JobAdder account identifier used to locate the stored OAuth connection.

    candidate_id : int
        JobAdder candidate identifier whose notes should be fetched.

    item_limit : int
        Maximum number of note items to request in this first bounded read.

    Returns
    -------
    JobAdderCandidateNotesResponse | JSONResponse
        Candidate notes response when the stored connection exists and the
        JobAdder API call succeeds.

        Standard API error response when the stored connection cannot be
        found, is missing required fields, the token refresh fails, or the
        provider read fails.

    Notes
    -----
    - Candidate notes are not returned as full note bodies inside the main
      candidate-detail payload.
    - JobAdder exposes them through a dedicated notes endpoint, and the API
      docs indicate that full note text should be requested through the
      `Fields=text` query parameter.
    - This route therefore exists specifically to prove that the backend can
      pull real candidate notes rather than only seeing a notes link.

    Example
    -------
    A request looks like:

        GET /api/v1/integrations/jobadder/accounts/2236/candidates/16496678/notes

    and returns:

    - the JobAdder account context
    - the requested candidate ID
    - a note count
    - the note list returned by JobAdder

    In plain language:

    - load the stored JobAdder connection
    - refresh the token if needed
    - call the dedicated candidate-notes endpoint
    - return the notes payload in one predictable wrapper
    """

    # Start from the same shared connection-preparation path used by the other
    # authenticated JobAdder read routes so note retrieval inherits the same:
    # - missing-connection handling
    # - proactive refresh handling
    # - local field validation
    stored_connection = _prepare_jobadder_connection_for_api_read(
        jobadder_account=jobadder_account
    )

    if isinstance(stored_connection, JSONResponse):
        return stored_connection

    # Delegate the "read, maybe refresh, maybe retry once" mechanics to the
    # shared route helper. This keeps the route focused on its actual resource:
    # candidate notes.
    notes_result = _perform_jobadder_read_with_refresh_retry(
        jobadder_account=jobadder_account,
        stored_connection=stored_connection,
        read_callable=lambda *, api_url, access_token: fetch_jobadder_candidate_notes(
            api_url=api_url,
            access_token=access_token,
            candidate_id=candidate_id,
            item_limit=item_limit,
        ),
        provider_failure_message="JobAdder candidate notes read failed.",
    )

    if isinstance(notes_result, JSONResponse):
        return notes_result

    candidate_notes, api_url, jobadder_instance = notes_result

    return JobAdderCandidateNotesResponse(
        jobadder_account=jobadder_account,
        jobadder_instance=jobadder_instance,
        api_url=api_url,
        candidate_id=candidate_id,
        note_count=candidate_notes["note_count"],
        total_count=candidate_notes["total_count"],
        links=candidate_notes["links"],
        notes=candidate_notes["notes"],
    )


@router.get(
    "/jobadder/accounts/{jobadder_account}/candidates/{candidate_id}/skills",
    response_model=JobAdderCandidateSkillsResponse,
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
            "description": "JobAdder candidate skills read failed.",
        },
    },
)
def get_jobadder_candidate_skills_route(
    jobadder_account: int,
    candidate_id: int,
) -> JobAdderCandidateSkillsResponse | JSONResponse:
    """
    Return the structured candidate-skills hierarchy from JobAdder.

    Parameters
    ----------
    jobadder_account : int
        JobAdder account identifier used to locate the stored OAuth connection.

    candidate_id : int
        JobAdder candidate identifier whose skills should be fetched.

    Returns
    -------
    JobAdderCandidateSkillsResponse | JSONResponse
        Structured category tree when the stored connection exists and the
        JobAdder API call succeeds.

        Standard API error response when the stored connection cannot be found,
        is missing required fields, the token refresh fails, or the provider
        read fails.

    Notes
    -----
    - The OpenAPI spec exposes candidate skills separately from the main
      candidate detail payload.
    - This route preserves that separate source-system view so the backend can
      inspect the real category/subcategory/skill hierarchy before deciding how
      to model skills canonically.

    Example
    -------
    A request looks like:

        GET /api/v1/integrations/jobadder/accounts/2236/candidates/16496678/skills

    and returns:

    - the JobAdder account context
    - the requested candidate ID
    - the category count
    - the structured categories tree
    """
    # Prepare or refresh the stored connection before the provider read so this
    # route behaves consistently with the preview and candidate-detail routes.
    stored_connection = _prepare_jobadder_connection_for_api_read(
        jobadder_account=jobadder_account
    )

    if isinstance(stored_connection, JSONResponse):
        return stored_connection

    skills_result = _perform_jobadder_read_with_refresh_retry(
        jobadder_account=jobadder_account,
        stored_connection=stored_connection,
        read_callable=lambda *, api_url, access_token: fetch_jobadder_candidate_skills(
            api_url=api_url,
            access_token=access_token,
            candidate_id=candidate_id,
        ),
        provider_failure_message="JobAdder candidate skills read failed.",
    )

    if isinstance(skills_result, JSONResponse):
        return skills_result

    candidate_skills, api_url, jobadder_instance = skills_result

    return JobAdderCandidateSkillsResponse(
        jobadder_account=jobadder_account,
        jobadder_instance=jobadder_instance,
        api_url=api_url,
        candidate_id=candidate_id,
        category_count=candidate_skills["category_count"],
        links=candidate_skills["links"],
        categories=candidate_skills["categories"],
    )


def _refresh_dropbox_stored_connection(
    *,
    dropbox_account_id: str,
    refresh_token_value: Any,
    stored_scope_value: Any,
) -> dict[str, Any] | JSONResponse:
    """
    Refresh the stored Dropbox token set and persist the replacement row.

    Parameters
    ----------
    dropbox_account_id : str
        Dropbox account identifier used as the natural key for the stored
        connection row.

    refresh_token_value : Any
        Raw refresh-token value read from the current stored connection row.

    stored_scope_value : Any
        Raw scope value read from the current stored connection row.

    Returns
    -------
    dict[str, Any] | JSONResponse
        Updated stored connection row on success.

        Standard API error response when the refresh token is missing, the
        Dropbox refresh request fails, or the refreshed token set could not be
        saved.

    Example
    -------
    This helper is used when:

    - a stored token is already expired before the first Dropbox read
    - a Dropbox read comes back with `401` and a refresh/retry is needed
    """

    if not isinstance(refresh_token_value, str) or refresh_token_value.strip() == "":
        return build_error_response(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            code="internal_error",
            message="The stored Dropbox connection is missing a refresh token.",
            details=[{"dropbox_account_id": dropbox_account_id}],
        )

    try:
        refreshed_token_set = refresh_dropbox_access_token(
            refresh_token=refresh_token_value,
        )
    except DropboxOAuthExchangeError as exc:
        details: list[dict[str, Any]] = [
            {"dropbox_account_id": dropbox_account_id}
        ]

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
            message="Dropbox token refresh failed.",
            details=details,
        )

    # Dropbox refresh responses typically contain the new short-lived access
    # token and expiry window only. They may omit:
    # - `refresh_token`
    # - `scope`
    # - `account_id`
    #
    # Persisting the raw refresh response directly would therefore risk wiping
    # stable connection metadata from the stored row. Merge the new access-token
    # fields with the stable identifiers already held locally before saving.
    merged_scope = (
        refreshed_token_set.scope
        if isinstance(refreshed_token_set.scope, str)
        and refreshed_token_set.scope.strip() != ""
        else (
            stored_scope_value
            if isinstance(stored_scope_value, str)
            and stored_scope_value.strip() != ""
            else None
        )
    )

    merged_refresh_token = (
        refreshed_token_set.refresh_token
        if isinstance(refreshed_token_set.refresh_token, str)
        and refreshed_token_set.refresh_token.strip() != ""
        else refresh_token_value
    )

    merged_raw_payload = dict(refreshed_token_set.raw_payload)
    merged_raw_payload.setdefault("account_id", dropbox_account_id)

    refreshed_token_set = DropboxTokenSet(
        access_token=refreshed_token_set.access_token,
        token_type=refreshed_token_set.token_type,
        expires_in=refreshed_token_set.expires_in,
        refresh_token=merged_refresh_token,
        scope=merged_scope,
        account_id=dropbox_account_id,
        raw_payload=merged_raw_payload,
    )

    try:
        return save_dropbox_oauth_connection(refreshed_token_set)
    except (RuntimeError, ValueError) as exc:
        return build_error_response(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            code="internal_error",
            message="Dropbox token refresh succeeded, but the refreshed connection could not be saved.",
            details=[
                {"dropbox_account_id": dropbox_account_id},
                {"reason": str(exc)},
            ],
        )


def _prepare_dropbox_connection_for_api_read(
    *,
    dropbox_account_id: str,
) -> dict[str, Any] | JSONResponse:
    """
    Load one stored Dropbox connection row and ensure it is ready for an API
    read.

    Parameters
    ----------
    dropbox_account_id : str
        Dropbox account identifier used to locate the stored OAuth connection.

    Returns
    -------
    dict[str, Any] | JSONResponse
        Stored connection row that contains at least a usable access token.

        Standard API error response when the stored connection is missing,
        incomplete, or requires a refresh that fails.

    Example
    -------
    A route that needs to read from Dropbox can call:

        stored_connection = _prepare_dropbox_connection_for_api_read(
            dropbox_account_id="dbid:AAExample",
        )

    and either receive:

    - a usable stored connection row
    - or a ready-to-return `JSONResponse` error
    """
    # Start by loading the one stored connection row for this Dropbox account.
    #
    # Every later decision in this helper depends on that row:
    # - whether the account has been connected at all
    # - whether the required local fields exist
    # - whether the token should be refreshed before the provider read
    stored_connection = get_dropbox_oauth_connection(dropbox_account_id)

    if stored_connection is None:
        return build_error_response(
            status_code=status.HTTP_404_NOT_FOUND,
            code="not_found",
            message="Stored Dropbox connection was not found.",
            details=[{"dropbox_account_id": dropbox_account_id}],
        )

    raw_access_token = stored_connection.get("access_token")
    raw_refresh_token = stored_connection.get("refresh_token")
    raw_scope = stored_connection.get("scope")
    raw_obtained_at = stored_connection.get("obtained_at")
    raw_expires_in_seconds = stored_connection.get("expires_in_seconds")

    if not isinstance(raw_access_token, str) or raw_access_token.strip() == "":
        return build_error_response(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            code="internal_error",
            message="The stored Dropbox connection is missing an access token.",
            details=[{"dropbox_account_id": dropbox_account_id}],
        )

    # Refresh proactively when the stored token timing data says the access
    # token is already expired or too close to expiry. That keeps the normal
    # first provider read on the strongest available credential state.
    if is_dropbox_access_token_expired(
        obtained_at=raw_obtained_at,
        expires_in_seconds=raw_expires_in_seconds,
    ):
        refreshed_connection = _refresh_dropbox_stored_connection(
            dropbox_account_id=dropbox_account_id,
            refresh_token_value=raw_refresh_token,
            stored_scope_value=raw_scope,
        )

        if isinstance(refreshed_connection, JSONResponse):
            return refreshed_connection

        refreshed_access_token = refreshed_connection.get("access_token")

        if (
            not isinstance(refreshed_access_token, str)
            or refreshed_access_token.strip() == ""
        ):
            return build_error_response(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                code="internal_error",
                message="The refreshed Dropbox connection is missing an access token.",
                details=[{"dropbox_account_id": dropbox_account_id}],
            )

        return refreshed_connection

    return stored_connection


def _perform_dropbox_read_with_refresh_retry(
    *,
    dropbox_account_id: str,
    stored_connection: dict[str, Any],
    read_callable,
    provider_failure_message: str,
) -> dict[str, Any] | JSONResponse:
    """
    Perform one Dropbox read and retry once with a refreshed token after `401`.

    Parameters
    ----------
    dropbox_account_id : str
        Dropbox account identifier used for error reporting and refresh saves.

    stored_connection : dict[str, Any]
        Stored Dropbox connection row that already passed the initial local
        validation checks.

    read_callable : callable
        Small function that accepts keyword argument `access_token` and
        performs one provider read.

    provider_failure_message : str
        Safe route-level error message to use when the provider read fails.

    Returns
    -------
    dict[str, Any] | JSONResponse
        Normalized read result returned by the service helper.

        Standard API error response when the provider read fails definitively
        or the refresh-and-retry path cannot recover.

    Example
    -------
    Routes can pass small resource-specific lambdas such as:

        lambda *, access_token: fetch_dropbox_current_account(...)

    or:

        lambda *, access_token: fetch_dropbox_list_folder(...)
    """
    # Pull the relevant stored fields into local names once so the retry logic
    # below reads clearly and does not repeatedly index into the connection
    # dictionary.
    raw_access_token = stored_connection.get("access_token")
    raw_refresh_token = stored_connection.get("refresh_token")
    raw_scope = stored_connection.get("scope")

    try:
        read_result = read_callable(access_token=raw_access_token)
    except DropboxApiError as exc:
        if exc.status_code == 401:
            # `401` is the one provider failure we treat as potentially
            # recoverable here.
            #
            # The intent is narrow and deliberate:
            # - refresh once
            # - retry once
            # - if that still fails, surface the failure clearly
            refreshed_connection = _refresh_dropbox_stored_connection(
                dropbox_account_id=dropbox_account_id,
                refresh_token_value=raw_refresh_token,
                stored_scope_value=raw_scope,
            )

            if isinstance(refreshed_connection, JSONResponse):
                return refreshed_connection

            refreshed_access_token = refreshed_connection.get("access_token")

            if (
                not isinstance(refreshed_access_token, str)
                or refreshed_access_token.strip() == ""
            ):
                return build_error_response(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    code="internal_error",
                    message="The refreshed Dropbox connection is missing an access token.",
                    details=[{"dropbox_account_id": dropbox_account_id}],
                )

            # Retry exactly once with the refreshed token set.
            #
            # More than one retry would start hiding genuine provider or data
            # problems behind repeated automatic behaviour.
            try:
                return read_callable(access_token=refreshed_access_token)
            except DropboxApiError as retry_exc:
                details: list[dict[str, Any]] = [
                    {"dropbox_account_id": dropbox_account_id}
                ]

                if retry_exc.status_code is not None:
                    details.append({"provider_status_code": retry_exc.status_code})

                if retry_exc.endpoint_url is not None:
                    details.append({"endpoint_url": retry_exc.endpoint_url})

                return build_error_response(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    code="internal_error",
                    message=provider_failure_message,
                    details=details,
                )

        details: list[dict[str, Any]] = [{"dropbox_account_id": dropbox_account_id}]

        if exc.status_code is not None:
            details.append({"provider_status_code": exc.status_code})

        if exc.endpoint_url is not None:
            details.append({"endpoint_url": exc.endpoint_url})

        return build_error_response(
            status_code=status.HTTP_502_BAD_GATEWAY,
            code="internal_error",
            message=provider_failure_message,
            details=details,
        )

    return read_result


@router.get(
    "/dropbox/authorize",
    response_model=DropboxAuthorizationUrlResponse,
    responses={
        401: {
            "model": ApiErrorResponse,
            "description": "Dropbox OAuth is not configured.",
        }
    },
)
def get_dropbox_authorization_url_route(
    state: str | None = Query(
        default=None,
        description=(
            "Optional opaque state value to round-trip through the Dropbox OAuth "
            "approval flow."
        ),
    ),
) -> DropboxAuthorizationUrlResponse | JSONResponse:
    """
    Return a ready-to-open Dropbox authorization URL.

    Notes
    -----
    - This route mirrors the JobAdder authorize route shape so the frontend or
      operator flow can obtain one approval URL to send to Tom.
    - Dropbox still requires one registered Dropbox app first. This route only
      builds the URL once the backend has the app key and redirect URI.

    Example
    -------
    A request looks like:

        GET /api/v1/integrations/dropbox/authorize?state=connect-dropbox-dev
    """

    if not has_dropbox_oauth_configuration():
        return build_error_response(
            status_code=status.HTTP_401_UNAUTHORIZED,
            code="unauthorized",
            message="Dropbox OAuth is not configured.",
            details=[
                {
                    "required_settings": [
                        "DROPBOX_CLIENT_ID",
                        "DROPBOX_REDIRECT_URI",
                    ]
                }
            ],
        )

    try:
        authorization_url = build_dropbox_authorization_url(state=state)
    except ValueError as exc:
        return build_error_response(
            status_code=status.HTTP_401_UNAUTHORIZED,
            code="unauthorized",
            message=str(exc),
        )

    return DropboxAuthorizationUrlResponse(
        authorization_url=authorization_url,
        oauth_configuration_ready=True,
        state=state,
    )


@router.get(
    "/dropbox/callback",
    response_model=DropboxOAuthConnectionSavedResponse,
    responses={
        400: {
            "model": ApiErrorResponse,
            "description": "Dropbox authorization was not completed.",
        },
        401: {
            "model": ApiErrorResponse,
            "description": "Dropbox token exchange is not configured.",
        },
        422: {
            "model": ApiErrorResponse,
            "description": "Dropbox authorization code is required.",
        },
        500: {
            "model": ApiErrorResponse,
            "description": "Dropbox token exchange succeeded but saving failed.",
        },
        502: {
            "model": ApiErrorResponse,
            "description": "Dropbox token exchange failed.",
        },
    },
)
def complete_dropbox_oauth_callback_route(
    code: str | None = Query(
        default=None,
        description="One-time Dropbox authorization code returned by the callback.",
    ),
    state: str | None = Query(
        default=None,
        description="Optional opaque state value originally sent to Dropbox.",
    ),
    error: str | None = Query(
        default=None,
        description="Optional Dropbox OAuth error code returned by the provider.",
    ),
    error_description: str | None = Query(
        default=None,
        description=(
            "Optional human-readable Dropbox OAuth error description returned "
            "by the provider."
        ),
    ),
) -> DropboxOAuthConnectionSavedResponse | JSONResponse:
    """
    Complete the Dropbox OAuth callback by exchanging the code and saving the
    resulting token set.

    Example
    -------
    A successful callback request looks like:

        GET /api/v1/integrations/dropbox/callback?code=...
    """

    if error is not None:
        details: list[dict[str, Any]] = [{"provider": "dropbox", "error": error}]

        if error_description:
            details.append({"provider_error_description": error_description})

        if state:
            details.append({"state": state})

        return build_error_response(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="unauthorized",
            message="Dropbox authorization was not completed.",
            details=details,
        )

    if code is None or code.strip() == "":
        return build_error_response(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            code="validation_error",
            message="Dropbox authorization code is required.",
            details=[{"query_param": "code", "reason": "missing_or_empty"}],
        )

    if not has_dropbox_token_exchange_configuration():
        return build_error_response(
            status_code=status.HTTP_401_UNAUTHORIZED,
            code="unauthorized",
            message="Dropbox token exchange is not configured.",
            details=[
                {
                    "required_settings": [
                        "DROPBOX_CLIENT_ID",
                        "DROPBOX_CLIENT_SECRET",
                        "DROPBOX_REDIRECT_URI",
                    ]
                }
            ],
        )

    try:
        token_set = exchange_dropbox_authorization_code(code=code)
    except DropboxOAuthExchangeError as exc:
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
            message="Dropbox token exchange failed.",
            details=details,
        )

    try:
        saved_connection = save_dropbox_oauth_connection(token_set)
    except (RuntimeError, ValueError) as exc:
        details: list[dict[str, Any]] = [{"reason": str(exc)}]

        if state:
            details.append({"state": state})

        return build_error_response(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            code="internal_error",
            message="Dropbox token exchange succeeded, but the connection could not be saved.",
            details=details,
        )

    return DropboxOAuthConnectionSavedResponse(
        status="connected",
        message="Dropbox connection completed successfully.",
        oauth_connection_id=str(saved_connection["id"]),
        dropbox_account_id=str(saved_connection["dropbox_account_id"]),
        state=state,
        next_step=(
            "The Dropbox tokens were saved successfully. The next step is to "
            "make the first authenticated Dropbox API read."
        ),
    )


@router.get(
    "/dropbox/accounts/{dropbox_account_id}/current-account",
    response_model=DropboxCurrentAccountResponse,
    responses={
        404: {
            "model": ApiErrorResponse,
            "description": "Stored Dropbox OAuth connection was not found.",
        },
        500: {
            "model": ApiErrorResponse,
            "description": "Stored Dropbox connection is missing required fields.",
        },
        502: {
            "model": ApiErrorResponse,
            "description": "Dropbox current-account read failed.",
        },
    },
)
def get_dropbox_current_account_route(
    dropbox_account_id: str,
) -> DropboxCurrentAccountResponse | JSONResponse:
    """
    Return the currently connected Dropbox account profile.

    Example
    -------
    A request looks like:

        GET /api/v1/integrations/dropbox/accounts/dbid:AAExample/current-account
    """
    # Start from the shared connection-preparation path so every authenticated
    # Dropbox read inherits the same local validation and proactive-refresh
    # behaviour.
    stored_connection = _prepare_dropbox_connection_for_api_read(
        dropbox_account_id=dropbox_account_id
    )

    if isinstance(stored_connection, JSONResponse):
        return stored_connection

    account_result = _perform_dropbox_read_with_refresh_retry(
        dropbox_account_id=dropbox_account_id,
        stored_connection=stored_connection,
        read_callable=lambda *, access_token: fetch_dropbox_current_account(
            access_token=access_token,
        ),
        provider_failure_message="Dropbox current-account read failed.",
    )

    if isinstance(account_result, JSONResponse):
        return account_result

    return DropboxCurrentAccountResponse(
        dropbox_account_id=dropbox_account_id,
        account=account_result["account"],
    )


@router.get(
    "/dropbox/accounts/{dropbox_account_id}/files/list-folder",
    response_model=DropboxFolderPreviewResponse,
    responses={
        404: {
            "model": ApiErrorResponse,
            "description": "Stored Dropbox OAuth connection was not found.",
        },
        500: {
            "model": ApiErrorResponse,
            "description": "Stored Dropbox connection is missing required fields.",
        },
        502: {
            "model": ApiErrorResponse,
            "description": "Dropbox folder listing failed.",
        },
    },
)
def get_dropbox_folder_preview_route(
    dropbox_account_id: str,
    path: str = Query(
        default="",
        description=(
            "Dropbox folder path to inspect. Use the empty string to list the "
            "root folder."
        ),
    ),
    recursive: bool = Query(
        default=False,
        description="Whether Dropbox should traverse subfolders recursively.",
    ),
    limit: int = Query(
        default=25,
        ge=1,
        le=200,
        description="Maximum number of folder entries to request in the first page.",
    ),
) -> DropboxFolderPreviewResponse | JSONResponse:
    """
    Return a first-page preview of a Dropbox folder.

    Notes
    -----
    - This route is intentionally a preview route rather than a full cursor
      traversal workflow.
    - It is designed for early Dropbox source-shape inspection, where the
      immediate question is "what is in this folder?" rather than "ingest the
      entire tree right now".

    Example
    -------
    A request looks like:

        GET /api/v1/integrations/dropbox/accounts/dbid:AAExample/files/list-folder?path=
    """
    # As with the current-account route, start from the shared
    # connection-preparation path so the folder read inherits the same:
    # - missing-connection handling
    # - proactive refresh handling
    # - local field validation
    stored_connection = _prepare_dropbox_connection_for_api_read(
        dropbox_account_id=dropbox_account_id
    )

    if isinstance(stored_connection, JSONResponse):
        return stored_connection

    folder_result = _perform_dropbox_read_with_refresh_retry(
        dropbox_account_id=dropbox_account_id,
        stored_connection=stored_connection,
        read_callable=lambda *, access_token: fetch_dropbox_list_folder(
            access_token=access_token,
            path=path,
            recursive=recursive,
            limit=limit,
        ),
        provider_failure_message="Dropbox folder listing failed.",
    )

    if isinstance(folder_result, JSONResponse):
        return folder_result

    return DropboxFolderPreviewResponse(
        dropbox_account_id=dropbox_account_id,
        path=folder_result["path"],
        entry_count=folder_result["entry_count"],
        has_more=folder_result["has_more"],
        cursor=folder_result["cursor"],
        entries=folder_result["entries"],
    )


__all__ = ["router"]
