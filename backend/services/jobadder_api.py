"""
JobAdder API read helpers for the intelligence backend.

This module contains the small service helpers for making authenticated
read-only requests to the JobAdder API after OAuth has completed successfully.

It gives the rest of the repository a stable way to talk about:

- building the Authorization header for JobAdder API requests
- using the stored JobAdder access token safely
- calling specific read-only JobAdder endpoints
- downloading candidate attachment bytes transiently
- normalising provider-side HTTP and payload errors into one local exception
- keeping external API request logic out of route handlers

Why this module exists
----------------------
We have already proved that the backend can:

- generate the JobAdder authorisation URL
- receive the JobAdder callback
- exchange the one-time code for tokens
- store the returned token set in Supabase/Postgres

The next proof point is different:

    "Can the backend use the stored token to read real data from JobAdder?"

That is what this module answers.

Current scope
-------------
This module still stays intentionally narrow, but it now covers the core
read-side surfaces we need for the first ingestion pipeline:

- fetch a first-page preview of candidates
- fetch a first-page preview of applications
- fetch one application's attachment list
- fetch a first-page preview of job ads
- fetch a first-page preview of job-ad applications
- fetch one full candidate record
- fetch candidate attachments
- fetch candidate skills
- fetch candidate notes
- download one candidate attachment transiently

That is enough to prove:

- the stored token is valid for API use
- the stored `api` base URL returned by JobAdder is usable
- the backend can parse real JobAdder collection and detail responses
- the backend can retrieve related candidate resources such as notes
- the backend can download the selected CV bytes for later text extraction

Notes on endpoint construction
------------------------------
JobAdder's official documentation shows candidate reads under `/v2/candidates`,
including:

- `GET https://api.jobadder.com/v2/candidates/{CANDIDATE_ID}`
- list reads under `https://api.jobadder.com/v2/candidates?...`
- related resources such as:
  - `/candidates/{candidateId}/attachments`
  - `/candidates/{candidateId}/notes`
  - `/candidates/{candidateId}/skills`

The OAuth token response also returns an `api` field, which is the API base URL
associated with the connected JobAdder account.

This module therefore centralises endpoint normalisation so every helper builds
URLs consistently whether the stored API base looks like:

    https://api.jobadder.com

or:

    https://eu2api.jobadder.com/v2/

Example
-------
Typical callers in the rest of the backend do not hand-build URLs directly.
Instead, they call helpers such as:

    fetch_jobadder_candidate_notes(
        api_url="https://eu2api.jobadder.com/v2/",
        access_token="...",
        candidate_id=16496678,
        item_limit=10,
    )

or:

    download_jobadder_candidate_attachment(
        api_url="https://eu2api.jobadder.com/v2/",
        access_token="...",
        candidate_id=16496678,
        attachment_id=21091489,
    )

and receive a small normalised wrapper rather than needing to work with raw
`httpx` request details directly.

Important boundaries
--------------------
This module should not contain:

- FastAPI route handlers
- database read/write logic
- schema classes
- token exchange logic
- refresh-token logic
- ingestion or mapping logic
- business decisions about candidate matching

Those concerns belong in separate modules that depend on this one.
"""

import re
from typing import Any

import httpx

class JobAdderApiError(RuntimeError):
    """
    Raised when the backend cannot complete a JobAdder API read safely.

    Attributes
    ----------
    message : str
        Safe human-readable explanation of what failed.

    status_code : int | None
        HTTP status code returned by JobAdder, if available.

    retry_after : str | None
        Value of the `Retry-After` header when JobAdder throttles the request.

    endpoint_url : str | None
        Fully resolved JobAdder endpoint URL that the backend attempted to call.

    response_body : dict[str, Any] | None
        Safe decoded provider response body when available.

    Notes
    -----
    - This exception is for backend control flow.
    - Route handlers can catch it and turn it into the project's standard API
      error shape.
    - It should never carry token values.

    Example
    -------
    A caller may catch this exception and inspect:

        error.status_code
        error.retry_after
        error.endpoint_url

    to decide whether the failure was:

    - a provider-side 401
    - a throttling response
    - a broken endpoint URL
    """

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        retry_after: str | None = None,
        endpoint_url: str | None = None,
        response_body: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.retry_after = retry_after
        self.endpoint_url = endpoint_url
        self.response_body = response_body

    def __str__(self) -> str:
        """
        Return the human-readable error message.

        In plain language:

        - when the exception is printed
        - show the main message only
        """

        return self.message


def build_jobadder_api_headers(*, access_token: str) -> dict[str, str]:
    """
    Build the standard HTTP headers for a JobAdder API request.

    Parameters
    ----------
    access_token : str
        Stored JobAdder bearer token.

    Returns
    -------
    dict[str, str]
        Header dictionary for an authenticated JobAdder API request.

    Raises
    ------
    ValueError
        If the access token is blank.

    Notes
    -----
    - This helper keeps bearer-token formatting out of route handlers.
    - The JobAdder API expects the token in the standard
      `Authorization: Bearer ...` header.

    Example
    -------
    Calling:

        build_jobadder_api_headers(access_token="abc123")

    returns:

        {
            "Authorization": "Bearer abc123",
            "Accept": "application/json",
        }

    In plain language:

    - take the saved access token
    - turn it into the headers JobAdder expects
    """

    cleaned_access_token = access_token.strip()

    if cleaned_access_token == "":
        raise ValueError("JobAdder access token cannot be empty.")

    return {
        "Authorization": f"Bearer {cleaned_access_token}",
        "Accept": "application/json",
    }


def fetch_jobadder_candidate_detail(
    *,
    api_url: str,
    access_token: str,
    candidate_id: int,
    timeout_seconds: float = 30.0,
) -> dict[str, Any]:
    """
    Fetch one full candidate record from the JobAdder API.

    Parameters
    ----------
    api_url : str
        API base URL returned by JobAdder in the OAuth token response.

        Example shapes:

            https://api.jobadder.com
            https://eu2api.jobadder.com/v2

    access_token : str
        Stored bearer token used for authenticated JobAdder API requests.

    candidate_id : int
        JobAdder candidate identifier to fetch.

    timeout_seconds : float
        HTTP timeout used for the provider request.

    Returns
    -------
    dict[str, Any]
        Normalised dictionary containing:

        - `candidate`
        - `endpoint_url`
        - `raw_payload`

    Raises
    ------
    ValueError
        If the API URL, access token, or candidate ID is invalid.

    JobAdderApiError
        If JobAdder rejects the request, returns an unusable response, or
        cannot be reached safely.

    Notes
    -----
    - This is the next step after the first list preview read.
    - It gives the backend access to the full documented candidate shape, which
      is more useful for canonical-schema mapping than the thinner list record.
    - The helper still remains read-only. It does not write to the database,
      and it does not attempt any ingestion or mapping.

    In plain language:

    - build the candidate-detail URL
    - call JobAdder with the stored token
    - confirm the response body is one candidate object
    - return that object in a small predictable wrapper
    """
    # Candidate IDs are source-system identifiers, so treat non-positive values
    # as invalid caller input rather than trying to "make them work" later.
    #
    # Doing this up front keeps the lower-level URL builder and HTTP layer
    # focused on real provider work instead of spending effort on obviously bad
    # local inputs.
    if candidate_id < 1:
        raise ValueError("JobAdder candidate_id must be at least 1.")

    # Build the endpoint through the shared URL normaliser.
    #
    # That matters because the stored JobAdder API base may already include
    # `/v2`, and we do not want each public helper re-implementing slightly
    # different URL-concatenation logic.
    endpoint_url = _build_jobadder_api_endpoint(
        api_url=api_url,
        resource_path=f"/candidates/{candidate_id}",
    )
    headers = build_jobadder_api_headers(access_token=access_token)

    # Use the shared request helper so that:
    # - transport failures
    # - HTTP status failures
    # - JSON decoding failures
    #
    # all come back through one consistent local exception type.
    response_payload = _request_jobadder_json(
        endpoint_url=endpoint_url,
        headers=headers,
        timeout_seconds=timeout_seconds,
        provider_failure_message="JobAdder candidate read failed.",
    )

    # A candidate-detail read should yield one object, not a list wrapper. If
    # the payload is not a dictionary, the route would have no safe way to
    # reason about the returned record structure.
    if not isinstance(response_payload, dict):
        raise JobAdderApiError(
            "JobAdder candidate read response did not include a candidate object.",
            endpoint_url=endpoint_url,
            response_body={"decoded_json": response_payload},
        )

    return {
        "candidate": response_payload,
        "endpoint_url": endpoint_url,
        "raw_payload": response_payload,
    }


