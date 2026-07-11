"""
Integration endpoints for version 1 of the intelligence API.

This module contains small endpoints that sit at the boundary between the
backend and external systems such as JobAdder, Dropbox, and Outlook.

It gives the rest of the repository a stable way to verify:

- the backend has a real JobAdder OAuth callback path
- the backend can build a real JobAdder approval URL
- the registered redirect URI points at a live backend route
- provider callback query parameters are handled safely
- configuration readiness can be reported clearly during setup
- the backend can make a first authenticated read against the JobAdder API
- the backend can make the same first authenticated reads against Dropbox
- the backend can make the same first authenticated reads against Outlook

Keeping integration endpoints in their own module makes the project easier to
extend because:

- `backend.api.router` stays focused on route registration
- provider-specific HTTP handling stays separate from candidate and Make.com
  endpoints
- future provider callbacks can follow the same local pattern
- Dropbox integration can grow without inventing a second route style
- Outlook integration can grow in the same pattern
- later token exchange and token storage can be added without mixing concerns

Example
-------
This module now covers the first few live integration steps for JobAdder,
Dropbox, and Outlook:

- `GET /api/v1/integrations/jobadder/authorize`
- `GET /api/v1/integrations/jobadder/callback`
- `GET /api/v1/integrations/jobadder/accounts/{jobadder_account}/candidates-preview`
- `GET /api/v1/integrations/jobadder/accounts/{jobadder_account}/jobads-preview`
- `GET /api/v1/integrations/jobadder/accounts/{jobadder_account}/jobads/{ad_id}/applications-preview`
- `GET /api/v1/integrations/jobadder/accounts/{jobadder_account}/applications-preview`
- `GET /api/v1/integrations/jobadder/accounts/{jobadder_account}/applications/{application_id}`
- `GET /api/v1/integrations/jobadder/accounts/{jobadder_account}/applications/{application_id}/attachments-preview`
- `GET /api/v1/integrations/jobadder/accounts/{jobadder_account}/candidates/{candidate_id}/attachments-preview`
- `GET /api/v1/integrations/jobadder/accounts/{jobadder_account}/candidates/{candidate_id}`
- `GET /api/v1/integrations/jobadder/accounts/{jobadder_account}/candidates/{candidate_id}/notes`
- `GET /api/v1/integrations/jobadder/accounts/{jobadder_account}/candidates/{candidate_id}/skills`
- `GET /api/v1/integrations/dropbox/authorize`
- `GET /api/v1/integrations/dropbox/callback`
- `GET /api/v1/integrations/dropbox/accounts/{dropbox_account_id}/current-account`
- `GET /api/v1/integrations/dropbox/accounts/{dropbox_account_id}/files/list-folder`
- `GET /api/v1/integrations/outlook/authorize`
- `GET /api/v1/integrations/outlook/callback`
- `GET /api/v1/integrations/outlook/accounts/{microsoft_user_id}/current-user`
- `GET /api/v1/integrations/outlook/accounts/{microsoft_user_id}/mail-folders`
- `GET /api/v1/integrations/outlook/accounts/{microsoft_user_id}/messages`
- `GET /api/v1/integrations/outlook/accounts/{microsoft_user_id}/messages/{message_id}/attachments`
- `GET /api/v1/integrations/outlook/accounts/{microsoft_user_id}/messages/{message_id}/attachments/{attachment_id}/download-proof`

In plain language:

- this module answers the question:

    "Does the backend have the pieces needed to start the JobAdder, Dropbox, and Outlook OAuth flows?"

- it exchanges the returned JobAdder authorization code server-side
- it saves the returned JobAdder token set in Postgres
- it can perform a first authenticated JobAdder candidate-list preview read
- it does not create candidates or jobs
- it handles the approval-link, OAuth callback, and first preview-read HTTP steps
"""

import hashlib
import json
from io import BytesIO
from zipfile import BadZipFile, ZipFile
from dataclasses import replace
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Query, Request, status
from fastapi.responses import JSONResponse

from backend.db.jobadder_oauth import (
    get_jobadder_oauth_connection,
    save_jobadder_oauth_connection,
)
from backend.db.dropbox_oauth import (
    get_dropbox_oauth_connection,
    save_dropbox_oauth_connection,
)
from backend.db.outlook_oauth import (
    get_outlook_oauth_connection,
    save_outlook_oauth_connection,
)
from backend.schemas.errors import ApiError, ApiErrorResponse
from backend.schemas.integrations import (
    DropboxAuthorizationUrlResponse,
    DropboxCurrentAccountResponse,
    DropboxFolderPreviewResponse,
    DropboxOAuthConnectionSavedResponse,
    DropboxZipJsonMemberPreviewResponse,
    DropboxZipMembersPreviewResponse,
    LinkedHelperPersonIngestRequest,
    LinkedHelperPersonIngestResponse,
    RecruitlyCollectionIngestRequest,
    RecruitlyCollectionIngestResponse,
    RecruitlyEntityPreviewResponse,
    RecruitlyJournalPreviewResponse,
    JobAdderApplicationDetailResponse,
    JobAdderAuthorizationUrlResponse,
    JobAdderCandidateAttachmentDownloadProofResponse,
    JobAdderCandidateDetailResponse,
    JobAdderCandidateAttachmentsResponse,
    JobAdderCandidateNotesResponse,
    JobAdderCandidateSkillsResponse,
    JobAdderCandidatesPreviewResponse,
    JobAdderApplicationsPreviewResponse,
    JobAdderApplicationAttachmentsResponse,
    JobAdderJobAdApplicationsPreviewResponse,
    JobAdderJobApplicationsPreviewResponse,
    JobAdderJobDetailResponse,
    JobAdderJobAdsPreviewResponse,
    JobAdderOAuthConnectionSavedResponse,
    OutlookAuthorizationUrlResponse,
    OutlookCvAttachmentExportRequest,
    OutlookCvAttachmentExportResponse,
    OutlookCurrentUserResponse,
    OutlookFolderIngestRunRequest,
    OutlookFolderIngestRunResponse,
    OutlookMailFoldersResponse,
    OutlookMessageAttachmentDownloadProofResponse,
    OutlookMessageAttachmentsResponse,
    OutlookMessagesResponse,
    OutlookOAuthConnectionSavedResponse,
)
from backend.core.security import check_request_bearer_token
from backend.settings import get_settings
from backend.services.dropbox_api import (
    DropboxApiError,
    download_dropbox_file,
    fetch_dropbox_current_account,
    fetch_dropbox_list_folder,
)
from backend.services.dropbox_oauth import (
    DEFAULT_DROPBOX_SCOPE,
    DropboxOAuthExchangeError,
    DropboxTokenSet,
    build_dropbox_authorization_url,
    exchange_dropbox_authorization_code,
    has_dropbox_oauth_configuration,
    has_dropbox_token_exchange_configuration,
    is_dropbox_access_token_expired,
    refresh_dropbox_access_token,
)
from backend.services.outlook_api import (
    OutlookApiError,
    download_outlook_message_file_attachment,
    fetch_outlook_child_mail_folders,
    fetch_outlook_current_user,
    fetch_outlook_mail_folders,
    fetch_outlook_message_attachments,
    fetch_outlook_messages,
)
from backend.services.outlook_cv_attachment_export import (
    run_outlook_cv_attachment_export,
)
from backend.services.linkedin_helper_ingestion import (
    ingest_linkedin_helper_person,
)
from backend.services.recruitly_ingestion import (
    ingest_recruitly_collection_page,
)
from backend.services.recruitly_api import (
    RecruitlyApiError,
    fetch_recruitly_candidates_preview,
    fetch_recruitly_companies_preview,
    fetch_recruitly_contacts_preview,
    fetch_recruitly_jobs_preview,
    fetch_recruitly_record_journal_preview,
)
from backend.services.outlook_oauth import (
    OutlookOAuthExchangeError,
    OutlookTokenSet,
    build_outlook_authorization_url,
    exchange_outlook_authorization_code,
    has_outlook_oauth_configuration,
    has_outlook_token_exchange_configuration,
    is_outlook_access_token_expired,
    refresh_outlook_access_token,
)
from backend.services.jobadder_api import (
    JobAdderApiError,
    fetch_jobadder_application_detail,
    download_jobadder_candidate_attachment,
    fetch_jobadder_candidate_detail,
    fetch_jobadder_candidate_attachments,
    fetch_jobadder_candidate_notes,
    fetch_jobadder_candidate_skills,
    fetch_jobadder_candidates_preview,
    fetch_jobadder_applications_preview,
    fetch_jobadder_application_attachments,
    fetch_jobadder_jobad_applications_preview,
    fetch_jobadder_job_applications_preview,
    fetch_jobadder_job_detail,
    fetch_jobadder_jobads_preview,
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
from scripts.persist_outlook_tw394_folder import (
    load_ready_outlook_connection,
    resolve_outlook_folder_path,
    run_outlook_folder_ingest,
)
from scripts.persist_recruiterflow_initial_chunks import (
    _load_dropbox_connection,
)


router = APIRouter(prefix="/integrations", tags=["integrations"])


def _split_scope_string(scope_value: str | None) -> list[str]:
    """
    Split one space-separated OAuth scope string into normalized scope items.

    Example
    -------
    Calling:

        _split_scope_string("files.metadata.read files.content.read")

    returns:

        ["files.metadata.read", "files.content.read"]
    """

    if not isinstance(scope_value, str):
        return []

    return [item for item in scope_value.split() if item.strip() != ""]


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


def _authorize_admin_request(request: Request) -> JSONResponse | None:
    """
    Validate the shared bearer token for narrow protected admin routes.

    Notes
    -----
    - Prefer `ADMIN_API_TOKEN` / `INTERNAL_ADMIN_API_TOKEN`.
    - Fall back to `MAKE_API_TOKEN` through settings so already-configured
      environments can exercise the route immediately.
    """

    settings = get_settings()
    expected_token = getattr(settings, "admin_api_token", "")
    if not isinstance(expected_token, str) or expected_token.strip() == "":
        expected_token = getattr(settings, "make_api_token", "")

    if not isinstance(expected_token, str) or expected_token.strip() == "":
        return build_error_response(
            status_code=status.HTTP_401_UNAUTHORIZED,
            code="unauthorized",
            message="Admin API bearer token is not configured.",
        )

    auth_result = check_request_bearer_token(
        request=request,
        expected_token=expected_token,
    )
    if auth_result.is_authorised:
        return None

    return build_error_response(
        status_code=status.HTTP_401_UNAUTHORIZED,
        code="unauthorized",
        message="Valid admin bearer credentials were not provided.",
    )


def _normalize_outlook_folder_segments(folder_segments: list[str]) -> list[str]:
    """
    Normalize one Outlook folder path list from the protected ingest request.
    """

    normalized_segments = [
        segment.strip()
        for segment in folder_segments
        if isinstance(segment, str) and segment.strip() != ""
    ]
    if not normalized_segments:
        raise ValueError("At least one non-empty Outlook folder segment is required.")
    return normalized_segments


def _load_recruitly_configuration() -> tuple[str, str] | JSONResponse:
    """
    Load the bounded Recruitly API configuration for protected preview routes.
    """

    settings = get_settings()
    api_key = getattr(settings, "recruitly_api_key", "")
    api_base_url = getattr(settings, "recruitly_base_url", "")

    if not isinstance(api_key, str) or api_key.strip() == "":
        return build_error_response(
            status_code=status.HTTP_401_UNAUTHORIZED,
            code="unauthorized",
            message="Recruitly API is not configured.",
            details=[{"required_settings": ["RECRUITLY_API_KEY"]}],
        )

    if not isinstance(api_base_url, str) or api_base_url.strip() == "":
        return build_error_response(
            status_code=status.HTTP_401_UNAUTHORIZED,
            code="unauthorized",
            message="Recruitly API is not configured.",
            details=[{"required_settings": ["RECRUITLY_BASE_URL"]}],
        )

    return api_base_url.strip(), api_key.strip()


def _build_recruitly_error_details(exc: Exception) -> list[dict[str, Any]]:
    """
    Build one consistent protected-route error detail payload for Recruitly.

    Notes
    -----
    - Always include the local exception type and message.
    - When Recruitly returned the failure, also surface the downstream status,
      endpoint, and decoded body so production checks can distinguish bad keys
      from route/permission issues without extra logging changes.
    """

    details: list[dict[str, Any]] = [
        {
            "error_type": exc.__class__.__name__,
            "message": str(exc),
        }
    ]

    if isinstance(exc, RecruitlyApiError):
        if exc.status_code is not None:
            details.append({"status_code": exc.status_code})
        if exc.endpoint_url is not None:
            details.append({"endpoint_url": exc.endpoint_url})
        if exc.response_body is not None:
            details.append({"response_body": exc.response_body})

    return details


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

                if retry_exc.response_body:
                    details.append(
                        {"provider_response_body": retry_exc.response_body}
                    )

                retry_request_payload = getattr(
                    retry_exc, "request_payload", None
                )
                if retry_request_payload is not None:
                    details.append(
                        {"provider_request_payload": retry_request_payload}
                    )

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

        if exc.response_body:
            details.append({"provider_response_body": exc.response_body})

        request_payload = getattr(exc, "request_payload", None)
        if request_payload is not None:
            details.append({"provider_request_payload": request_payload})

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
    "/jobadder/accounts/{jobadder_account}/candidates/{candidate_id}/attachments-preview",
    response_model=JobAdderCandidateAttachmentsResponse,
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
            "description": "JobAdder candidate attachments read failed.",
        },
    },
)
def get_jobadder_candidate_attachments_route(
    jobadder_account: int,
    candidate_id: int,
) -> JobAdderCandidateAttachmentsResponse | JSONResponse:
    """
    Return the attachment list for one JobAdder candidate.

    Parameters
    ----------
    jobadder_account : int
        JobAdder account identifier used to locate the stored OAuth connection.

    candidate_id : int
        JobAdder candidate identifier whose attachments should be fetched.

    Returns
    -------
    JobAdderCandidateAttachmentsResponse | JSONResponse
        Candidate attachments response when the stored connection exists and
        the JobAdder API call succeeds.

    Example
    -------
    A request looks like:

        GET /api/v1/integrations/jobadder/accounts/2236/candidates/17071060/attachments-preview

    In plain language:

    - load the stored JobAdder connection
    - refresh the token first if needed
    - ask JobAdder for the candidate's attachment list
    - return the small normalized attachment wrapper
    """
    stored_connection = _prepare_jobadder_connection_for_api_read(
        jobadder_account=jobadder_account
    )

    if isinstance(stored_connection, JSONResponse):
        return stored_connection

    # Candidate attachments turned out to matter more than application
    # attachments for the tw398 sample. Keep this route symmetrical with the
    # other preview routes so we can compare those surfaces consistently.
    attachment_result = _perform_jobadder_read_with_refresh_retry(
        jobadder_account=jobadder_account,
        stored_connection=stored_connection,
        read_callable=lambda *, api_url, access_token: fetch_jobadder_candidate_attachments(
            api_url=api_url,
            access_token=access_token,
            candidate_id=candidate_id,
        ),
        provider_failure_message="JobAdder candidate attachments read failed.",
    )

    if isinstance(attachment_result, JSONResponse):
        return attachment_result

    attachments_result, api_url, jobadder_instance = attachment_result

    return JobAdderCandidateAttachmentsResponse(
        jobadder_account=jobadder_account,
        jobadder_instance=jobadder_instance,
        api_url=api_url,
        candidate_id=candidate_id,
        attachment_count=attachments_result["attachment_count"],
        links=attachments_result["links"],
        attachments=attachments_result["items"],
    )


