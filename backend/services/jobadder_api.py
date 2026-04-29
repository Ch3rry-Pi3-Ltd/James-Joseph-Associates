"""
JobAdder API read helpers for the intelligence backend.

This module contains the first small service helpers for making authenticated
read-only requests to the JobAdder API after OAuth has completed successfully.

It gives the rest of the repository a stable way to talk about:

- building the Authorization header for JobAdder API requests
- using the stored JobAdder access token safely
- calling one small read-only JobAdder endpoint
- Normalising provider-side HTTP and payload errors into one local exception
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

Scope of this first step
------------------------
This module intentionally starts small.

Rather than building a large general-purpose JobAdder client immediately, it
implements one narrow, safe, read-only helper:

- fetch a first-page preview of candidates from the authenticated JobAdder
  account

This is enough to prove:

- the stored token is valid for API use
- the stored `api` base URL returned by JobAdder is usuable
- the backend can parse a real JobAdder response
- we can inspect live payload structure before deciding how to ingest it

Notes on the chosen endpoint
----------------------------
JobAdder's official documentation shows candidate reads under `/v2/candidates`,
including:

- `GET https://api.jobadder.com/v2/candidates/{CANDIDATE_ID}`
- list reads under `https://api.jobadder.com/v2/candidates?...`

The OAuth token response also returns an `api` field, which is the API base URL
associated with the connected JobAdder account.

This helper therefore builds the first preview URL as one of:

    {API_URL}/v2/candidates

or, when the stored API URL already ends in `/v2`:

    {API_URL}/candidates

Example
-------
Typical callers in the rest of the backend do not hand-build URLs directly.
Instead, they call helpers such as:

    fetch_jobadder_candidates_preview(
        api_url="https://eu2api.jobadder.com/v2/",
        access_token="...",
        item_limit=10,
    )

and receive a small normalised wrapper rather than a raw `httpx.Response`.

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


def _request_jobadder_json(
    *,
    endpoint_url: str,
    headers: dict[str, str],
    timeout_seconds: float,
    provider_failure_message: str,
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


__all__ = [
    "JobAdderApiError",
    "build_jobadder_api_headers",
    "fetch_jobadder_candidate_attachments",
    "fetch_jobadder_candidate_detail",
    "fetch_jobadder_candidate_skills",
    "fetch_jobadder_candidates_preview",
]