def fetch_jobadder_candidate_attachments(
    *,
    api_url: str,
    access_token: str,
    candidate_id: int,
    timeout_seconds: float = 30.0,
) -> dict[str, Any]:
    """
    Fetch the attachment list for one JobAdder candidate.

    Parameters
    ----------
    api_url : str
        API base URL returned by JobAdder in the OAuth token response.

        Example shapes:

            https://api.jobadder.com
            https://eu2api.jobadder.com/v2

    access_token : str
        Stored bearer token used for authenticated JobAdder API requests.

    candidate_id : int
        JobAdder candidate identifier whose attachments should be fetched.

    timeout_seconds : float
        HTTP timeout used for the provider request.

    Returns
    -------
    dict[str, Any]
        Normalised dictionary containing:

        - `items`
        - `attachment_count`
        - `links`
        - `endpoint_url`
        - `raw_payload`

    Raises
    ------
    ValueError
        If the API URL, access token, or candidate ID is invalid.

    JobAdderApiError
        If JobAdder rejects the request, returns an unusable response, or
        cannot be reached safely.

    Notes
    -----
    - This helper is the attachment-list companion to the candidate-detail
      helper.
    - It is still intentionally read-only. It does not download attachment
      bytes and it does not decide which attachment is a CV or resume.
    - The orchestration layer above this helper can later apply business rules
      such as:
        - selecting the latest resume
        - preferring PDFs
        - routing the file to Dropbox or another document source

    In plain language:

    - build the candidate-attachments URL
    - call JobAdder with the stored token
    - confirm the response contains an attachment list
    - return that list in a small predictable wrapper
    """
    # Attachment reads depend on a real candidate ID in exactly the same way as
    # candidate-detail reads do, so fail fast on invalid caller input before
    # any provider interaction starts.
    if candidate_id < 1:
        raise ValueError("JobAdder candidate_id must be at least 1.")

    # Keep attachment endpoint construction on the same shared URL-normalisation
    # path as every other JobAdder helper.
    #
    # That consistency is more important than it might look, because provider
    # integrations tend to grow by accretion. Centralised URL rules reduce the
    # chance of quietly reintroducing old path bugs.
    endpoint_url = _build_jobadder_api_endpoint(
        api_url=api_url,
        resource_path=f"/candidates/{candidate_id}/attachments",
    )
    headers = build_jobadder_api_headers(access_token=access_token)

    # Reuse the shared transport helper so the attachments read behaves like
    # the other resource reads in:
    # - error handling
    # - timeout behaviour
    # - JSON expectations
    response_payload = _request_jobadder_json(
        endpoint_url=endpoint_url,
        headers=headers,
        timeout_seconds=timeout_seconds,
        provider_failure_message="JobAdder candidate attachments read failed.",
    )

    raw_items = response_payload.get("items")

    # The attachments endpoint is documented as a collection response. If
    # `items` is missing or not a list, the backend should fail clearly rather
    # than guessing whether the provider returned a different payload shape.
    if not isinstance(raw_items, list):
        raise JobAdderApiError(
            "JobAdder candidate attachments response did not include an items list.",
            status_code=200,
            endpoint_url=endpoint_url,
            response_body=response_payload,
        )

    raw_links = response_payload.get("links")
    links = raw_links if isinstance(raw_links, dict) else {}

    return {
        "items": raw_items,
        "attachment_count": len(raw_items),
        "links": links,
        "endpoint_url": endpoint_url,
        "raw_payload": response_payload,
    }


def fetch_jobadder_application_attachments(
    *,
    api_url: str,
    access_token: str,
    application_id: int,
    timeout_seconds: float = 30.0,
) -> dict[str, Any]:
    """
    Fetch the attachment list for one JobAdder application.

    Parameters
    ----------
    api_url : str
        API base URL returned by JobAdder in the OAuth token response.

    access_token : str
        Stored bearer token used for authenticated JobAdder API requests.

    application_id : int
        JobAdder application identifier whose attachments should be fetched.

    timeout_seconds : float
        HTTP timeout used for the provider request.

    Returns
    -------
    dict[str, Any]
        Normalised dictionary containing:

        - `items`
        - `attachment_count`
        - `links`
        - `endpoint_url`
        - `raw_payload`

    Raises
    ------
    ValueError
        If the API URL, access token, or application ID is invalid.

    JobAdderApiError
        If JobAdder rejects the request, returns an unusable response, or
        cannot be reached safely.

    Notes
    -----
    - This is the application-level counterpart to candidate attachments.
    - It is still read-only. It does not download attachment bytes.
    - The immediate use is payload inspection and source reconciliation.

    Example
    -------
    Calling:

        fetch_jobadder_application_attachments(
            api_url="https://eu2api.jobadder.com/v2/",
            access_token="...",
            application_id=12204918,
        )

    returns a small wrapper around the application's attachment list.
    """
    if application_id < 1:
        raise ValueError("JobAdder application_id must be at least 1.")

    endpoint_url = _build_jobadder_api_endpoint(
        api_url=api_url,
        resource_path=f"/applications/{application_id}/attachments",
    )
    headers = build_jobadder_api_headers(access_token=access_token)

    response_payload = _request_jobadder_json(
        endpoint_url=endpoint_url,
        headers=headers,
        timeout_seconds=timeout_seconds,
        provider_failure_message="JobAdder application attachments read failed.",
    )

    raw_items = response_payload.get("items")

    if not isinstance(raw_items, list):
        raise JobAdderApiError(
            "JobAdder application attachments response did not include an items list.",
            status_code=200,
            endpoint_url=endpoint_url,
            response_body=response_payload,
        )

    raw_links = response_payload.get("links")
    links = raw_links if isinstance(raw_links, dict) else {}

    return {
        "items": raw_items,
        "attachment_count": len(raw_items),
        "links": links,
        "endpoint_url": endpoint_url,
        "raw_payload": response_payload,
    }


def fetch_jobadder_application_detail(
    *,
    api_url: str,
    access_token: str,
    application_id: int,
    timeout_seconds: float = 30.0,
) -> dict[str, Any]:
    """
    Fetch one full JobAdder application record.

    Parameters
    ----------
    api_url : str
        API base URL returned by JobAdder in the OAuth token response.

    access_token : str
        Stored bearer token used for authenticated JobAdder API requests.

    application_id : int
        JobAdder application identifier to fetch.

    timeout_seconds : float
        HTTP timeout used for the provider request.

    Returns
    -------
    dict[str, Any]
        Normalized dictionary containing:

        - `application`
        - `endpoint_url`
        - `raw_payload`

    Raises
    ------
    ValueError
        If the API URL, access token, or application ID is invalid.

    JobAdderApiError
        If JobAdder rejects the request, returns an unusable response, or
        cannot be reached safely.

    Notes
    -----
    This is the detail-level companion to the top-level applications preview.

    The preview route is useful for discovery, but the persistence path needs a
    stable one-record payload for a known upstream application ID. That is why
    this helper exists instead of forcing persistence code to scrape the first
    page of the preview collection and hope the target application is still
    there.

    Example
    -------
    Calling:

        fetch_jobadder_application_detail(
            api_url="https://eu2api.jobadder.com/v2/",
            access_token="...",
            application_id=12204918,
        )

    returns one wrapper around the decoded application object.
    """
    if application_id < 1:
        raise ValueError("JobAdder application_id must be at least 1.")

    endpoint_url = _build_jobadder_api_endpoint(
        api_url=api_url,
        resource_path=f"/applications/{application_id}",
    )
    headers = build_jobadder_api_headers(access_token=access_token)

    # Treat application detail the same way as candidate/job detail:
    # - build one deterministic endpoint
    # - perform one authenticated read
    # - require one decoded object back
    #
    # Keeping these detail helpers structurally similar makes the routes and
    # persistence services much easier to reason about later.
    response_payload = _request_jobadder_json(
        endpoint_url=endpoint_url,
        headers=headers,
        timeout_seconds=timeout_seconds,
        provider_failure_message="JobAdder application read failed.",
    )

    if not isinstance(response_payload, dict):
        raise JobAdderApiError(
            "JobAdder application read response did not include an application object.",
            endpoint_url=endpoint_url,
            response_body={"decoded_json": response_payload},
        )

    return {
        "application": response_payload,
        "endpoint_url": endpoint_url,
        "raw_payload": response_payload,
    }