@router.get(
    "/jobadder/accounts/{jobadder_account}/candidates/{candidate_id}/attachments/{attachment_id}/download-proof",
    response_model=JobAdderCandidateAttachmentDownloadProofResponse,
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
            "description": "JobAdder candidate attachment download failed.",
        },
    },
)
def get_jobadder_candidate_attachment_download_proof_route(
    jobadder_account: int,
    candidate_id: int,
    attachment_id: int,
) -> JobAdderCandidateAttachmentDownloadProofResponse | JSONResponse:
    """
    Download one JobAdder candidate attachment transiently and return proof
    metadata for cross-source comparison work.

    Notes
    -----
    - This route is intentionally narrow.
    - It exists so we can compare a JobAdder candidate CV against another
      source such as Dropbox without exposing the raw file bytes through the
      API response.
    - The SHA-256 hash lets us answer a concrete question:

        "Is the Dropbox CV byte-identical to the JobAdder candidate attachment?"

    Example
    -------
    A request looks like:

        GET /api/v1/integrations/jobadder/accounts/2236/candidates/17071060/attachments/21562882/download-proof

    And a successful response looks like:

        {
            "candidate_id": 17071060,
            "attachment_id": 21562882,
            "file_name": "sanjeev sadha.docx",
            "byte_count": 18931,
            "sha256": "...",
        }
    """
    stored_connection = _prepare_jobadder_connection_for_api_read(
        jobadder_account=jobadder_account
    )

    if isinstance(stored_connection, JSONResponse):
        return stored_connection

    download_result = _perform_jobadder_read_with_refresh_retry(
        jobadder_account=jobadder_account,
        stored_connection=stored_connection,
        read_callable=lambda *, api_url, access_token: download_jobadder_candidate_attachment(
            api_url=api_url,
            access_token=access_token,
            candidate_id=candidate_id,
            attachment_id=attachment_id,
        ),
        provider_failure_message="JobAdder candidate attachment download failed.",
    )

    if isinstance(download_result, JSONResponse):
        return download_result

    downloaded_attachment, api_url, jobadder_instance = download_result
    content_bytes = downloaded_attachment["content_bytes"]

    # Keep the proof route deliberately small and deterministic:
    # - report the provider metadata we need for comparison
    # - compute a stable content hash
    # - never return the raw file bytes over the API
    sha256_digest = hashlib.sha256(content_bytes).hexdigest()

    return JobAdderCandidateAttachmentDownloadProofResponse(
        jobadder_account=jobadder_account,
        jobadder_instance=jobadder_instance,
        api_url=api_url,
        candidate_id=candidate_id,
        attachment_id=attachment_id,
        file_name=downloaded_attachment.get("file_name"),
        content_type=downloaded_attachment.get("content_type"),
        content_length=downloaded_attachment.get("content_length"),
        byte_count=len(content_bytes),
        sha256=sha256_digest,
    )


@router.get(
    "/jobadder/accounts/{jobadder_account}/applications/{application_id}",
    response_model=JobAdderApplicationDetailResponse,
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
            "description": "JobAdder application detail read failed.",
        },
    },
)
def get_jobadder_application_detail_route(
    jobadder_account: int,
    application_id: int,
) -> JobAdderApplicationDetailResponse | JSONResponse:
    """
    Return one full JobAdder application record.

    Parameters
    ----------
    jobadder_account : int
        JobAdder account identifier used to locate the stored OAuth connection.

    application_id : int
        JobAdder application identifier requested by the route.

    Returns
    -------
    JobAdderApplicationDetailResponse | JSONResponse
        Full application response when the stored connection exists and the
        JobAdder API call succeeds.

    Notes
    -----
    This route exists for the first real applications persistence slice.

    The applications preview route is useful for discovery, but the persistence
    path needs a deterministic one-application read so it can safely persist
    the same upstream application even after the preview page ordering changes.

    Example
    -------
    A request looks like:

        GET /api/v1/integrations/jobadder/accounts/2236/applications/12204918

    and returns:

    - the JobAdder account context
    - the API URL used
    - the requested application ID
    - the full application object
    """
    stored_connection = _prepare_jobadder_connection_for_api_read(
        jobadder_account=jobadder_account
    )

    if isinstance(stored_connection, JSONResponse):
        return stored_connection

    detail_result = _perform_jobadder_read_with_refresh_retry(
        jobadder_account=jobadder_account,
        stored_connection=stored_connection,
        read_callable=lambda *, api_url, access_token: fetch_jobadder_application_detail(
            api_url=api_url,
            access_token=access_token,
            application_id=application_id,
        ),
        provider_failure_message="JobAdder application detail read failed.",
    )

    if isinstance(detail_result, JSONResponse):
        return detail_result

    application_detail, api_url, jobadder_instance = detail_result

    return JobAdderApplicationDetailResponse(
        jobadder_account=jobadder_account,
        jobadder_instance=jobadder_instance,
        api_url=api_url,
        application_id=application_id,
        application=application_detail["application"],
    )


@router.get(
    "/jobadder/accounts/{jobadder_account}/applications/{application_id}/attachments-preview",
    response_model=JobAdderApplicationAttachmentsResponse,
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
            "description": "JobAdder application attachments read failed.",
        },
    },
)
def get_jobadder_application_attachments_route(
    jobadder_account: int,
    application_id: int,
) -> JobAdderApplicationAttachmentsResponse | JSONResponse:
    """
    Return the attachment list for one JobAdder application.

    Parameters
    ----------
    jobadder_account : int
        JobAdder account identifier used to locate the stored OAuth connection.

    application_id : int
        JobAdder application identifier whose attachments should be fetched.

    Returns
    -------
    JobAdderApplicationAttachmentsResponse | JSONResponse
        Application attachments response when the stored connection exists and
        the JobAdder API call succeeds.

    Example
    -------
    A request looks like:

        GET /api/v1/integrations/jobadder/accounts/2236/applications/12204918/attachments-preview

    Notes
    -----
    We added this route specifically to test whether advert-response CV files
    live on the application record itself or only on the candidate record.
    """
    stored_connection = _prepare_jobadder_connection_for_api_read(
        jobadder_account=jobadder_account
    )

    if isinstance(stored_connection, JSONResponse):
        return stored_connection

    attachment_result = _perform_jobadder_read_with_refresh_retry(
        jobadder_account=jobadder_account,
        stored_connection=stored_connection,
        read_callable=lambda *, api_url, access_token: fetch_jobadder_application_attachments(
            api_url=api_url,
            access_token=access_token,
            application_id=application_id,
        ),
        provider_failure_message="JobAdder application attachments read failed.",
    )

    if isinstance(attachment_result, JSONResponse):
        return attachment_result

    attachments_result, api_url, jobadder_instance = attachment_result

    return JobAdderApplicationAttachmentsResponse(
        jobadder_account=jobadder_account,
        jobadder_instance=jobadder_instance,
        api_url=api_url,
        application_id=application_id,
        attachment_count=attachments_result["attachment_count"],
        links=attachments_result["links"],
        attachments=attachments_result["items"],
    )


