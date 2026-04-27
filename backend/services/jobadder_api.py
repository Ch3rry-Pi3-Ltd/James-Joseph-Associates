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

This helper therefore builds the first preview URL as:

    {API_URL}/v2/candidates

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

        Example shape:

            https://api.jobadder.com

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

    That is a conservative first target because JobAdder's documentation shows
    candidate GETs under `/v2/candidates`, including list reads.

    In plain language:

    - build the candidate-list URL
    - call JobAdder with the stored token
    - confirm the response has a candidate `items` list
    - return a trimmed preview of that first page
    """

    cleaned_api_url = api_url.strip()
    cleaned_access_token = access_token.strip()

    if cleaned_api_url == "":
        raise ValueError("JobAdder API URL cannot be empty.")

    if cleaned_access_token == "":
        raise ValueError("JobAdder access token cannot be empty.")

    if item_limit < 1:
        raise ValueError("JobAdder candidate preview item_limit must be at least 1.")

    endpoint_url = f"{cleaned_api_url.rstrip('/')}/v2/candidates"
    headers = build_jobadder_api_headers(access_token=cleaned_access_token)

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

    # If JobAdder rejects the request, return one structured local exception
    # rather than leaking raw provider handling into every route.
    if response.status_code >= 400:
        raise JobAdderApiError(
            "JobAdder candidate read failed.",
            status_code=response.status_code,
            retry_after=_safe_string(response.headers.get("Retry-After")),
            endpoint_url=endpoint_url,
            response_body=response_payload,
        )

    raw_items = response_payload.get("items")

    # A successful list response is only useful if it actually contains an
    # `items` array. Fail fast if JobAdder returns something unexpected
    if not isinstance(raw_items, list):
        raise JobAdderApiError(
            "JobAdder candidate read response did not include an items list.",
            status_code=response.status_code,
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
    #   - We fetch the provider's first page as-is.
    #   - Then we trim the returned list locally so the API route can expose a
    #     predictable small preview.
    items = raw_items[:item_limit]

    return {
        "items": items,
        "item_count": len(items),
        "total_count": total_count,
        "links": links,
        "endpoint_url": endpoint_url,
        "raw_payload": response_payload,
    }


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
    """

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
    "fetch_jobadder_candidates_preview",
]