def download_jobadder_candidate_attachment(
    *,
    api_url: str,
    access_token: str,
    candidate_id: int,
    attachment_id: int,
    timeout_seconds: float = 30.0,
) -> dict[str, Any]:
    """
    Download one candidate attachment from the JobAdder API.

    Parameters
    ----------
    api_url : str
        API base URL returned by JobAdder in the OAuth token response.

        Example shapes:

            https://api.jobadder.com
            https://eu2api.jobadder.com/v2

    access_token : str
        Stored bearer token used for authenticated JobAdder API requests.

    candidate_id : int
        JobAdder candidate identifier that owns the attachment.

    attachment_id : int
        JobAdder attachment identifier to download.

    timeout_seconds : float
        HTTP timeout used for the provider request.

    Returns
    -------
    dict[str, Any]
        Normalised dictionary containing:

        - `content_bytes`
        - `content_type`
        - `content_length`
        - `file_name`
        - `endpoint_url`

    Raises
    ------
    ValueError
        If the API URL, access token, candidate ID, or attachment ID is
        invalid.

    JobAdderApiError
        If JobAdder rejects the request or the attachment cannot be reached
        safely.

    Notes
    -----
    - This helper is deliberately narrower than a future full document-storage
      pipeline.
    - It only performs the transient provider download step.
    - It does not write the file anywhere.
    - It does not parse PDF text.
    - It does not decide whether the attachment should be retained long term.

    Example
    -------
    A typical call looks like:

        download_jobadder_candidate_attachment(
            api_url="https://eu2api.jobadder.com/v2/",
            access_token="...",
            candidate_id=16496678,
            attachment_id=21091489,
        )

    and returns a dictionary of the form:

        {
            "content_bytes": b"...",
            "content_type": "application/pdf",
            "content_length": 123456,
            "file_name": "Roger Campbell - CV 2025.pdf",
            "endpoint_url": "https://eu2api.jobadder.com/v2/candidates/16496678/attachments/21091489",
        }

    In plain language:

    - build the candidate-attachment download URL
    - call JobAdder with the stored token
    - return the file bytes plus the useful response metadata
    """

    # Both the parent candidate ID and the attachment ID are source-system
    # identifiers. Treat invalid values as caller-input problems immediately
    # rather than deferring them into confusing provider errors later.
    if candidate_id < 1:
        raise ValueError("JobAdder candidate_id must be at least 1.")

    if attachment_id < 1:
        raise ValueError("JobAdder attachment_id must be at least 1.")

    # Keep the download endpoint on the same shared URL-normalisation path as
    # the JSON resource helpers.
    #
    # That gives us one consistent rule for handling:
    # - API bases that already include `/v2`
    # - trailing slashes
    # - resource paths with or without leading slashes
    endpoint_url = _build_jobadder_api_endpoint(
        api_url=api_url,
        resource_path=f"/candidates/{candidate_id}/attachments/{attachment_id}",
    )
    headers = build_jobadder_api_headers(access_token=access_token)

    # Use a separate shared transport helper for binary content so the public
    # attachment-download helper can stay focused on:
    # - identifying the correct endpoint
    # - validating the source identifiers
    # - returning one small normalised wrapper
    response = _request_jobadder_binary(
        endpoint_url=endpoint_url,
        headers=headers,
        timeout_seconds=timeout_seconds,
        provider_failure_message="JobAdder candidate attachment download failed.",
    )

    content_type = _safe_string(response.headers.get("Content-Type"))
    content_length = _safe_int(response.headers.get("Content-Length"))
    file_name = _extract_file_name_from_content_disposition(
        response.headers.get("Content-Disposition")
    )

    return {
        "content_bytes": response.content,
        "content_type": content_type,
        "content_length": content_length,
        "file_name": file_name,
        "endpoint_url": endpoint_url,
    }


def fetch_jobadder_candidates_preview(
    *,
    api_url: str,
    access_token: str,
    item_limit: int = 10,
    timeout_seconds: float = 30.0,
) -> dict[str, Any]:
    """
    Fetch a first-page preview of candidates from the JobAdder API.

    Parameters
    ----------
    api_url : str
        API base URL returned by JobAdder in the OAuth token response.

        Example shapes:

            https://api.jobadder.com
            https://eu2api.jobadder.com/v2

    access_token : str
        Stored bearer token used for authenticated JobAdder API requests.

    item_limit : int
        Maximum number of candidate items to return from the first page of the
        JobAdder response.

        The backend fetches the provider's first page and then slices the local
        result down to this count.

    timeout_seconds : float
        HTTP timeout used for the provider request.

    Returns
    -------
    dict[str, Any]
        Small normalised dictionary containing:

        - `items`
        - `item_count`
        - `total_count`
        - `links`
        - `endpoint_url`
        - `raw_payload`

    Raises
    ------
    ValueError
        If the API URL, access token, or item limit is invalid.

    JobAdderApiError
        If JobAdder rejects the request, returns an unusable response, or
        cannot be reached safely.

    Notes
    -----
    - This helper is intentionally read-only.
    - It does not write to the database.
    - It does not refresh tokens yet.
    - It only proves that the stored token can call one real JobAdder endpoint.

    Endpoint choice
    ---------------
    This helper calls:

        {API_URL}/v2/candidates

    However, some stored JobAdder `api` values already include the `/v2`
    version segment. In that case, appending another `/v2` would produce an
    invalid URL such as:

        https://eu2api.jobadder.com/v2/v2/candidates

    So this helper normalises the final URL and only adds the version segment
    when it is not already present.

    That is a conservative first target because JobAdder's documentation shows
    candidate GETs under `/v2/candidates`, including list reads.

    In plain language:

    - build the candidate-list URL
    - call JobAdder with the stored token
    - confirm the response has a candidate `items` list
    - return a trimmed preview of that first page
    """
    # The preview contract is explicitly "one or more items", so reject `0` or
    # negative values before doing any provider work.
    #
    # That keeps the public behaviour easy to explain:
    # the caller is asking for a preview size, not for a raw pagination probe.
    if item_limit < 1:
        raise ValueError("JobAdder candidate preview item_limit must be at least 1.")

    # Normalise the final endpoint once in the shared URL builder.
    #
    # This is the same fix that prevents `/v2/v2/candidates` regressions, and
    # it belongs in the shared path-building layer rather than inline string
    # concatenation in each helper.
    endpoint_url = _build_jobadder_api_endpoint(
        api_url=api_url,
        resource_path="/candidates",
    )
    headers = build_jobadder_api_headers(access_token=access_token)

    # Delegate the transport and JSON decoding behaviour to the shared request
    # helper so the preview logic can stay focused on list-shape validation and
    # trimming.
    response_payload = _request_jobadder_json(
        endpoint_url=endpoint_url,
        headers=headers,
        timeout_seconds=timeout_seconds,
        provider_failure_message="JobAdder candidate read failed.",
    )

    raw_items = response_payload.get("items")

    # A successful list response is only useful if it actually contains an
    # `items` array. Fail fast if JobAdder returns something unexpected
    if not isinstance(raw_items, list):
        raise JobAdderApiError(
            "JobAdder candidate read response did not include an items list.",
            status_code=200,
            endpoint_url=endpoint_url,
            response_body=response_payload,
        )

    raw_links = response_payload.get("links")
    links = raw_links if isinstance(raw_links, dict) else {}

    raw_total_count = response_payload.get("totalCount")
    total_count: int | None = None

    if raw_total_count is not None:
        try:
            total_count = int(raw_total_count)
        except (TypeError, ValueError):
            total_count = None

    # Keep the first step intentionally small
    #
    # The reasoning is worth making explicit:
    # - we are not yet trying to implement a general pagination client
    # - we only need a small inspection-friendly preview
    # - trimming locally keeps the public route contract predictable even if the
    #   provider's default page size is much larger
    items = raw_items[:item_limit]

    return {
        "items": items,
        "item_count": len(items),
        "total_count": total_count,
        "links": links,
        "endpoint_url": endpoint_url,
        "raw_payload": response_payload,
    }