@router.get(
    "/jobadder/accounts/{jobadder_account}/applications-preview",
    response_model=JobAdderApplicationsPreviewResponse,
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
            "description": "JobAdder applications read failed.",
        },
    },
)
def get_jobadder_applications_preview_route(
    jobadder_account: int,
    item_limit: int = Query(
        default=10,
        ge=1,
        le=25,
        description=(
            "Maximum number of application items to return from the first page "
            "of the JobAdder response."
        ),
    ),
    active_only: bool = Query(
        default=False,
        description="Whether to request only active applications.",
    ),
    rejected_only: bool = Query(
        default=False,
        description="Whether to request only rejected applications.",
    ),
) -> JobAdderApplicationsPreviewResponse | JSONResponse:
    """
    Return a small first-page preview of JobAdder applications.

    Parameters
    ----------
    jobadder_account : int
        JobAdder account identifier used to locate the stored OAuth connection.

    item_limit : int
        Maximum number of application items to return from the first page of
        the JobAdder response.

    active_only : bool
        Whether to request only active applications.

    rejected_only : bool
        Whether to request only rejected applications.

    Returns
    -------
    JobAdderApplicationsPreviewResponse | JSONResponse
        First-page application preview when the stored connection exists and
        the JobAdder API call succeeds.

    Example
    -------
    A request looks like:

        GET /api/v1/integrations/jobadder/accounts/2236/applications-preview?active_only=true

    Notes
    -----
    This route is currently the most useful advert-response discovery surface.
    In the live account, it proved more informative than `jobads-preview`
    because applications were present even when the top-level job-ad preview
    returned zero rows.
    """
    if active_only and rejected_only:
        return build_error_response(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            code="validation_error",
            message=(
                "JobAdder applications preview cannot request both active_only "
                "and rejected_only."
            ),
            details=[
                {"query_params": ["active_only", "rejected_only"]},
                {"reason": "mutually_exclusive"},
            ],
        )

    stored_connection = _prepare_jobadder_connection_for_api_read(
        jobadder_account=jobadder_account
    )

    if isinstance(stored_connection, JSONResponse):
        return stored_connection

    preview_result = _perform_jobadder_read_with_refresh_retry(
        jobadder_account=jobadder_account,
        stored_connection=stored_connection,
        read_callable=lambda *, api_url, access_token: fetch_jobadder_applications_preview(
            api_url=api_url,
            access_token=access_token,
            item_limit=item_limit,
            active_only=active_only,
            rejected_only=rejected_only,
        ),
        provider_failure_message="JobAdder applications read failed.",
    )

    if isinstance(preview_result, JSONResponse):
        return preview_result

    preview, api_url, jobadder_instance = preview_result

    return JobAdderApplicationsPreviewResponse(
        jobadder_account=jobadder_account,
        jobadder_instance=jobadder_instance,
        api_url=api_url,
        active_only=active_only,
        rejected_only=rejected_only,
        item_count=preview["item_count"],
        total_count=preview["total_count"],
        links=preview["links"],
        applications=preview["items"],
    )


@router.get(
    "/jobadder/accounts/{jobadder_account}/jobs/{job_id}",
    response_model=JobAdderJobDetailResponse,
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
            "description": "JobAdder job read failed.",
        },
    },
)
def get_jobadder_job_detail_route(
    jobadder_account: int,
    job_id: int,
) -> JobAdderJobDetailResponse | JSONResponse:
    """
    Return one full JobAdder job/opportunity record.

    Parameters
    ----------
    jobadder_account : int
        JobAdder account identifier used to locate the stored OAuth connection.

    job_id : int
        JobAdder job identifier requested by the route.

    Returns
    -------
    JobAdderJobDetailResponse | JSONResponse
        Full JobAdder job detail when the stored connection exists and the
        provider read succeeds.

    Example
    -------
    A request looks like:

        GET /api/v1/integrations/jobadder/accounts/2236/jobs/936462

    Notes
    -----
    This route exists to compare the structured JobAdder opportunity record
    against Dropbox job-spec folders and job-spec PDFs that share the same
    `tw...` vacancy code.
    """
    stored_connection = _prepare_jobadder_connection_for_api_read(
        jobadder_account=jobadder_account
    )

    if isinstance(stored_connection, JSONResponse):
        return stored_connection

    detail_result = _perform_jobadder_read_with_refresh_retry(
        jobadder_account=jobadder_account,
        stored_connection=stored_connection,
        read_callable=lambda *, api_url, access_token: fetch_jobadder_job_detail(
            api_url=api_url,
            access_token=access_token,
            job_id=job_id,
        ),
        provider_failure_message="JobAdder job read failed.",
    )

    if isinstance(detail_result, JSONResponse):
        return detail_result

    job_detail, api_url, jobadder_instance = detail_result

    return JobAdderJobDetailResponse(
        jobadder_account=jobadder_account,
        jobadder_instance=jobadder_instance,
        api_url=api_url,
        job_id=job_id,
        job=job_detail["job"],
    )


@router.get(
    "/jobadder/accounts/{jobadder_account}/jobs/{job_id}/applications-preview",
    response_model=JobAdderJobApplicationsPreviewResponse,
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
            "description": "JobAdder job applications read failed.",
        },
    },
)
def get_jobadder_job_applications_preview_route(
    jobadder_account: int,
    job_id: int,
    item_limit: int = Query(
        default=10,
        ge=1,
        le=100,
        description=(
            "Maximum number of application items to return from the first page "
            "of the JobAdder response."
        ),
    ),
) -> JobAdderJobApplicationsPreviewResponse | JSONResponse:
    """
    Return a small first-page preview of applications for one JobAdder job.

    Parameters
    ----------
    jobadder_account : int
        JobAdder account identifier used to locate the stored OAuth connection.

    job_id : int
        JobAdder job identifier whose applications should be fetched.

    item_limit : int
        Maximum number of application items to return from the first page of
        the JobAdder response.

    Returns
    -------
    JobAdderJobApplicationsPreviewResponse | JSONResponse
        First-page application preview for the requested job when the stored
        connection exists and the provider read succeeds.

    Notes
    -----
    This route exists for vacancy-aware reconciliation work.

    It lets the backend ask a narrower question than the top-level
    applications preview:

        "Show me the applications for this one known opportunity."

    Example
    -------
    A request looks like:

        GET /api/v1/integrations/jobadder/accounts/2236/jobs/891841/applications-preview?item_limit=25
    """
    stored_connection = _prepare_jobadder_connection_for_api_read(
        jobadder_account=jobadder_account
    )

    if isinstance(stored_connection, JSONResponse):
        return stored_connection

    preview_result = _perform_jobadder_read_with_refresh_retry(
        jobadder_account=jobadder_account,
        stored_connection=stored_connection,
        read_callable=lambda *, api_url, access_token: fetch_jobadder_job_applications_preview(
            api_url=api_url,
            access_token=access_token,
            job_id=job_id,
            item_limit=item_limit,
        ),
        provider_failure_message="JobAdder job applications read failed.",
    )

    if isinstance(preview_result, JSONResponse):
        return preview_result

    preview, api_url, jobadder_instance = preview_result

    return JobAdderJobApplicationsPreviewResponse(
        jobadder_account=jobadder_account,
        jobadder_instance=jobadder_instance,
        api_url=api_url,
        job_id=job_id,
        item_count=preview["item_count"],
        total_count=preview["total_count"],
        links=preview["links"],
        applications=preview["items"],
    )


@router.get(
    "/jobadder/accounts/{jobadder_account}/jobads-preview",
    response_model=JobAdderJobAdsPreviewResponse,
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
            "description": "JobAdder job-ad read failed.",
        },
    },
)
def get_jobadder_jobads_preview_route(
    jobadder_account: int,
    item_limit: int = Query(
        default=10,
        ge=1,
        le=25,
        description=(
            "Maximum number of job-ad items to return from the first page of "
            "the JobAdder response."
        ),
    ),
) -> JobAdderJobAdsPreviewResponse | JSONResponse:
    """
    Return a small first-page preview of job ads from the connected JobAdder
    account.

    Parameters
    ----------
    jobadder_account : int
        JobAdder account identifier used to locate the stored OAuth connection.

    item_limit : int
        Maximum number of job-ad items to return from the first page of the
        JobAdder response.

    Returns
    -------
    JobAdderJobAdsPreviewResponse | JSONResponse
        First-page job-ad preview when the stored connection exists and the
        JobAdder API call succeeds.

        Standard API error response when the stored connection cannot be found,
        is missing required fields, the token refresh fails, or the provider
        read fails.

    Example
    -------
    A request looks like:

        GET /api/v1/integrations/jobadder/accounts/2236/jobads-preview

    In plain language:

    - load the stored JobAdder connection
    - refresh the token first if needed
    - use the working token to call the job-ads endpoint
    - retry once with a refreshed token if JobAdder rejects the first attempt
    - return a small preview of job-ad data
    """
    stored_connection = _prepare_jobadder_connection_for_api_read(
        jobadder_account=jobadder_account
    )

    if isinstance(stored_connection, JSONResponse):
        return stored_connection

    preview_result = _perform_jobadder_read_with_refresh_retry(
        jobadder_account=jobadder_account,
        stored_connection=stored_connection,
        read_callable=lambda *, api_url, access_token: fetch_jobadder_jobads_preview(
            api_url=api_url,
            access_token=access_token,
            item_limit=item_limit,
        ),
        provider_failure_message="JobAdder job-ad read failed.",
    )

    if isinstance(preview_result, JSONResponse):
        return preview_result

    preview, api_url, jobadder_instance = preview_result

    return JobAdderJobAdsPreviewResponse(
        jobadder_account=jobadder_account,
        jobadder_instance=jobadder_instance,
        api_url=api_url,
        item_count=preview["item_count"],
        total_count=preview["total_count"],
        links=preview["links"],
        jobads=preview["items"],
    )


@router.get(
    "/jobadder/accounts/{jobadder_account}/jobads/{ad_id}/applications-preview",
    response_model=JobAdderJobAdApplicationsPreviewResponse,
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
            "description": "JobAdder job-ad applications read failed.",
        },
    },
)
def get_jobadder_jobad_applications_preview_route(
    jobadder_account: int,
    ad_id: int,
    item_limit: int = Query(
        default=10,
        ge=1,
        le=25,
        description=(
            "Maximum number of application items to return from the first page "
            "of the JobAdder response."
        ),
    ),
    active_only: bool = Query(
        default=False,
        description=(
            "Whether to preview only active applications using the dedicated "
            "JobAdder active-applications endpoint."
        ),
    ),
) -> JobAdderJobAdApplicationsPreviewResponse | JSONResponse:
    """
    Return a small first-page preview of applications for one JobAdder job ad.

    Parameters
    ----------
    jobadder_account : int
        JobAdder account identifier used to locate the stored OAuth connection.

    ad_id : int
        JobAdder job-ad identifier whose applications should be fetched.

    item_limit : int
        Maximum number of application items to return from the first page of
        the JobAdder response.

    active_only : bool
        Whether to read only active applications.

    Returns
    -------
    JobAdderJobAdApplicationsPreviewResponse | JSONResponse
        First-page application preview when the stored connection exists and
        the JobAdder API call succeeds.

        Standard API error response when the stored connection cannot be found,
        is missing required fields, the token refresh fails, or the provider
        read fails.

    Example
    -------
    A request looks like:

        GET /api/v1/integrations/jobadder/accounts/2236/jobads/12345/applications-preview?active_only=true

    In plain language:

    - load the stored JobAdder connection
    - refresh the token first if needed
    - call the job-ad applications endpoint
    - optionally use the active-only path
    - return a small preview of application data
    """
    stored_connection = _prepare_jobadder_connection_for_api_read(
        jobadder_account=jobadder_account
    )

    if isinstance(stored_connection, JSONResponse):
        return stored_connection

    preview_result = _perform_jobadder_read_with_refresh_retry(
        jobadder_account=jobadder_account,
        stored_connection=stored_connection,
        read_callable=lambda *, api_url, access_token: fetch_jobadder_jobad_applications_preview(
            api_url=api_url,
            access_token=access_token,
            ad_id=ad_id,
            item_limit=item_limit,
            active_only=active_only,
        ),
        provider_failure_message="JobAdder job-ad applications read failed.",
    )

    if isinstance(preview_result, JSONResponse):
        return preview_result

    preview, api_url, jobadder_instance = preview_result

    return JobAdderJobAdApplicationsPreviewResponse(
        jobadder_account=jobadder_account,
        jobadder_instance=jobadder_instance,
        api_url=api_url,
        ad_id=ad_id,
        active_only=active_only,
        item_count=preview["item_count"],
        total_count=preview["total_count"],
        links=preview["links"],
        applications=preview["items"],
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

                if retry_exc.response_body is not None:
                    details.append(
                        {"provider_response_body": retry_exc.response_body}
                    )

                if retry_exc.request_payload is not None:
                    details.append(
                        {"provider_request_payload": retry_exc.request_payload}
                    )

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

        if exc.response_body is not None:
            details.append({"provider_response_body": exc.response_body})

        if exc.request_payload is not None:
            details.append({"provider_request_payload": exc.request_payload})

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

    requested_scope_items = _split_scope_string(DEFAULT_DROPBOX_SCOPE)
    granted_scope_items = _split_scope_string(token_set.scope)
    granted_scope_set = set(granted_scope_items)
    missing_requested_scopes = [
        scope_item
        for scope_item in requested_scope_items
        if scope_item not in granted_scope_set
    ]

    return DropboxOAuthConnectionSavedResponse(
        status="connected",
        message="Dropbox connection completed successfully.",
        oauth_connection_id=str(saved_connection["id"]),
        dropbox_account_id=str(saved_connection["dropbox_account_id"]),
        requested_scope=DEFAULT_DROPBOX_SCOPE,
        granted_scope=token_set.scope,
        missing_requested_scopes=missing_requested_scopes,
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
    folder_path: str = Query(
        default="",
        description=(
            "Dropbox folder path to inspect. Use the empty string to list the "
            "root folder. This parameter is deliberately named `folder_path` "
            "instead of `path` to avoid deployed-runtime collisions."
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
    - The public query parameter is named `folder_path` rather than `path`.
      Some deployed runtimes treat `path` as reserved request-path plumbing,
      which can otherwise leak the API route path into the Dropbox request
      payload.

    Example
    -------
    A request looks like:

        GET /api/v1/integrations/dropbox/accounts/dbid:AAExample/files/list-folder?folder_path=
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
            path=folder_path,
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


@router.get(
    "/dropbox/accounts/{dropbox_account_id}/files/zip-members-preview",
    response_model=DropboxZipMembersPreviewResponse,
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
            "description": "Dropbox ZIP inspection failed.",
        },
    },
)
def get_dropbox_zip_members_preview_route(
    dropbox_account_id: str,
    file_path: str = Query(
        ...,
        min_length=1,
        description="Full Dropbox path of the ZIP file to inspect.",
    ),
    member_prefix: str | None = Query(
        default=None,
        description=(
            "Optional ZIP member prefix filter such as `candidate/` or `job/`."
        ),
    ),
    limit: int = Query(
        default=100,
        ge=1,
        le=500,
        description="Maximum number of ZIP members to return in the preview.",
    ),
) -> DropboxZipMembersPreviewResponse | JSONResponse:
    """
    Return a bounded structural preview of a Dropbox ZIP file.

    Parameters
    ----------
    dropbox_account_id : str
        Dropbox account identifier used to locate the stored OAuth connection.

    file_path : str
        Full Dropbox path of the ZIP archive to inspect.

    member_prefix : str | None
        Optional ZIP member prefix filter used to narrow the preview.

    limit : int
        Maximum number of ZIP members to expose in the preview response.

    Returns
    -------
    DropboxZipMembersPreviewResponse | JSONResponse
        ZIP structure preview on success, otherwise a ready-to-return API
        error response.

    Notes
    -----
    - This route downloads the ZIP transiently, inspects its member list, and
      returns structural metadata only.
    - It exists to inspect static export shape safely before building the
      importer itself.

    Example
    -------
    A request looks like:

        GET /api/v1/integrations/dropbox/accounts/dbid:AAExample/files/zip-members-preview?file_path=/exports/Recruiterflow.zip&member_prefix=candidate/
    """
    stored_connection = _prepare_dropbox_connection_for_api_read(
        dropbox_account_id=dropbox_account_id
    )

    if isinstance(stored_connection, JSONResponse):
        return stored_connection

    download_result = _perform_dropbox_read_with_refresh_retry(
        dropbox_account_id=dropbox_account_id,
        stored_connection=stored_connection,
        read_callable=lambda *, access_token: download_dropbox_file(
            access_token=access_token,
            path=file_path,
        ),
        provider_failure_message="Dropbox ZIP inspection failed.",
    )

    if isinstance(download_result, JSONResponse):
        return download_result

    content_bytes = download_result["content_bytes"]

    try:
        with ZipFile(BytesIO(content_bytes)) as archive:
            members = archive.infolist()
            if member_prefix:
                members = [
                    member
                    for member in members
                    if member.filename.startswith(member_prefix)
                ]
            preview_entries = [
                {
                    "name": member.filename,
                    "is_dir": member.is_dir(),
                    "file_size": member.file_size,
                    "compress_size": member.compress_size,
                }
                for member in members[:limit]
            ]
            # Top-level names give us the first import clue quickly: whether the
            # archive is mostly flat CSV exports, nested attachment folders, or
            # a mixed backup structure that needs staged handling.
            top_level_entries = sorted(
                {
                    member.filename.split("/", 1)[0]
                    for member in members
                    if member.filename.strip() != ""
                }
            )
    except BadZipFile:
        return build_error_response(
            status_code=status.HTTP_502_BAD_GATEWAY,
            code="internal_error",
            message="Dropbox ZIP inspection failed.",
            details=[
                {"dropbox_account_id": dropbox_account_id},
                {"file_path": file_path},
                {"reason": "The downloaded Dropbox file is not a valid ZIP archive."},
            ],
        )

    return DropboxZipMembersPreviewResponse(
        dropbox_account_id=dropbox_account_id,
        file_path=file_path,
        file_name=download_result["file_name"],
        byte_count=len(content_bytes),
        entry_count=len(members),
        top_level_entries=top_level_entries,
        preview_entries=preview_entries,
    )


@router.get(
    "/dropbox/accounts/{dropbox_account_id}/files/zip-json-member-preview",
    response_model=DropboxZipJsonMemberPreviewResponse,
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
            "description": "Dropbox ZIP JSON preview failed.",
        },
    },
)
def get_dropbox_zip_json_member_preview_route(
    dropbox_account_id: str,
    file_path: str = Query(
        ...,
        min_length=1,
        description="Full Dropbox path of the ZIP file to inspect.",
    ),
    member_name: str = Query(
        ...,
        min_length=1,
        description="ZIP member path to parse as JSON.",
    ),
    preview_limit: int = Query(
        default=3,
        ge=1,
        le=20,
        description="Maximum number of top-level items or keys to include in the preview.",
    ),
) -> DropboxZipJsonMemberPreviewResponse | JSONResponse:
    """
    Return a bounded JSON preview for one member inside a Dropbox ZIP file.

    Parameters
    ----------
    dropbox_account_id : str
        Dropbox account identifier used to locate the stored OAuth connection.

    file_path : str
        Full Dropbox path of the ZIP archive to inspect.

    member_name : str
        ZIP member path to parse as JSON.

    preview_limit : int
        Maximum number of items or keys to expose in the preview payload.

    Returns
    -------
    DropboxZipJsonMemberPreviewResponse | JSONResponse
        JSON member preview on success, otherwise a ready-to-return API error
        response.

    Notes
    -----
    - This route is intentionally bounded. It exists for importer design and
      schema mapping rather than full export delivery.
    - It is especially useful for Recruiterflow-style chunked exports such as
      `candidate/1.100.json` and `job/1.100.json`.

    Example
    -------
    A request looks like:

        GET /api/v1/integrations/dropbox/accounts/dbid:AAExample/files/zip-json-member-preview?file_path=/exports/Recruiterflow.zip&member_name=candidate/1.100.json
    """
    stored_connection = _prepare_dropbox_connection_for_api_read(
        dropbox_account_id=dropbox_account_id
    )

    if isinstance(stored_connection, JSONResponse):
        return stored_connection

    download_result = _perform_dropbox_read_with_refresh_retry(
        dropbox_account_id=dropbox_account_id,
        stored_connection=stored_connection,
        read_callable=lambda *, access_token: download_dropbox_file(
            access_token=access_token,
            path=file_path,
        ),
        provider_failure_message="Dropbox ZIP JSON preview failed.",
    )

    if isinstance(download_result, JSONResponse):
        return download_result

    try:
        with ZipFile(BytesIO(download_result["content_bytes"])) as archive:
            try:
                member_bytes = archive.read(member_name)
            except KeyError:
                return build_error_response(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    code="internal_error",
                    message="Dropbox ZIP JSON preview failed.",
                    details=[
                        {"dropbox_account_id": dropbox_account_id},
                        {"file_path": file_path},
                        {"member_name": member_name},
                        {"reason": "The requested ZIP member was not found."},
                    ],
                )
    except BadZipFile:
        return build_error_response(
            status_code=status.HTTP_502_BAD_GATEWAY,
            code="internal_error",
            message="Dropbox ZIP JSON preview failed.",
            details=[
                {"dropbox_account_id": dropbox_account_id},
                {"file_path": file_path},
                {"reason": "The downloaded Dropbox file is not a valid ZIP archive."},
            ],
        )

    try:
        decoded_text = member_bytes.decode("utf-8")
        parsed_payload = json.loads(decoded_text)
    except (UnicodeDecodeError, json.JSONDecodeError):
        return build_error_response(
            status_code=status.HTTP_502_BAD_GATEWAY,
            code="internal_error",
            message="Dropbox ZIP JSON preview failed.",
            details=[
                {"dropbox_account_id": dropbox_account_id},
                {"file_path": file_path},
                {"member_name": member_name},
                {"reason": "The requested ZIP member is not valid UTF-8 JSON."},
            ],
        )

    if isinstance(parsed_payload, dict):
        keys = list(parsed_payload.keys())
        preview_payload = {
            key: parsed_payload[key]
            for key in keys[:preview_limit]
        }
        return DropboxZipJsonMemberPreviewResponse(
            dropbox_account_id=dropbox_account_id,
            file_path=file_path,
            member_name=member_name,
            top_level_type="dict",
            entry_count=None,
            key_count=len(keys),
            keys_preview=keys[: min(50, len(keys))],
            sample_item_keys=[],
            preview_payload=preview_payload,
        )

    if isinstance(parsed_payload, list):
        preview_payload = parsed_payload[:preview_limit]
        sample_item_keys: list[str] = []

        if preview_payload and isinstance(preview_payload[0], dict):
            # The first object item usually gives the fastest schema read for
            # chunked export files, while keeping the response small enough for
            # operator review and route-based inspection.
            sample_item_keys = list(preview_payload[0].keys())[:50]

        return DropboxZipJsonMemberPreviewResponse(
            dropbox_account_id=dropbox_account_id,
            file_path=file_path,
            member_name=member_name,
            top_level_type="list",
            entry_count=len(parsed_payload),
            key_count=None,
            keys_preview=[],
            sample_item_keys=sample_item_keys,
            preview_payload=preview_payload,
        )

    return build_error_response(
        status_code=status.HTTP_502_BAD_GATEWAY,
        code="internal_error",
        message="Dropbox ZIP JSON preview failed.",
        details=[
            {"dropbox_account_id": dropbox_account_id},
            {"file_path": file_path},
            {"member_name": member_name},
            {"reason": "The requested ZIP member did not contain a JSON object or list."},
        ],
    )