def fetch_jobadder_jobads_preview(
    *,
    api_url: str,
    access_token: str,
    item_limit: int = 10,
    timeout_seconds: float = 30.0,
) -> dict[str, Any]:
    """
    Fetch a first-page preview of job ads from the JobAdder API.

    Parameters
    ----------
    api_url : str
        API base URL returned by JobAdder in the OAuth token response.

    access_token : str
        Stored bearer token used for authenticated JobAdder API requests.

    item_limit : int
        Maximum number of job-ad items to return from the first page of the
        JobAdder response.

    timeout_seconds : float
        HTTP timeout used for the provider request.

    Returns
    -------
    dict[str, Any]
        Small normalised dictionary containing:

        - `items`
        - `item_count`
        - `total_count`
        - `links`
        - `endpoint_url`
        - `raw_payload`

    Raises
    ------
    ValueError
        If the API URL, access token, or item limit is invalid.

    JobAdderApiError
        If JobAdder rejects the request, returns an unusable response, or
        cannot be reached safely.

    Notes
    -----
    - This is the job-ad analogue of the candidate-preview helper.
    - The immediate goal is payload inspection rather than long-term contract
      design, so nested job-ad items remain flexible dictionaries.

    Example
    -------
    Calling:

        fetch_jobadder_jobads_preview(
            api_url="https://eu2api.jobadder.com/v2/",
            access_token="...",
            item_limit=5,
        )

    returns a small wrapper around JobAdder's first job-ad page.
    """
    if item_limit < 1:
        raise ValueError("JobAdder job-ad preview item_limit must be at least 1.")

    endpoint_url = _build_jobadder_api_endpoint(
        api_url=api_url,
        resource_path="/jobads",
    )
    headers = build_jobadder_api_headers(access_token=access_token)

    response_payload = _request_jobadder_json(
        endpoint_url=endpoint_url,
        headers=headers,
        timeout_seconds=timeout_seconds,
        provider_failure_message="JobAdder job-ad read failed.",
    )

    raw_items = response_payload.get("items")

    if not isinstance(raw_items, list):
        raise JobAdderApiError(
            "JobAdder job-ad read response did not include an items list.",
            status_code=200,
            endpoint_url=endpoint_url,
            response_body=response_payload,
        )

    raw_links = response_payload.get("links")
    links = raw_links if isinstance(raw_links, dict) else {}

    raw_total_count = response_payload.get("totalCount")
    total_count: int | None = None

    if raw_total_count is not None:
        try:
            total_count = int(raw_total_count)
        except (TypeError, ValueError):
            total_count = None

    items = raw_items[:item_limit]

    return {
        "items": items,
        "item_count": len(items),
        "total_count": total_count,
        "links": links,
        "endpoint_url": endpoint_url,
        "raw_payload": response_payload,
    }


def fetch_jobadder_job_detail(
    *,
    api_url: str,
    access_token: str,
    job_id: int,
    timeout_seconds: float = 30.0,
) -> dict[str, Any]:
    """
    Fetch one full JobAdder job/opportunity record.

    Parameters
    ----------
    api_url : str
        API base URL returned by JobAdder in the OAuth token response.

        Example shapes:

            https://api.jobadder.com
            https://eu2api.jobadder.com/v2

    access_token : str
        Stored bearer token used for authenticated JobAdder API requests.

    job_id : int
        JobAdder job identifier to fetch.

    timeout_seconds : float
        HTTP timeout used for the provider request.

    Returns
    -------
    dict[str, Any]
        Normalised dictionary containing:

        - `job`
        - `endpoint_url`
        - `raw_payload`

    Raises
    ------
    ValueError
        If the API URL, access token, or job ID is invalid.

    JobAdderApiError
        If JobAdder rejects the request, returns an unusable response, or
        cannot be reached safely.

    Notes
    -----
    - This is the structured opportunity-side counterpart to the application
      and candidate helpers.
    - It exists so we can compare the JobAdder opportunity record directly
      against Dropbox job-spec folders and PDFs for the same `tw...` code.

    Example
    -------
    Calling:

        fetch_jobadder_job_detail(
            api_url="https://eu2api.jobadder.com/v2/",
            access_token="...",
            job_id=936462,
        )

    returns a wrapper around one JobAdder `/jobs/{jobId}` response.
    """
    if job_id < 1:
        raise ValueError("JobAdder job_id must be at least 1.")

    endpoint_url = _build_jobadder_api_endpoint(
        api_url=api_url,
        resource_path=f"/jobs/{job_id}",
    )
    headers = build_jobadder_api_headers(access_token=access_token)

    response_payload = _request_jobadder_json(
        endpoint_url=endpoint_url,
        headers=headers,
        timeout_seconds=timeout_seconds,
        provider_failure_message="JobAdder job read failed.",
    )

    if not isinstance(response_payload, dict):
        raise JobAdderApiError(
            "JobAdder job read response did not decode into an object.",
            status_code=200,
            endpoint_url=endpoint_url,
            response_body=response_payload,
        )

    return {
        "job": response_payload,
        "endpoint_url": endpoint_url,
        "raw_payload": response_payload,
    }


def fetch_jobadder_applications_preview(
    *,
    api_url: str,
    access_token: str,
    item_limit: int = 10,
    active_only: bool = False,
    rejected_only: bool = False,
    timeout_seconds: float = 30.0,
) -> dict[str, Any]:
    """
    Fetch a first-page preview of job applications from the JobAdder API.

    Parameters
    ----------
    api_url : str
        API base URL returned by JobAdder in the OAuth token response.

    access_token : str
        Stored bearer token used for authenticated JobAdder API requests.

    item_limit : int
        Maximum number of application items to return from the first page of
        the JobAdder response.

    active_only : bool
        Whether to request only active applications.

    rejected_only : bool
        Whether to request only rejected applications.

    timeout_seconds : float
        HTTP timeout used for the provider request.

    Returns
    -------
    dict[str, Any]
        Small normalised dictionary containing:

        - `items`
        - `item_count`
        - `total_count`
        - `links`
        - `endpoint_url`
        - `raw_payload`

    Raises
    ------
    ValueError
        If the API URL, access token, or item limit is invalid, or if mutually
        exclusive filters are requested together.

    JobAdderApiError
        If JobAdder rejects the request, returns an unusable response, or
        cannot be reached safely.

    Example
    -------
    Calling:

        fetch_jobadder_applications_preview(
            api_url="https://eu2api.jobadder.com/v2/",
            access_token="...",
            item_limit=5,
            active_only=True,
        )

    returns a small wrapper around JobAdder's first applications page.
    """
    if item_limit < 1:
        raise ValueError(
            "JobAdder applications preview item_limit must be at least 1."
        )

    if active_only and rejected_only:
        raise ValueError(
            "JobAdder applications preview cannot request both active_only and rejected_only."
        )

    endpoint_url = _build_jobadder_api_endpoint(
        api_url=api_url,
        resource_path="/applications",
    )
    headers = build_jobadder_api_headers(access_token=access_token)

    params: dict[str, Any] | None = None
    # The applications collection is filter-driven rather than path-driven, so
    # keep these booleans in query params instead of inventing separate local
    # endpoints for each list shape.
    if active_only:
        params = {"active": True}
    elif rejected_only:
        params = {"rejected": True}

    response_payload = _request_jobadder_json(
        endpoint_url=endpoint_url,
        headers=headers,
        timeout_seconds=timeout_seconds,
        provider_failure_message="JobAdder applications read failed.",
        params=params,
    )

    raw_items = response_payload.get("items")

    if not isinstance(raw_items, list):
        raise JobAdderApiError(
            "JobAdder applications read response did not include an items list.",
            status_code=200,
            endpoint_url=endpoint_url,
            response_body=response_payload,
        )

    raw_links = response_payload.get("links")
    links = raw_links if isinstance(raw_links, dict) else {}

    raw_total_count = response_payload.get("totalCount")
    total_count: int | None = None

    if raw_total_count is not None:
        try:
            total_count = int(raw_total_count)
        except (TypeError, ValueError):
            total_count = None

    items = raw_items[:item_limit]

    return {
        "items": items,
        "item_count": len(items),
        "total_count": total_count,
        "links": links,
        "endpoint_url": endpoint_url,
        "raw_payload": response_payload,
    }