def _refresh_outlook_stored_connection(
    *,
    microsoft_user_id: str,
    refresh_token_value: Any,
    stored_connection: dict[str, Any],
) -> dict[str, Any] | JSONResponse:
    """
    Refresh the stored Outlook token set and persist the replacement row.

    Parameters
    ----------
    microsoft_user_id : str
        Natural key for the stored Outlook OAuth connection.

    refresh_token_value : Any
        Raw refresh-token value currently stored in Postgres.

    stored_connection : dict[str, Any]
        Existing persisted Outlook connection row used to preserve stable
        metadata if Microsoft omits it from the refresh response.

    Returns
    -------
    dict[str, Any] | JSONResponse
        Updated stored connection row on success, otherwise a ready-to-return
        API error response.

    Notes
    -----
    - Microsoft refresh responses can omit fields we still care about locally,
      such as the previous refresh token, tenant ID, or mailbox login.
    - This helper therefore merges the new token response with the stable
      stored metadata before saving the replacement row.

    Example
    -------
    This helper is used when:

    - a stored token is already expired before the first Graph read
    - a Graph read comes back with `401` and a refresh/retry is needed
    """

    if not isinstance(refresh_token_value, str) or refresh_token_value.strip() == "":
        return build_error_response(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            code="internal_error",
            message="The stored Outlook connection is missing a refresh token.",
            details=[{"microsoft_user_id": microsoft_user_id}],
        )

    try:
        refreshed_token_set = refresh_outlook_access_token(
            refresh_token=refresh_token_value,
        )
    except OutlookOAuthExchangeError as exc:
        details: list[dict[str, Any]] = [{"microsoft_user_id": microsoft_user_id}]

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
            message="Outlook token refresh failed.",
            details=details,
        )

    # Microsoft refresh responses are not guaranteed to repeat every identity
    # hint we captured earlier. Preserve the stable stored metadata so the
    # refreshed row remains fully usable for later reads and debugging.
    merged_raw_payload = dict(refreshed_token_set.raw_payload)

    merged_raw_payload.setdefault("refresh_token", refresh_token_value)
    merged_raw_payload.setdefault("oid", stored_connection.get("microsoft_user_id"))
    merged_raw_payload.setdefault("tid", stored_connection.get("tenant_id"))
    merged_raw_payload.setdefault(
        "preferred_username",
        stored_connection.get("user_principal_name"),
    )

    refreshed_token_set = OutlookTokenSet(
        access_token=refreshed_token_set.access_token,
        token_type=refreshed_token_set.token_type,
        expires_in=refreshed_token_set.expires_in,
        refresh_token=(
            refreshed_token_set.refresh_token
            or refresh_token_value
        ),
        scope=refreshed_token_set.scope or stored_connection.get("scope"),
        microsoft_user_id=(
            refreshed_token_set.microsoft_user_id
            or stored_connection.get("microsoft_user_id")
        ),
        tenant_id=refreshed_token_set.tenant_id or stored_connection.get("tenant_id"),
        user_principal_name=(
            refreshed_token_set.user_principal_name
            or stored_connection.get("user_principal_name")
        ),
        raw_payload=merged_raw_payload,
    )

    try:
        return save_outlook_oauth_connection(refreshed_token_set)
    except Exception as exc:
        return build_error_response(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            code="internal_error",
            message="Outlook token refresh succeeded, but the refreshed connection could not be saved.",
            details=[
                {"microsoft_user_id": microsoft_user_id},
                {"reason": str(exc)},
            ],
        )


def _prepare_outlook_connection_for_api_read(
    *,
    microsoft_user_id: str,
) -> dict[str, Any] | JSONResponse:
    """
    Load one stored Outlook connection row and ensure it is ready for a Graph
    API read.

    Parameters
    ----------
    microsoft_user_id : str
        Microsoft user identifier used to locate the stored connection row.

    Returns
    -------
    dict[str, Any] | JSONResponse
        Usable stored connection row when the backend can proceed with a Graph
        read, otherwise a ready-to-return API error response.

    Example
    -------
    A route can call:

        stored_connection = _prepare_outlook_connection_for_api_read(
            microsoft_user_id="aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
        )

    and then either:

    - perform the Graph read immediately
    - or return the already-built error response
    """

    stored_connection = get_outlook_oauth_connection(microsoft_user_id)

    if stored_connection is None:
        return build_error_response(
            status_code=status.HTTP_404_NOT_FOUND,
            code="not_found",
            message="Stored Outlook connection was not found.",
            details=[{"microsoft_user_id": microsoft_user_id}],
        )

    access_token = stored_connection.get("access_token")

    if not isinstance(access_token, str) or access_token.strip() == "":
        return build_error_response(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            code="internal_error",
            message="The stored Outlook connection is missing an access token.",
            details=[{"microsoft_user_id": microsoft_user_id}],
        )

    obtained_at = stored_connection.get("obtained_at")
    expires_in_seconds = stored_connection.get("expires_in_seconds")

    # Refresh proactively when the stored timing data says the token is
    # expired or too close to expiry. That gives the first Graph read the best
    # available credential state instead of waiting for a predictable `401`.
    if (
        obtained_at is not None
        and isinstance(expires_in_seconds, int)
        and is_outlook_access_token_expired(
            obtained_at=obtained_at,
            expires_in_seconds=expires_in_seconds,
        )
    ):
        refreshed_connection = _refresh_outlook_stored_connection(
            microsoft_user_id=microsoft_user_id,
            refresh_token_value=stored_connection.get("refresh_token"),
            stored_connection=stored_connection,
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
                message="The refreshed Outlook connection is missing an access token.",
                details=[{"microsoft_user_id": microsoft_user_id}],
            )

        return refreshed_connection

    return stored_connection


def _perform_outlook_read_with_refresh_retry(
    *,
    microsoft_user_id: str,
    stored_connection: dict[str, Any],
    read_callable,
    provider_failure_message: str,
) -> dict[str, Any] | JSONResponse:
    """
    Perform one Graph read and retry once with a refreshed token after `401`.

    Parameters
    ----------
    microsoft_user_id : str
        Microsoft user identifier used for error reporting and refresh saves.

    stored_connection : dict[str, Any]
        Stored Outlook connection row that already passed the initial local
        validation checks.

    read_callable : callable
        Small function that accepts keyword argument `access_token` and performs
        one Graph read.

    provider_failure_message : str
        Safe route-level message to use if Graph rejects the read.

    Returns
    -------
    dict[str, Any] | JSONResponse
        Normalized read result on success, otherwise a ready-to-return API
        error response.

    Notes
    -----
    - The only provider failure treated as recoverable here is `401`.
    - The retry policy is deliberately narrow:
        - refresh once
        - retry once
        - surface the failure clearly if Graph still rejects the call

    Example
    -------
    Routes can pass lambdas such as:

        lambda *, access_token: fetch_outlook_current_user(
            access_token=access_token
        )
    """

    access_token = stored_connection.get("access_token")
    if not isinstance(access_token, str) or access_token.strip() == "":
        return build_error_response(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            code="internal_error",
            message="The stored Outlook connection is missing an access token.",
            details=[{"microsoft_user_id": microsoft_user_id}],
        )

    try:
        return read_callable(access_token=access_token)
    except OutlookApiError as exc:
        if exc.status_code == status.HTTP_401_UNAUTHORIZED:
            refreshed_connection = _refresh_outlook_stored_connection(
                microsoft_user_id=microsoft_user_id,
                refresh_token_value=stored_connection.get("refresh_token"),
                stored_connection=stored_connection,
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
                    message="The refreshed Outlook connection is missing an access token.",
                    details=[{"microsoft_user_id": microsoft_user_id}],
                )

            try:
                return read_callable(access_token=refreshed_access_token)
            except OutlookApiError as retry_exc:
                details: list[dict[str, Any]] = [
                    {"microsoft_user_id": microsoft_user_id}
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

        details: list[dict[str, Any]] = [{"microsoft_user_id": microsoft_user_id}]

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


def _ensure_outlook_token_set_has_user_identity(
    *,
    token_set: OutlookTokenSet,
) -> OutlookTokenSet:
    """
    Ensure one Outlook token set carries a usable Microsoft user identifier.

    Notes
    -----
    Microsoft does not always return the identity hints we want in the token
    response itself. In particular, the delegated token exchange can succeed
    while omitting the `oid` claim we use as the natural key for persisted
    Outlook connections.

    In that case, the safest recovery path is:

    1. keep the access token we just received
    2. call Graph `/me`
    3. use the returned user `id` and `userPrincipalName` to enrich the
       token set before persistence

    Example
    -------
    A callback flow can do:

        token_set = exchange_outlook_authorization_code(code="...")
        token_set = _ensure_outlook_token_set_has_user_identity(
            token_set=token_set
        )

    and then persist the enriched token set normally.
    """

    if (
        isinstance(token_set.microsoft_user_id, str)
        and token_set.microsoft_user_id.strip() != ""
    ):
        return token_set

    current_user_result = fetch_outlook_current_user(
        access_token=token_set.access_token
    )
    current_user = current_user_result.get("user", {})

    microsoft_user_id = current_user.get("id")
    user_principal_name = (
        current_user.get("userPrincipalName")
        or current_user.get("mail")
        or token_set.user_principal_name
    )

    if (
        not isinstance(microsoft_user_id, str)
        or microsoft_user_id.strip() == ""
    ):
        raise RuntimeError(
            "Outlook token set did not include a usable Microsoft user identifier."
        )

    merged_raw_payload = dict(token_set.raw_payload)
    merged_raw_payload.setdefault("resolved_current_user", current_user)

    return replace(
        token_set,
        microsoft_user_id=microsoft_user_id.strip(),
        user_principal_name=(
            user_principal_name.strip()
            if isinstance(user_principal_name, str)
            and user_principal_name.strip() != ""
            else None
        ),
        raw_payload=merged_raw_payload,
    )

@router.get(
    "/outlook/authorize",
    response_model=OutlookAuthorizationUrlResponse,
    responses={
        401: {
            "model": ApiErrorResponse,
            "description": "Outlook OAuth is not configured.",
        }
    },
)
def get_outlook_authorization_url_route(
    state: str | None = Query(
        default=None,
        description=(
            "Optional opaque state value to round-trip through the Outlook "
            "approval flow."
        ),
    ),
) -> OutlookAuthorizationUrlResponse | JSONResponse:
    """
    Return a ready-to-open Outlook authorization URL.

    Example
    -------
    A request looks like:

        GET /api/v1/integrations/outlook/authorize?state=connect-outlook-dev
    """

    if not has_outlook_oauth_configuration():
        return build_error_response(
            status_code=status.HTTP_401_UNAUTHORIZED,
            code="unauthorized",
            message="Outlook OAuth is not configured.",
            details=[
                {
                    "required_settings": [
                        "MICROSOFT_CLIENT_ID",
                        "MICROSOFT_REDIRECT_URI",
                    ]
                }
            ],
        )

    try:
        authorization_url = build_outlook_authorization_url(state=state)
    except ValueError as exc:
        return build_error_response(
            status_code=status.HTTP_401_UNAUTHORIZED,
            code="unauthorized",
            message=str(exc),
        )

    return OutlookAuthorizationUrlResponse(
        authorization_url=authorization_url,
        oauth_configuration_ready=True,
        state=state,
    )


@router.get(
    "/outlook/callback",
    response_model=OutlookOAuthConnectionSavedResponse,
    responses={
        400: {"model": ApiErrorResponse, "description": "Outlook authorization was not completed."},
        401: {"model": ApiErrorResponse, "description": "Outlook token exchange is not configured."},
        422: {"model": ApiErrorResponse, "description": "Outlook authorization code is required."},
        500: {"model": ApiErrorResponse, "description": "Outlook token exchange succeeded but saving failed."},
        502: {"model": ApiErrorResponse, "description": "Outlook token exchange failed."},
    },
)
def complete_outlook_oauth_callback_route(
    code: str | None = Query(
        default=None,
        description="One-time Microsoft authorization code returned by the callback.",
    ),
    state: str | None = Query(
        default=None,
        description="Optional opaque state value originally sent to Microsoft.",
    ),
    error: str | None = Query(
        default=None,
        description="Optional Microsoft OAuth error code returned by the provider.",
    ),
    error_description: str | None = Query(
        default=None,
        description="Optional human-readable Microsoft OAuth error description returned by the provider.",
    ),
) -> OutlookOAuthConnectionSavedResponse | JSONResponse:
    """
    Complete the Outlook OAuth callback by exchanging the code and saving the
    resulting token set.

    Example
    -------
    A successful callback request looks like:

        GET /api/v1/integrations/outlook/callback?code=...
    """

    if error is not None:
        details: list[dict[str, Any]] = [{"provider": "microsoft", "error": error}]
        if error_description:
            details.append({"provider_error_description": error_description})
        if state:
            details.append({"state": state})

        return build_error_response(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="unauthorized",
            message="Outlook authorization was not completed.",
            details=details,
        )

    if code is None or code.strip() == "":
        return build_error_response(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            code="validation_error",
            message="Outlook authorization code is required.",
            details=[{"query_param": "code", "reason": "missing_or_empty"}],
        )

    if not has_outlook_token_exchange_configuration():
        return build_error_response(
            status_code=status.HTTP_401_UNAUTHORIZED,
            code="unauthorized",
            message="Outlook token exchange is not configured.",
            details=[
                {
                    "required_settings": [
                        "MICROSOFT_CLIENT_ID",
                        "MICROSOFT_CLIENT_SECRET",
                        "MICROSOFT_REDIRECT_URI",
                    ]
                }
            ],
        )

    try:
        token_set = exchange_outlook_authorization_code(code=code)
    except OutlookOAuthExchangeError as exc:
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
            message="Outlook token exchange failed.",
            details=details,
        )

    try:
        token_set = _ensure_outlook_token_set_has_user_identity(
            token_set=token_set
        )
    except OutlookApiError as exc:
        details: list[dict[str, Any]] = []

        if exc.status_code is not None:
            details.append({"provider_status_code": exc.status_code})
        if exc.endpoint_url is not None:
            details.append({"endpoint_url": exc.endpoint_url})
        if state:
            details.append({"state": state})

        return build_error_response(
            status_code=status.HTTP_502_BAD_GATEWAY,
            code="internal_error",
            message=(
                "Outlook token exchange succeeded, but the connected "
                "Microsoft user could not be resolved."
            ),
            details=details,
        )
    except RuntimeError as exc:
        details: list[dict[str, Any]] = [{"reason": str(exc)}]
        if state:
            details.append({"state": state})

        return build_error_response(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            code="internal_error",
            message=(
                "Outlook token exchange succeeded, but the connected "
                "Microsoft user could not be resolved."
            ),
            details=details,
        )

    try:
        saved_connection = save_outlook_oauth_connection(token_set)
    except Exception as exc:
        details: list[dict[str, Any]] = [{"reason": str(exc)}]
        if state:
            details.append({"state": state})

        return build_error_response(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            code="internal_error",
            message="Outlook token exchange succeeded, but the connection could not be saved.",
            details=details,
        )

    return OutlookOAuthConnectionSavedResponse(
        status="connected",
        message="Outlook connection completed successfully.",
        oauth_connection_id=str(saved_connection["id"]),
        microsoft_user_id=str(saved_connection["microsoft_user_id"]),
        tenant_id=(
            str(saved_connection["tenant_id"])
            if saved_connection.get("tenant_id") is not None
            else None
        ),
        user_principal_name=(
            str(saved_connection["user_principal_name"])
            if saved_connection.get("user_principal_name") is not None
            else None
        ),
        state=state,
        next_step=(
            "The Outlook tokens were saved successfully. The next step is to "
            "make the first authenticated Microsoft Graph read."
        ),
    )


@router.get(
    "/outlook/accounts/{microsoft_user_id}/current-user",
    response_model=OutlookCurrentUserResponse,
)
def get_outlook_current_user_route(
    microsoft_user_id: str,
) -> OutlookCurrentUserResponse | JSONResponse:
    """
    Return the currently connected Microsoft user profile.

    Example
    -------
    A request looks like:

        GET /api/v1/integrations/outlook/accounts/{microsoft_user_id}/current-user
    """

    stored_connection = _prepare_outlook_connection_for_api_read(
        microsoft_user_id=microsoft_user_id
    )
    if isinstance(stored_connection, JSONResponse):
        return stored_connection

    user_result = _perform_outlook_read_with_refresh_retry(
        microsoft_user_id=microsoft_user_id,
        stored_connection=stored_connection,
        read_callable=lambda *, access_token: fetch_outlook_current_user(
            access_token=access_token
        ),
        provider_failure_message="Outlook current-user read failed.",
    )
    if isinstance(user_result, JSONResponse):
        return user_result

    return OutlookCurrentUserResponse(
        microsoft_user_id=microsoft_user_id,
        user=user_result["user"],
    )


@router.get(
    "/outlook/accounts/{microsoft_user_id}/mail-folders",
    response_model=OutlookMailFoldersResponse,
)
def get_outlook_mail_folders_route(
    microsoft_user_id: str,
    mailbox: str | None = Query(
        default=None,
        description=(
            "Optional delegated mailbox identifier such as a user principal "
            "name or mailbox email."
        ),
    ),
    limit: int = Query(
        default=25,
        ge=1,
        le=200,
        description="Maximum number of mail folders to request in the first page.",
    ),
) -> OutlookMailFoldersResponse | JSONResponse:
    """
    Return a first-page preview of Outlook mail folders.

    Example
    -------
    A request looks like:

        GET /api/v1/integrations/outlook/accounts/{microsoft_user_id}/mail-folders?mailbox=recruitment@example.com&limit=25
    """

    stored_connection = _prepare_outlook_connection_for_api_read(
        microsoft_user_id=microsoft_user_id
    )
    if isinstance(stored_connection, JSONResponse):
        return stored_connection

    folder_result = _perform_outlook_read_with_refresh_retry(
        microsoft_user_id=microsoft_user_id,
        stored_connection=stored_connection,
        read_callable=lambda *, access_token: fetch_outlook_mail_folders(
            access_token=access_token,
            mailbox=mailbox,
            limit=limit,
        ),
        provider_failure_message="Outlook mail-folder read failed.",
    )
    if isinstance(folder_result, JSONResponse):
        return folder_result

    return OutlookMailFoldersResponse(
        microsoft_user_id=microsoft_user_id,
        mailbox=mailbox,
        folder_count=folder_result["folder_count"],
        folders=folder_result["folders"],
    )


@router.get(
    "/outlook/accounts/{microsoft_user_id}/mail-folders/{parent_folder_id}/child-folders",
    response_model=OutlookMailFoldersResponse,
)
def get_outlook_child_mail_folders_route(
    microsoft_user_id: str,
    parent_folder_id: str,
    mailbox: str | None = Query(
        default=None,
        description=(
            "Optional delegated mailbox identifier such as a user principal "
            "name or mailbox email."
        ),
    ),
    limit: int = Query(
        default=200,
        ge=1,
        le=200,
        description="Maximum number of child folders to request in the first page.",
    ),
) -> OutlookMailFoldersResponse | JSONResponse:
    """
    Return a first-page preview of child folders under one Outlook parent folder.
    """

    stored_connection = _prepare_outlook_connection_for_api_read(
        microsoft_user_id=microsoft_user_id
    )
    if isinstance(stored_connection, JSONResponse):
        return stored_connection

    folder_result = _perform_outlook_read_with_refresh_retry(
        microsoft_user_id=microsoft_user_id,
        stored_connection=stored_connection,
        read_callable=lambda *, access_token: fetch_outlook_child_mail_folders(
            access_token=access_token,
            parent_folder_id=parent_folder_id,
            mailbox=mailbox,
            limit=limit,
        ),
        provider_failure_message="Outlook child mail-folder read failed.",
    )
    if isinstance(folder_result, JSONResponse):
        return folder_result

    return OutlookMailFoldersResponse(
        microsoft_user_id=microsoft_user_id,
        mailbox=mailbox,
        folder_count=folder_result["folder_count"],
        folders=folder_result["folders"],
    )


@router.get(
    "/outlook/accounts/{microsoft_user_id}/messages",
    response_model=OutlookMessagesResponse,
)
def get_outlook_messages_route(
    microsoft_user_id: str,
    folder_id: str = Query(
        ...,
        description="Mail folder identifier whose messages should be listed."
    ),
    mailbox: str | None = Query(
        default=None,
        description=(
            "Optional delegated mailbox identifier such as a user principal "
            "name or mailbox email."
        ),
    ),
    limit: int = Query(
        default=25,
        ge=1,
        le=200,
        description="Maximum number of messages to request in the first page.",
    ),
    received_from: datetime | None = Query(
        default=None,
        description="Optional lower bound for Outlook receivedDateTime filtering.",
    ),
    received_to: datetime | None = Query(
        default=None,
        description="Optional upper bound for Outlook receivedDateTime filtering.",
    ),
) -> OutlookMessagesResponse | JSONResponse:
    """
    Return a first-page preview of messages in one Outlook mail folder.

    Example
    -------
    A request looks like:

        GET /api/v1/integrations/outlook/accounts/{microsoft_user_id}/messages?folder_id=inbox
    """

    stored_connection = _prepare_outlook_connection_for_api_read(
        microsoft_user_id=microsoft_user_id
    )
    if isinstance(stored_connection, JSONResponse):
        return stored_connection

    message_result = _perform_outlook_read_with_refresh_retry(
        microsoft_user_id=microsoft_user_id,
        stored_connection=stored_connection,
        read_callable=lambda *, access_token: fetch_outlook_messages(
            access_token=access_token,
            folder_id=folder_id,
            mailbox=mailbox,
            limit=limit,
            received_from=received_from,
            received_to=received_to,
        ),
        provider_failure_message="Outlook message-list read failed.",
    )
    if isinstance(message_result, JSONResponse):
        return message_result

    return OutlookMessagesResponse(
        microsoft_user_id=microsoft_user_id,
        mailbox=mailbox,
        folder_id=folder_id,
        message_count=message_result["message_count"],
        messages=message_result["messages"],
    )