def fetch_jobadder_jobad_applications_preview(
    *,
    api_url: str,
    access_token: str,
    ad_id: int,
    item_limit: int = 10,
    active_only: bool = False,
    timeout_seconds: float = 30.0,
) -> dict[str, Any]:
    """
    Fetch a first-page preview of applications for one JobAdder job ad.

    Parameters
    ----------
    api_url : str
        API base URL returned by JobAdder in the OAuth token response.

    access_token : str
        Stored bearer token used for authenticated JobAdder API requests.

    ad_id : int
        JobAdder job-ad identifier whose applications should be fetched.

    item_limit : int
        Maximum number of application items to return from the first page of
        the JobAdder response.

    active_only : bool
        Whether to read only active applications using
        `/jobads/{adId}/applications/active`.

    timeout_seconds : float
        HTTP timeout used for the provider request.

    Returns
    -------
    dict[str, Any]
        Small normalised dictionary containing:

        - `items`
        - `item_count`
        - `total_count`
        - `links`
        - `endpoint_url`
        - `raw_payload`

    Raises
    ------
    ValueError
        If the API URL, access token, ad ID, or item limit is invalid.

    JobAdderApiError
        If JobAdder rejects the request, returns an unusable response, or
        cannot be reached safely.

    Notes
    -----
    - This is the first vacancy/application-aware JobAdder helper.
    - It is intentionally bounded to a small preview because the current goal
      is payload inspection, not bulk ingestion.

    Example
    -------
    Calling:

        fetch_jobadder_jobad_applications_preview(
            api_url="https://eu2api.jobadder.com/v2/",
            access_token="...",
            ad_id=12345,
            item_limit=5,
            active_only=True,
        )

    returns a small wrapper around JobAdder's application list for that ad.
    """
    if ad_id < 1:
        raise ValueError("JobAdder ad_id must be at least 1.")

    if item_limit < 1:
        raise ValueError(
            "JobAdder job-ad applications preview item_limit must be at least 1."
        )

    applications_resource_path = (
        f"/jobads/{ad_id}/applications/active"
        if active_only
        else f"/jobads/{ad_id}/applications"
    )

    endpoint_url = _build_jobadder_api_endpoint(
        api_url=api_url,
        resource_path=applications_resource_path,
    )
    headers = build_jobadder_api_headers(access_token=access_token)

    response_payload = _request_jobadder_json(
        endpoint_url=endpoint_url,
        headers=headers,
        timeout_seconds=timeout_seconds,
        provider_failure_message="JobAdder job-ad applications read failed.",
    )

    raw_items = response_payload.get("items")

    if not isinstance(raw_items, list):
        raise JobAdderApiError(
            "JobAdder job-ad applications response did not include an items list.",
            status_code=200,
            endpoint_url=endpoint_url,
            response_body=response_payload,
        )

    raw_links = response_payload.get("links")
    links = raw_links if isinstance(raw_links, dict) else {}

    raw_total_count = response_payload.get("totalCount")
    total_count: int | None = None

    if raw_total_count is not None:
        try:
            total_count = int(raw_total_count)
        except (TypeError, ValueError):
            total_count = None

    items = raw_items[:item_limit]

    return {
        "items": items,
        "item_count": len(items),
        "total_count": total_count,
        "links": links,
        "endpoint_url": endpoint_url,
        "raw_payload": response_payload,
    }


def fetch_jobadder_candidates_page(
    *,
    api_url: str,
    access_token: str,
    page: int = 1,
    page_size: int = 100,
    page_url: str | None = None,
    timeout_seconds: float = 30.0,
) -> dict[str, Any]:
    """
    Fetch one page of candidates from the JobAdder API.

    Parameters
    ----------
    api_url : str
        API base URL returned by JobAdder in the OAuth token response.

        Example shapes:

            https://api.jobadder.com
            https://eu2api.jobadder.com/v2

    access_token : str
        Stored bearer token used for authenticated JobAdder API requests.

    page : int
        1-based page number for the first request when `page_url` is not
        supplied.

    page_size : int
        Requested provider page size for the first request when `page_url` is
        not supplied.

    page_url : str | None
        Optional fully-qualified next-page URL returned by JobAdder.

        When supplied, this URL takes precedence over `api_url`, `page`, and
        `page_size`.

    timeout_seconds : float
        HTTP timeout used for the provider request.

    Returns
    -------
    dict[str, Any]
        Normalised dictionary containing:

        - `items`
        - `item_count`
        - `total_count`
        - `links`
        - `endpoint_url`
        - `raw_payload`
        - `page`
        - `page_size`

    Raises
    ------
    ValueError
        If the API URL, access token, page, or page size is invalid.

    JobAdderApiError
        If JobAdder rejects the request, returns an unusable response, or
        cannot be reached safely.

    Notes
    -----
    - This helper is the paginated companion to
      `fetch_jobadder_candidates_preview(...)`.
    - The first page can be requested by number and size.
    - Subsequent pages should usually follow the provider-supplied
      `links["next"]` URL rather than reconstructing page URLs manually.

    Example
    -------
    A caller can request the first page explicitly:

        fetch_jobadder_candidates_page(
            api_url="https://eu2api.jobadder.com/v2/",
            access_token="...",
            page=1,
            page_size=100,
        )

    Or it can follow the provider's next link directly:

        fetch_jobadder_candidates_page(
            api_url="https://eu2api.jobadder.com/v2/",
            access_token="...",
            page_url="https://eu2api.jobadder.com/v2/candidates?page=2",
        )

    In plain language:

    - request one concrete page of candidates
    - trust JobAdder's `next` link when continuing pagination
    - return one stable list-page wrapper
    """
    if page < 1:
        raise ValueError("JobAdder candidate page must be at least 1.")

    if page_size < 1:
        raise ValueError("JobAdder candidate page_size must be at least 1.")

    endpoint_url, params = _build_jobadder_candidate_page_request(
        api_url=api_url,
        page=page,
        page_size=page_size,
        page_url=page_url,
    )
    headers = build_jobadder_api_headers(access_token=access_token)

    # Keep the list-page helper aligned with the rest of the module:
    # - one shared transport helper
    # - one local shape validator
    # - one predictable return wrapper
    response_payload = _request_jobadder_json(
        endpoint_url=endpoint_url,
        headers=headers,
        timeout_seconds=timeout_seconds,
        provider_failure_message="JobAdder candidate read failed.",
        params=params,
    )

    return _normalise_jobadder_candidates_list_response(
        response_payload=response_payload,
        endpoint_url=endpoint_url,
        page=page,
        page_size=page_size,
    )


def fetch_jobadder_candidate_skills(
    *,
    api_url: str,
    access_token: str,
    candidate_id: int,
    timeout_seconds: float = 30.0,
) -> dict[str, Any]:
    """
    Fetch the structured skills tree for one JobAdder candidate.

    Parameters
    ----------
    api_url : str
        API base URL returned by JobAdder in the OAuth token response.

    access_token : str
        Stored bearer token used for authenticated JobAdder API requests.

    candidate_id : int
        JobAdder candidate identifier whose skills should be fetched.

    timeout_seconds : float
        HTTP timeout used for the provider request.

    Returns
    -------
    dict[str, Any]
        Normalised dictionary containing:

        - `categories`
        - `category_count`
        - `links`
        - `endpoint_url`
        - `raw_payload`

    Raises
    ------
    ValueError
        If the API URL, access token, or candidate ID is invalid.

    JobAdderApiError
        If JobAdder rejects the request, returns an unusable response, or
        cannot be reached safely.

    Notes
    -----
    - The OpenAPI spec documents a dedicated candidate-skills endpoint that
      returns a category -> subcategory -> skill hierarchy.
    - This is more useful than flat `skillTags` when the goal is to understand
      the real source-system skills structure before designing ingestion.

    In plain language:

    - build the candidate-skills URL
    - call JobAdder with the stored token
    - confirm the response contains a category list
    - return the structured skills tree in a predictable wrapper
    """
    # Structured skills are still tied to one concrete candidate record, so the
    # same candidate-ID validation rule applies here too.
    if candidate_id < 1:
        raise ValueError("JobAdder candidate_id must be at least 1.")

    # Keep the skill endpoint on the shared URL builder for the same reason as
    # every other helper: one place to enforce the `/v2` normalisation rule.
    endpoint_url = _build_jobadder_api_endpoint(
        api_url=api_url,
        resource_path=f"/candidates/{candidate_id}/skills",
    )
    headers = build_jobadder_api_headers(access_token=access_token)

    # Reuse the shared request helper to keep transport behaviour and provider
    # error handling aligned with the rest of the module.
    response_payload = _request_jobadder_json(
        endpoint_url=endpoint_url,
        headers=headers,
        timeout_seconds=timeout_seconds,
        provider_failure_message="JobAdder candidate skills read failed.",
    )

    raw_items = response_payload.get("items")

    # The skills endpoint is documented as a category list representation. If
    # `items` is missing or not a list, the backend should fail clearly rather
    # than guessing at an unknown structure.
    if not isinstance(raw_items, list):
        raise JobAdderApiError(
            "JobAdder candidate skills response did not include a category list.",
            endpoint_url=endpoint_url,
            response_body=response_payload,
        )

    raw_links = response_payload.get("links")
    links = raw_links if isinstance(raw_links, dict) else {}

    return {
        "categories": raw_items,
        "category_count": len(raw_items),
        "links": links,
        "endpoint_url": endpoint_url,
        "raw_payload": response_payload,
    }


def fetch_jobadder_candidate_notes(
    *,
    api_url: str,
    access_token: str,
    candidate_id: int,
    item_limit: int = 25,
    timeout_seconds: float = 30.0,
) -> dict[str, Any]:
    """
    Fetch candidate notes from the JobAdder API.

    Parameters
    ----------
    api_url : str
        API base URL returned by JobAdder in the OAuth token response.

        Example shapes:

            https://api.jobadder.com
            https://eu2api.jobadder.com/v2

    access_token : str
        Stored bearer token used for authenticated JobAdder API requests.

    candidate_id : int
        JobAdder candidate identifier whose notes should be fetched.

    item_limit : int
        Maximum number of note items to request from JobAdder for this first
        read.

    timeout_seconds : float
        HTTP timeout used for the provider request.

    Returns
    -------
    dict[str, Any]
        Normalised dictionary containing:

        - `notes`
        - `note_count`
        - `total_count`
        - `links`
        - `endpoint_url`
        - `raw_payload`

    Raises
    ------
    ValueError
        If the API URL, access token, candidate ID, or item limit is invalid.

    JobAdderApiError
        If JobAdder rejects the request, returns an unusable response, or
        cannot be reached safely.

    Notes
    -----
    - The candidate detail payload does not carry full note bodies directly.
    - Instead, JobAdder exposes candidate notes through a dedicated notes
      endpoint.
    - The OpenAPI spec also documents that the note list supports an extra
      `Fields=text` query parameter. This matters because, by default, note
      list items may only contain `textPartial` rather than the full note text.
    - This helper therefore requests `Fields=text` deliberately so the backend
      can inspect real note content rather than only truncated previews.

    Example
    -------
    A typical call looks like:

        fetch_jobadder_candidate_notes(
            api_url="https://eu2api.jobadder.com/v2/",
            access_token="...",
            candidate_id=16496678,
            item_limit=10,
        )

    and returns a dictionary of the form:

        {
            "notes": [...],
            "note_count": 2,
            "total_count": 2,
            "links": {...},
            "endpoint_url": "https://eu2api.jobadder.com/v2/candidates/16496678/notes",
            "raw_payload": {...},
        }

    In plain language:

    - build the candidate-notes URL
    - ask JobAdder for note records and include full note text when available
    - confirm the response contains a notes list
    - return that list in one predictable wrapper
    """

    # Candidate notes still belong to one concrete candidate record, so the
    # same candidate-ID validation rule applies here as it does to candidate
    # detail, skills, and attachments.
    if candidate_id < 1:
        raise ValueError("JobAdder candidate_id must be at least 1.")

    # Keep the first notes read intentionally bounded. We want a safe
    # inspection-friendly result before we later decide whether a wider sync,
    # pagination loop, or incremental notes ingestion is needed.
    if item_limit < 1:
        raise ValueError("JobAdder candidate notes item_limit must be at least 1.")

    endpoint_url = _build_jobadder_api_endpoint(
        api_url=api_url,
        resource_path=f"/candidates/{candidate_id}/notes",
    )
    headers = build_jobadder_api_headers(access_token=access_token)

    # Request `Fields=text` explicitly.
    #
    # This is a subtle but important point from the JobAdder docs:
    # - the list representation exposes `textPartial` by default
    # - full text is an opt-in additional field
    #
    # If we forget this, the backend may appear to "support notes" while only
    # ever retrieving truncated note previews. That would be a bad foundation
    # for mapping notes into the canonical system later.
    response_payload = _request_jobadder_json(
        endpoint_url=endpoint_url,
        headers=headers,
        timeout_seconds=timeout_seconds,
        provider_failure_message="JobAdder candidate notes read failed.",
        params={
            "Fields": ["text"],
            "Limit": item_limit,
        },
    )

    raw_items = response_payload.get("items")

    # A candidate-notes read is only useful if JobAdder actually returns a
    # notes list. If `items` is missing or malformed, fail clearly rather than
    # making up a best-effort interpretation of an unknown payload shape.
    if not isinstance(raw_items, list):
        raise JobAdderApiError(
            "JobAdder candidate notes response did not include an items list.",
            endpoint_url=endpoint_url,
            response_body=response_payload,
        )

    raw_links = response_payload.get("links")
    links = raw_links if isinstance(raw_links, dict) else {}

    raw_total_count = response_payload.get("totalCount")
    total_count: int | None = None

    # Keep the provider-reported total count when it is usable, but do not let
    # a malformed `totalCount` field poison an otherwise valid notes read.
    #
    # This is a good example of the distinction we want in integration code:
    # - the `items` list is essential to the helper's contract
    # - `totalCount` is useful metadata, but not structurally critical
    #
    # So we fail hard on a missing/malformed `items`, but degrade gracefully on
    # a weird total-count field.
    if raw_total_count is not None:
        try:
            total_count = int(raw_total_count)
        except (TypeError, ValueError):
            total_count = None

    return {
        "notes": raw_items,
        "note_count": len(raw_items),
        "total_count": total_count,
        "links": links,
        "endpoint_url": endpoint_url,
        "raw_payload": response_payload,
    }