@router.get(
    "/outlook/accounts/{microsoft_user_id}/messages/{message_id}/attachments/{attachment_id}/download-proof",
    response_model=OutlookMessageAttachmentDownloadProofResponse,
)
def get_outlook_message_attachment_download_proof_route(
    microsoft_user_id: str,
    message_id: str,
    attachment_id: str,
    mailbox: str | None = Query(
        default=None,
        description=(
            "Optional delegated mailbox identifier such as a user principal "
            "name or mailbox email."
        ),
    ),
) -> OutlookMessageAttachmentDownloadProofResponse | JSONResponse:
    """
    Download one Outlook file attachment transiently and return proof metadata.

    Notes
    -----
    - This route is intentionally narrow.
    - It exists for attachment verification and cross-source comparison work,
      not for public raw file delivery.
    - The immediate practical use is to prove that advert-response mailbox
      attachments can flow into the same extraction pipeline already used for
      JobAdder and Dropbox CV files.

    Example
    -------
    A request looks like:

        GET /api/v1/integrations/outlook/accounts/{microsoft_user_id}/messages/{message_id}/attachments/{attachment_id}/download-proof

    And a successful response looks like:

        {
            "message_id": "AAMkAGI2...",
            "attachment_id": "AAMkAGI2...AAABEgAQ...",
            "file_name": "Candidate CV.pdf",
            "byte_count": 326601,
            "sha256": "..."
        }

    The route deliberately returns proof metadata only. It does not stream the
    raw attachment bytes back to the client.
    """

    stored_connection = _prepare_outlook_connection_for_api_read(
        microsoft_user_id=microsoft_user_id
    )
    if isinstance(stored_connection, JSONResponse):
        return stored_connection

    download_result = _perform_outlook_read_with_refresh_retry(
        microsoft_user_id=microsoft_user_id,
        stored_connection=stored_connection,
        read_callable=lambda *, access_token: download_outlook_message_file_attachment(
            access_token=access_token,
            message_id=message_id,
            attachment_id=attachment_id,
            mailbox=mailbox,
        ),
        provider_failure_message="Outlook attachment download failed.",
    )
    if isinstance(download_result, JSONResponse):
        return download_result

    content_bytes = download_result["content_bytes"]
    sha256_digest = hashlib.sha256(content_bytes).hexdigest()

    return OutlookMessageAttachmentDownloadProofResponse(
        microsoft_user_id=microsoft_user_id,
        mailbox=mailbox,
        message_id=message_id,
        attachment_id=attachment_id,
        file_name=download_result.get("file_name"),
        content_type=download_result.get("content_type"),
        byte_count=len(content_bytes),
        sha256=sha256_digest,
    )


@router.get(
    "/outlook/accounts/{microsoft_user_id}/messages/{message_id}/attachments",
    response_model=OutlookMessageAttachmentsResponse,
)
def get_outlook_message_attachments_route(
    microsoft_user_id: str,
    message_id: str,
    mailbox: str | None = Query(
        default=None,
        description=(
            "Optional delegated mailbox identifier such as a user principal "
            "name or mailbox email."
        ),
    ),
    limit: int = Query(
        default=50,
        ge=1,
        le=200,
        description="Maximum number of attachments to request in the first page.",
    ),
) -> OutlookMessageAttachmentsResponse | JSONResponse:
    """
    Return a first-page preview of attachments on one Outlook message.

    Example
    -------
    A request looks like:

        GET /api/v1/integrations/outlook/accounts/{microsoft_user_id}/messages/{message_id}/attachments
    """

    stored_connection = _prepare_outlook_connection_for_api_read(
        microsoft_user_id=microsoft_user_id
    )
    if isinstance(stored_connection, JSONResponse):
        return stored_connection

    attachment_result = _perform_outlook_read_with_refresh_retry(
        microsoft_user_id=microsoft_user_id,
        stored_connection=stored_connection,
        read_callable=lambda *, access_token: fetch_outlook_message_attachments(
            access_token=access_token,
            message_id=message_id,
            mailbox=mailbox,
            limit=limit,
        ),
        provider_failure_message="Outlook attachment-list read failed.",
    )
    if isinstance(attachment_result, JSONResponse):
        return attachment_result

    return OutlookMessageAttachmentsResponse(
        microsoft_user_id=microsoft_user_id,
        mailbox=mailbox,
        message_id=message_id,
        attachment_count=attachment_result["attachment_count"],
        attachments=attachment_result["attachments"],
    )


@router.get(
    "/recruitly/admin/candidates-preview",
    response_model=RecruitlyEntityPreviewResponse,
    responses={
        401: {"model": ApiErrorResponse, "description": "Admin bearer token is missing or invalid."},
        502: {"model": ApiErrorResponse, "description": "Recruitly preview read failed."},
    },
)
def get_recruitly_candidates_preview_route(
    request: Request,
    query: str | None = Query(default=None),
    page: int = Query(default=0, ge=0),
    size: int = Query(default=20, ge=1, le=100),
) -> RecruitlyEntityPreviewResponse | JSONResponse:
    """
    Return one protected Recruitly candidate preview page.
    """

    auth_failure = _authorize_admin_request(request)
    if auth_failure is not None:
        return auth_failure

    configuration = _load_recruitly_configuration()
    if isinstance(configuration, JSONResponse):
        return configuration
    api_base_url, api_key = configuration

    try:
        preview = fetch_recruitly_candidates_preview(
            api_base_url=api_base_url,
            api_key=api_key,
            query=query,
            page=page,
            size=size,
        )
    except (RecruitlyApiError, ValueError) as exc:
        return build_error_response(
            status_code=status.HTTP_502_BAD_GATEWAY,
            code="integration_connection_invalid",
            message="Recruitly candidate preview failed.",
            details=_build_recruitly_error_details(exc),
        )

    return RecruitlyEntityPreviewResponse(
        resource="candidates",
        api_base_url=api_base_url,
        query=preview["query"],
        page=preview["page"],
        size=preview["size"],
        item_count=preview["item_count"],
        total_count=preview["total_count"],
        data=preview["data"],
    )


@router.get(
    "/recruitly/admin/companies-preview",
    response_model=RecruitlyEntityPreviewResponse,
    responses={
        401: {"model": ApiErrorResponse, "description": "Admin bearer token is missing or invalid."},
        502: {"model": ApiErrorResponse, "description": "Recruitly preview read failed."},
    },
)
def get_recruitly_companies_preview_route(
    request: Request,
    query: str | None = Query(default=None),
    page: int = Query(default=0, ge=0),
    size: int = Query(default=20, ge=1, le=100),
) -> RecruitlyEntityPreviewResponse | JSONResponse:
    """
    Return one protected Recruitly company preview page.
    """

    auth_failure = _authorize_admin_request(request)
    if auth_failure is not None:
        return auth_failure

    configuration = _load_recruitly_configuration()
    if isinstance(configuration, JSONResponse):
        return configuration
    api_base_url, api_key = configuration

    try:
        preview = fetch_recruitly_companies_preview(
            api_base_url=api_base_url,
            api_key=api_key,
            query=query,
            page=page,
            size=size,
        )
    except (RecruitlyApiError, ValueError) as exc:
        return build_error_response(
            status_code=status.HTTP_502_BAD_GATEWAY,
            code="integration_connection_invalid",
            message="Recruitly company preview failed.",
            details=_build_recruitly_error_details(exc),
        )

    return RecruitlyEntityPreviewResponse(
        resource="companies",
        api_base_url=api_base_url,
        query=preview["query"],
        page=preview["page"],
        size=preview["size"],
        item_count=preview["item_count"],
        total_count=preview["total_count"],
        data=preview["data"],
    )


@router.get(
    "/recruitly/admin/contacts-preview",
    response_model=RecruitlyEntityPreviewResponse,
    responses={
        401: {"model": ApiErrorResponse, "description": "Admin bearer token is missing or invalid."},
        502: {"model": ApiErrorResponse, "description": "Recruitly preview read failed."},
    },
)
def get_recruitly_contacts_preview_route(
    request: Request,
    query: str | None = Query(default=None),
    page: int = Query(default=0, ge=0),
    size: int = Query(default=20, ge=1, le=100),
) -> RecruitlyEntityPreviewResponse | JSONResponse:
    """
    Return one protected Recruitly contact preview page.
    """

    auth_failure = _authorize_admin_request(request)
    if auth_failure is not None:
        return auth_failure

    configuration = _load_recruitly_configuration()
    if isinstance(configuration, JSONResponse):
        return configuration
    api_base_url, api_key = configuration

    try:
        preview = fetch_recruitly_contacts_preview(
            api_base_url=api_base_url,
            api_key=api_key,
            query=query,
            page=page,
            size=size,
        )
    except (RecruitlyApiError, ValueError) as exc:
        return build_error_response(
            status_code=status.HTTP_502_BAD_GATEWAY,
            code="integration_connection_invalid",
            message="Recruitly contact preview failed.",
            details=_build_recruitly_error_details(exc),
        )

    return RecruitlyEntityPreviewResponse(
        resource="contacts",
        api_base_url=api_base_url,
        query=preview["query"],
        page=preview["page"],
        size=preview["size"],
        item_count=preview["item_count"],
        total_count=preview["total_count"],
        data=preview["data"],
    )


@router.get(
    "/recruitly/admin/jobs-preview",
    response_model=RecruitlyEntityPreviewResponse,
    responses={
        401: {"model": ApiErrorResponse, "description": "Admin bearer token is missing or invalid."},
        502: {"model": ApiErrorResponse, "description": "Recruitly preview read failed."},
    },
)
def get_recruitly_jobs_preview_route(
    request: Request,
    query: str | None = Query(default=None),
    page: int = Query(default=0, ge=0),
    size: int = Query(default=20, ge=1, le=100),
) -> RecruitlyEntityPreviewResponse | JSONResponse:
    """
    Return one protected Recruitly job preview page.
    """

    auth_failure = _authorize_admin_request(request)
    if auth_failure is not None:
        return auth_failure

    configuration = _load_recruitly_configuration()
    if isinstance(configuration, JSONResponse):
        return configuration
    api_base_url, api_key = configuration

    try:
        preview = fetch_recruitly_jobs_preview(
            api_base_url=api_base_url,
            api_key=api_key,
            query=query,
            page=page,
            size=size,
        )
    except (RecruitlyApiError, ValueError) as exc:
        return build_error_response(
            status_code=status.HTTP_502_BAD_GATEWAY,
            code="integration_connection_invalid",
            message="Recruitly job preview failed.",
            details=_build_recruitly_error_details(exc),
        )

    return RecruitlyEntityPreviewResponse(
        resource="jobs",
        api_base_url=api_base_url,
        query=preview["query"],
        page=preview["page"],
        size=preview["size"],
        item_count=preview["item_count"],
        total_count=preview["total_count"],
        data=preview["data"],
    )


@router.get(
    "/recruitly/admin/{record_type}/{record_id}/journal-preview",
    response_model=RecruitlyJournalPreviewResponse,
    responses={
        401: {"model": ApiErrorResponse, "description": "Admin bearer token is missing or invalid."},
        502: {"model": ApiErrorResponse, "description": "Recruitly preview read failed."},
    },
)
def get_recruitly_journal_preview_route(
    request: Request,
    record_type: str,
    record_id: str,
    page: int = Query(default=0, ge=0),
    size: int = Query(default=20, ge=1, le=100),
) -> RecruitlyJournalPreviewResponse | JSONResponse:
    """
    Return one protected Recruitly journal/activity preview page.
    """

    auth_failure = _authorize_admin_request(request)
    if auth_failure is not None:
        return auth_failure

    configuration = _load_recruitly_configuration()
    if isinstance(configuration, JSONResponse):
        return configuration
    api_base_url, api_key = configuration

    try:
        preview = fetch_recruitly_record_journal_preview(
            api_base_url=api_base_url,
            api_key=api_key,
            record_type=record_type,
            record_id=record_id,
            page=page,
            size=size,
        )
    except (RecruitlyApiError, ValueError) as exc:
        return build_error_response(
            status_code=status.HTTP_502_BAD_GATEWAY,
            code="integration_connection_invalid",
            message="Recruitly journal preview failed.",
            details=_build_recruitly_error_details(exc),
        )

    return RecruitlyJournalPreviewResponse(
        record_type=preview["record_type"],
        record_id=preview["record_id"],
        api_base_url=api_base_url,
        page=preview["page"],
        size=preview["size"],
        item_count=preview["item_count"],
        total_count=preview["total_count"],
        data=preview["data"],
    )