def _build_jobadder_api_endpoint(*, api_url: str, resource_path: str) -> str:
    """
    Build one normalised JobAdder API endpoint URL from a stored API base.

    Parameters
    ----------
    api_url : str
        Stored JobAdder API base URL.

    resource_path : str
        Resource path to append, such as `/candidates` or
        `/candidates/123/skills`.

    Returns
    -------
    str
        Fully resolved JobAdder endpoint URL.

    Raises
    ------
    ValueError
        If the API URL or resource path is blank.

    Notes
    -----
    - JobAdder may return API bases both with and without the `/v2` segment.
    - Centralising the normalisation rule here ensures every helper uses the
      same URL-building logic and avoids reintroducing the earlier `/v2/v2/...`
      bug.

    Example
    -------
    These calls:

        _build_jobadder_api_endpoint(
            api_url="https://api.jobadder.com",
            resource_path="/candidates",
        )

    and:

        _build_jobadder_api_endpoint(
            api_url="https://eu2api.jobadder.com/v2/",
            resource_path="/candidates",
        )

    produce:

        https://api.jobadder.com/v2/candidates
        https://eu2api.jobadder.com/v2/candidates
    """
    # Normalise both inputs before joining them.
    #
    # The point is not just cosmetic trimming. It is to force every caller
    # through one predictable path shape regardless of whether they supplied:
    # - a trailing slash
    # - a leading slash
    # - an API base that already ends in `/v2`
    cleaned_api_url = api_url.strip()
    cleaned_resource_path = resource_path.strip()

    if cleaned_api_url == "":
        raise ValueError("JobAdder API URL cannot be empty.")

    if cleaned_resource_path == "":
        raise ValueError("JobAdder resource_path cannot be empty.")

    cleaned_api_base = cleaned_api_url.rstrip("/")
    cleaned_path = cleaned_resource_path.lstrip("/")

    if cleaned_api_base.endswith("/v2"):
        return f"{cleaned_api_base}/{cleaned_path}"

    return f"{cleaned_api_base}/v2/{cleaned_path}"


def _build_jobadder_candidate_page_request(
    *,
    api_url: str,
    page: int,
    page_size: int,
    page_url: str | None,
) -> tuple[str, dict[str, Any] | None]:
    """
    Build the endpoint URL and params for one candidate-page request.

    Parameters
    ----------
    api_url : str
        Stored JobAdder API base URL.

    page : int
        1-based page number for a fresh first-page request.

    page_size : int
        Requested provider page size for a fresh first-page request.

    page_url : str | None
        Optional provider-supplied next-page URL.

    Returns
    -------
    tuple[str, dict[str, Any] | None]
        Tuple containing:

        - the endpoint URL to call
        - optional query params for the request

    Notes
    -----
    - When a provider-supplied `next` URL exists, we trust it and send no
      extra params.
    - Otherwise we construct the first-page candidate endpoint and pass page
      parameters explicitly.

    Example
    -------
    The first-page request becomes:

        (
            "https://eu2api.jobadder.com/v2/candidates",
            {"page": 1, "pagesize": 100},
        )

    while a `next` link becomes:

        (
            "https://eu2api.jobadder.com/v2/candidates?page=2",
            None,
        )
    """

    if isinstance(page_url, str) and page_url.strip() != "":
        return page_url.strip(), None

    endpoint_url = _build_jobadder_api_endpoint(
        api_url=api_url,
        resource_path="/candidates",
    )
    params = {
        "page": page,
        "pagesize": page_size,
    }

    return endpoint_url, params


def _normalise_jobadder_candidates_list_response(
    *,
    response_payload: dict[str, Any],
    endpoint_url: str,
    page: int,
    page_size: int,
) -> dict[str, Any]:
    """
    Normalise one JobAdder candidates-list response into a predictable wrapper.

    Parameters
    ----------
    response_payload : dict[str, Any]
        Decoded provider payload returned by JobAdder.

    endpoint_url : str
        Concrete URL used for this read.

    page : int
        Requested page number for the current read.

    page_size : int
        Requested page size for the current read.

    Returns
    -------
    dict[str, Any]
        Normalised candidates-list page wrapper.

    Notes
    -----
    This helper keeps the list-shape validation logic in one place so both:

    - preview reads
    - paginated page reads

    can rely on the same structural assumptions.

    Example
    -------
    A successful result looks like:

        {
            "items": [...],
            "item_count": 100,
            "total_count": 3210,
            "links": {"next": "..."},
            "endpoint_url": "...",
            "page": 1,
            "page_size": 100,
            "raw_payload": {...},
        }
    """

    raw_items = response_payload.get("items")

    # The items list is the only truly mandatory part of this response shape.
    # If it is missing or malformed, later pagination logic cannot safely
    # continue.
    if not isinstance(raw_items, list):
        raise JobAdderApiError(
            "JobAdder candidate read response did not include an items list.",
            status_code=200,
            endpoint_url=endpoint_url,
            response_body=response_payload,
        )

    raw_links = response_payload.get("links")
    links = raw_links if isinstance(raw_links, dict) else {}

    raw_total_count = response_payload.get("totalCount")
    total_count: int | None = None

    if raw_total_count is not None:
        try:
            total_count = int(raw_total_count)
        except (TypeError, ValueError):
            total_count = None

    return {
        "items": raw_items,
        "item_count": len(raw_items),
        "total_count": total_count,
        "links": links,
        "endpoint_url": endpoint_url,
        "page": page,
        "page_size": page_size,
        "raw_payload": response_payload,
    }


def _request_jobadder_json(
    *,
    endpoint_url: str,
    headers: dict[str, str],
    timeout_seconds: float,
    provider_failure_message: str,
    params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Perform one authenticated JobAdder GET request and decode the JSON body.

    Parameters
    ----------
    endpoint_url : str
        Fully resolved JobAdder endpoint URL.

    headers : dict[str, str]
        Authenticated request headers to send.

    timeout_seconds : float
        HTTP timeout used for the provider request.

    provider_failure_message : str
        Message to use when JobAdder rejects the request with an HTTP error.

    params : dict[str, Any] | None
        Optional query parameters to send with the provider request.

    Returns
    -------
    dict[str, Any]
        Decoded JSON dictionary returned by JobAdder.

    Raises
    ------
    JobAdderApiError
        If the provider request fails, returns an HTTP error, or produces a
        non-dictionary JSON payload.

    Notes
    -----
    - The service helpers in this module all perform the same transport work:
      make one GET request, decode the JSON, and convert HTTP errors into one
      local exception type.
    - Keeping that shared logic here makes the individual endpoint helpers
      easier to read and reduces the chance of subtle behavioural drift.

    Example
    -------
    Public helpers such as:

        fetch_jobadder_candidate_detail(...)
        fetch_jobadder_candidate_attachments(...)
        fetch_jobadder_candidate_skills(...)
        fetch_jobadder_candidate_notes(...)

    all delegate their transport work here so they can focus on validating the
    resource-specific response shape instead of repeating HTTP boilerplate.
    """
    # Make exactly one GET request with the caller-supplied endpoint and
    # headers.
    #
    # This helper exists precisely so the public resource functions do not each
    # need to repeat the same:
    # - `httpx.get(...)`
    # - network exception conversion
    # - JSON decoding
    # - HTTP status handling
    #
    # sequence over and over.
    try:
        # Only pass query params when a caller actually supplied them.
        #
        # This keeps the common no-query case visually simple, while still
        # allowing resource-specific helpers such as candidate notes to opt in
        # to provider query features like:
        # - `Fields=text`
        # - `Limit=...`
        if params is None:
            response = httpx.get(
                endpoint_url,
                headers=headers,
                timeout=timeout_seconds,
            )
        else:
            response = httpx.get(
                endpoint_url,
                headers=headers,
                params=params,
                timeout=timeout_seconds,
            )
    except httpx.HTTPError as exc:
        raise JobAdderApiError(
            "Could not reach the JobAdder API.",
            endpoint_url=endpoint_url,
        ) from exc

    response_payload = _decode_jobadder_json_response(response)

    if response.status_code >= 400:
        raise JobAdderApiError(
            provider_failure_message,
            status_code=response.status_code,
            retry_after=_safe_string(response.headers.get("Retry-After")),
            endpoint_url=endpoint_url,
            response_body=response_payload,
        )

    # A successful helper contract in this module is always "decoded JSON
    # object". If the provider returns some other JSON top-level shape, surface
    # that clearly rather than letting each public helper make different
    # assumptions about it.
    if not isinstance(response_payload, dict):
        raise JobAdderApiError(
            "JobAdder API response did not decode into an object.",
            status_code=200,
            endpoint_url=endpoint_url,
            response_body={"decoded_json": response_payload},
        )

    return response_payload


def _request_jobadder_binary(
    *,
    endpoint_url: str,
    headers: dict[str, str],
    timeout_seconds: float,
    provider_failure_message: str,
) -> httpx.Response:
    """
    Perform one authenticated JobAdder GET request for binary content.

    Parameters
    ----------
    endpoint_url : str
        Fully resolved JobAdder endpoint URL.

    headers : dict[str, str]
        Authenticated request headers to send.

    timeout_seconds : float
        HTTP timeout used for the provider request.

    provider_failure_message : str
        Message to use when JobAdder rejects the request with an HTTP error.

    Returns
    -------
    httpx.Response
        Successful raw HTTP response so the caller can access:

        - `response.content`
        - `response.headers`

    Raises
    ------
    JobAdderApiError
        If the provider request fails or JobAdder returns an HTTP error.

    Notes
    -----
    - The JSON helpers in this module normalise successful responses into
      dictionaries because their callers need decoded JSON objects.
    - Binary downloads are different: the caller needs the raw bytes and the
      response headers, so this helper returns the successful `httpx.Response`
      object directly.

    Example
    -------
    The public attachment-download helper calls this function and then reads:

        response.content
        response.headers["Content-Type"]
        response.headers["Content-Disposition"]

    to build a smaller binary-download wrapper for the rest of the backend.
    """

    # Keep the transport behaviour aligned with the JSON request helper:
    # - one GET request
    # - one local exception type
    # - one place to convert transport and provider failures into a backend-
    #   friendly error shape
    try:
        response = httpx.get(
            endpoint_url,
            headers=headers,
            timeout=timeout_seconds,
        )
    except httpx.HTTPError as exc:
        raise JobAdderApiError(
            "Could not reach the JobAdder API.",
            endpoint_url=endpoint_url,
        ) from exc

    # If JobAdder rejects the binary request, still try to decode the response
    # as JSON for safe debugging context.
    #
    # Many provider error responses remain JSON even when the success path
    # would have been a file download, so reusing the JSON-fallback decoder here
    # gives callers better diagnostics than a blank binary failure.
    if response.status_code >= 400:
        response_payload = _decode_jobadder_json_response(response)

        raise JobAdderApiError(
            provider_failure_message,
            status_code=response.status_code,
            retry_after=_safe_string(response.headers.get("Retry-After")),
            endpoint_url=endpoint_url,
            response_body=response_payload,
        )

    return response


def _decode_jobadder_json_response(response: httpx.Response) -> dict[str, Any]:
    """
    Decode a JobAdder API response body into a dictionary.

    Parameters
    ----------
    response : httpx.Response
        Raw HTTP response from JobAdder.

    Returns
    -------
    dict[str, Any]
        Decoded JSON object, or a small fallback dictionary when the response
        body was not valid JSON.

    Notes
    -----
    - The JobAdder API is expected to return JSON.
    - If it does not, we still want controlled debugging context rather than an
      unrelated JSON parsing exception.

    Example
    -------
    If JobAdder returns valid JSON, this helper returns the decoded object.

    If JobAdder returns non-JSON text such as an HTML error page, this helper
    returns:

        {"raw_text": "..."}

    so the caller still has safe context to report.
    """
    # Try JSON first because that is the provider contract we expect.
    #
    # If that fails, keep a small fallback wrapper instead of letting the raw
    # JSON decoding error leak upward without context.
    try:
        decoded = response.json()
    except ValueError:
        return {
            "raw_text": response.text,
        }

    if isinstance(decoded, dict):
        return decoded

    return {
        "decoded_json": decoded,
    }


def _extract_file_name_from_content_disposition(
    content_disposition: Any,
) -> str | None:
    """
    Extract a file name from an HTTP `Content-Disposition` header when present.

    Parameters
    ----------
    content_disposition : Any
        Raw `Content-Disposition` header value.

    Returns
    -------
    str | None
        Extracted file name, or `None` when the header is missing or does not
        contain a usable `filename=...` value.

    Example
    -------
    Given a header such as:

        attachment; filename="Roger Campbell - CV 2025.pdf"

    this helper returns:

        Roger Campbell - CV 2025.pdf

    Notes
    -----
    - This helper is intentionally conservative.
    - It only handles the simple `filename=...` pattern because that is enough
      for the current transient-download stage.
    - If JobAdder later requires more advanced RFC 5987 parsing, that can be
      added here in one place.
    """

    if not isinstance(content_disposition, str):
        return None

    match = re.search(
        r'filename="?([^";]+)"?',
        content_disposition,
        flags=re.IGNORECASE,
    )

    if match is None:
        return None

    extracted_file_name = match.group(1).strip()

    if extracted_file_name == "":
        return None

    return extracted_file_name


def _safe_string(value: Any) -> str | None:
    """
    Convert a provider field into a stripped optional string.

    Parameters
    ----------
    value : Any
        Raw value read from a provider payload or header.

    Returns
    -------
    str | None
        Cleaned string value, or `None` when the field is missing or blank.

    Example
    -------
    These inputs produce:

        " 40 "   -> "40"
        ""       -> None
        None     -> None
    """

    if not isinstance(value, str):
        return None

    cleaned_value = value.strip()

    if cleaned_value == "":
        return None

    return cleaned_value


def _safe_int(value: Any) -> int | None:
    """
    Convert a provider field into an optional integer safely.

    Parameters
    ----------
    value : Any
        Raw value read from a provider payload or header.

    Returns
    -------
    int | None
        Parsed integer value, or `None` when the provider field is missing,
        blank, or unusable.

    Example
    -------
    These values become:

        "12345" -> 12345
        " 42 "  -> 42
        ""      -> None
        None    -> None

    Notes
    -----
    - This helper is mainly useful for HTTP headers such as `Content-Length`,
      which arrive as strings but are semantically numeric.
    """

    if isinstance(value, bool):
        return None

    if isinstance(value, int):
        return value

    if isinstance(value, float):
        return int(value)

    if not isinstance(value, str):
        return None

    cleaned_value = value.strip()

    if cleaned_value == "":
        return None

    try:
        return int(cleaned_value)
    except ValueError:
        return None


__all__ = [
    "JobAdderApiError",
    "build_jobadder_api_headers",
    "download_jobadder_candidate_attachment",
    "fetch_jobadder_application_detail",
    "fetch_jobadder_application_attachments",
    "fetch_jobadder_applications_preview",
    "fetch_jobadder_candidate_attachments",
    "fetch_jobadder_jobad_applications_preview",
    "fetch_jobadder_job_detail",
    "fetch_jobadder_jobads_preview",
    "fetch_jobadder_candidates_page",
    "fetch_jobadder_candidate_detail",
    "fetch_jobadder_candidate_notes",
    "fetch_jobadder_candidate_skills",
    "fetch_jobadder_candidates_preview",
]