@router.post(
    "/recruitly/admin/companies-ingest",
    response_model=RecruitlyCollectionIngestResponse,
    responses={
        401: {"model": ApiErrorResponse, "description": "Admin bearer token is missing or invalid."},
        502: {"model": ApiErrorResponse, "description": "Recruitly company ingest failed."},
    },
)
def ingest_recruitly_companies_route(
    request: Request,
    payload: RecruitlyCollectionIngestRequest,
) -> RecruitlyCollectionIngestResponse | JSONResponse:
    """
    Persist one bounded Recruitly companies page into canonical storage.
    """

    auth_failure = _authorize_admin_request(request)
    if auth_failure is not None:
        return auth_failure

    configuration = _load_recruitly_configuration()
    if isinstance(configuration, JSONResponse):
        return configuration
    api_base_url, api_key = configuration

    try:
        ingest_report = ingest_recruitly_collection_page(
            resource="companies",
            api_base_url=api_base_url,
            api_key=api_key,
            query=payload.query,
            page=payload.page,
            size=payload.size,
            import_run_id=payload.import_run_id,
        )
    except (RecruitlyApiError, RuntimeError, ValueError) as exc:
        return build_error_response(
            status_code=status.HTTP_502_BAD_GATEWAY,
            code="integration_connection_invalid",
            message="Recruitly company ingest failed.",
            details=_build_recruitly_error_details(exc),
        )

    return RecruitlyCollectionIngestResponse(
        status="completed",
        resource="companies",
        message=(
            "Recruitly company ingest completed. The raw upstream payloads "
            "were preserved and canonical company rows were refreshed."
        ),
        query=ingest_report["query"],
        page=ingest_report["page"],
        size=ingest_report["size"],
        item_count=ingest_report["item_count"],
        total_count=ingest_report["total_count"],
        persisted_count=ingest_report["persisted_count"],
        persisted=ingest_report["persisted"],
    )


@router.post(
    "/recruitly/admin/contacts-ingest",
    response_model=RecruitlyCollectionIngestResponse,
    responses={
        401: {"model": ApiErrorResponse, "description": "Admin bearer token is missing or invalid."},
        502: {"model": ApiErrorResponse, "description": "Recruitly contact ingest failed."},
    },
)
def ingest_recruitly_contacts_route(
    request: Request,
    payload: RecruitlyCollectionIngestRequest,
) -> RecruitlyCollectionIngestResponse | JSONResponse:
    """
    Persist one bounded Recruitly contacts page into canonical storage.
    """

    auth_failure = _authorize_admin_request(request)
    if auth_failure is not None:
        return auth_failure

    configuration = _load_recruitly_configuration()
    if isinstance(configuration, JSONResponse):
        return configuration
    api_base_url, api_key = configuration

    try:
        ingest_report = ingest_recruitly_collection_page(
            resource="contacts",
            api_base_url=api_base_url,
            api_key=api_key,
            query=payload.query,
            page=payload.page,
            size=payload.size,
            import_run_id=payload.import_run_id,
        )
    except (RecruitlyApiError, RuntimeError, ValueError) as exc:
        return build_error_response(
            status_code=status.HTTP_502_BAD_GATEWAY,
            code="integration_connection_invalid",
            message="Recruitly contact ingest failed.",
            details=_build_recruitly_error_details(exc),
        )

    return RecruitlyCollectionIngestResponse(
        status="completed",
        resource="contacts",
        message=(
            "Recruitly contact ingest completed. The raw upstream payloads "
            "were preserved and canonical company/contact rows were refreshed."
        ),
        query=ingest_report["query"],
        page=ingest_report["page"],
        size=ingest_report["size"],
        item_count=ingest_report["item_count"],
        total_count=ingest_report["total_count"],
        persisted_count=ingest_report["persisted_count"],
        persisted=ingest_report["persisted"],
    )


@router.post(
    "/linkedin-helper/admin/ingest-person",
    response_model=LinkedHelperPersonIngestResponse,
    responses={
        401: {"model": ApiErrorResponse, "description": "Admin bearer token is missing or invalid."},
        502: {"model": ApiErrorResponse, "description": "Linked Helper ingest failed."},
    },
)
def ingest_linkedin_helper_person_route(
    request: Request,
    payload: LinkedHelperPersonIngestRequest,
) -> LinkedHelperPersonIngestResponse | JSONResponse:
    """
    Persist one Linked Helper sourced person/contact payload.

    Notes
    -----
    - This route is intentionally protected and operator-facing first.
    - The upstream source may be a webhook adapter or a CSV-to-JSON adapter.
    - The canonical storage contract is the stable part.
    """

    auth_failure = _authorize_admin_request(request)
    if auth_failure is not None:
        return auth_failure

    try:
        persisted = ingest_linkedin_helper_person(payload.model_dump())
    except (RuntimeError, ValueError) as exc:
        return build_error_response(
            status_code=status.HTTP_502_BAD_GATEWAY,
            code="integration_connection_invalid",
            message="Linked Helper person ingest failed.",
            details=[{"error_type": exc.__class__.__name__, "message": str(exc)}],
        )

    return LinkedHelperPersonIngestResponse(
        status="completed",
        message=(
            "Linked Helper person ingest completed. The raw upstream payload "
            "was preserved and the canonical rows were refreshed."
        ),
        persisted=persisted,
    )


@router.post(
    "/outlook/admin/folder-ingest",
    response_model=OutlookFolderIngestRunResponse,
    responses={
        400: {"model": ApiErrorResponse, "description": "Request validation failed."},
        401: {"model": ApiErrorResponse, "description": "Admin bearer token is missing or invalid."},
        502: {"model": ApiErrorResponse, "description": "Outlook or Dropbox integration call failed."},
    },
)
def run_outlook_folder_ingest_route(
    request: Request,
    payload: OutlookFolderIngestRunRequest,
) -> OutlookFolderIngestRunResponse | JSONResponse:
    """
    Run one tightly bounded protected Outlook folder-ingest slice.

    Notes
    -----
    - This route is intended for controlled operator/admin use.
    - It is deliberately capped for small production test batches.
    - It is not the final mailbox-scale backfill worker.
    """

    auth_failure = _authorize_admin_request(request)
    if auth_failure is not None:
        return auth_failure

    try:
        folder_segments = _normalize_outlook_folder_segments(payload.folder_segments)
    except ValueError as exc:
        return build_error_response(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="validation_error",
            message=str(exc),
        )

    try:
        stored_connection = load_ready_outlook_connection(
            microsoft_user_id=payload.microsoft_user_id,
        )
        dropbox_connection = _load_dropbox_connection(payload.dropbox_account_id)
        access_token = stored_connection["access_token"]
        dropbox_access_token = dropbox_connection["access_token"]
        assert isinstance(access_token, str)
        assert isinstance(dropbox_access_token, str)

        resolved_folder = resolve_outlook_folder_path(
            access_token=access_token,
            mailbox=payload.mailbox,
            folder_segments=folder_segments,
        )
        ingest_report = run_outlook_folder_ingest(
            access_token=access_token,
            microsoft_user_id=payload.microsoft_user_id,
            mailbox=payload.mailbox,
            folder_path=folder_segments,
            folder_id=resolved_folder["folder_id"],
            message_limit=payload.message_limit,
            attachment_limit=payload.attachment_limit,
            dropbox_access_token=dropbox_access_token,
            dropbox_export_folder=payload.dropbox_export_folder,
        )
    except (DropboxApiError, OutlookApiError, RuntimeError, ValueError) as exc:
        return build_error_response(
            status_code=status.HTTP_502_BAD_GATEWAY,
            code="integration_connection_invalid",
            message="Protected Outlook folder ingest failed.",
            details=[{"error_type": exc.__class__.__name__, "message": str(exc)}],
        )

    return OutlookFolderIngestRunResponse(
        status="completed",
        message=(
            "Protected Outlook folder ingest completed. Review the bounded "
            "run report before widening the batch."
        ),
        resolved_folder=resolved_folder,
        ingest_report=ingest_report,
    )


@router.post(
    "/outlook/admin/export-cv-attachments",
    response_model=OutlookCvAttachmentExportResponse,
    responses={
        400: {"model": ApiErrorResponse, "description": "Request validation failed."},
        401: {"model": ApiErrorResponse, "description": "Admin bearer token is missing or invalid."},
        502: {"model": ApiErrorResponse, "description": "Outlook or Dropbox integration call failed."},
    },
)
def run_outlook_cv_attachment_export_route(
    request: Request,
    payload: OutlookCvAttachmentExportRequest,
) -> OutlookCvAttachmentExportResponse | JSONResponse:
    """
    Run one tightly bounded non-LLM Outlook attachment scan and Dropbox export.

    Notes
    -----
    - This route scans messages and attachments only.
    - It uses local text extraction and heuristic CV detection.
    - It does not call the LLM or persist candidate data into Supabase.
    """

    auth_failure = _authorize_admin_request(request)
    if auth_failure is not None:
        return auth_failure

    try:
        folder_segments = _normalize_outlook_folder_segments(payload.folder_segments)
    except ValueError as exc:
        return build_error_response(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="validation_error",
            message=str(exc),
        )

    try:
        stored_connection = load_ready_outlook_connection(
            microsoft_user_id=payload.microsoft_user_id,
        )
        access_token = stored_connection["access_token"]
        assert isinstance(access_token, str)
        dropbox_access_token: str | None = None
        if not payload.dry_run:
            dropbox_connection = _load_dropbox_connection(payload.dropbox_account_id)
            raw_dropbox_access_token = dropbox_connection["access_token"]
            assert isinstance(raw_dropbox_access_token, str)
            dropbox_access_token = raw_dropbox_access_token

        resolved_folder = resolve_outlook_folder_path(
            access_token=access_token,
            mailbox=payload.mailbox,
            folder_segments=folder_segments,
        )
        export_report = run_outlook_cv_attachment_export(
            access_token=access_token,
            mailbox=payload.mailbox,
            folder_id=resolved_folder["folder_id"],
            folder_path=folder_segments,
            message_limit=payload.message_limit,
            attachment_limit=payload.attachment_limit,
            dropbox_access_token=dropbox_access_token,
            dropbox_export_folder=payload.dropbox_export_folder,
            received_from=payload.received_from,
            received_to=payload.received_to,
            dry_run=payload.dry_run,
        )
    except (DropboxApiError, OutlookApiError, RuntimeError, ValueError) as exc:
        return build_error_response(
            status_code=status.HTTP_502_BAD_GATEWAY,
            code="integration_connection_invalid",
            message="Protected Outlook CV attachment export failed.",
            details=[{"error_type": exc.__class__.__name__, "message": str(exc)}],
        )

    return OutlookCvAttachmentExportResponse(
        status="completed",
        message=(
            "Protected Outlook CV attachment export completed. Review the "
            "heuristic export report before widening the batch."
        ),
        resolved_folder=resolved_folder,
        export_report=export_report,
    )


__all__ = ["router"]
