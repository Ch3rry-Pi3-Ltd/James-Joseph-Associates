"""
Dropbox API helper functions for the intelligence backend.

This module contains the first authenticated Dropbox read helpers used after
OAuth succeeds.

It gives the rest of the repository a stable way to talk about:

- reading the connected Dropbox account profile
- listing the contents of a Dropbox folder
- downloading one Dropbox file transiently for later extraction work
- normalizing provider failures into one small backend exception type

Keeping this logic in its own module makes the project easier to extend because:

- route handlers do not need to know Dropbox endpoint URLs
- token refresh and storage logic stay separate from content reads
- later Dropbox CV-download work can reuse the same authenticated transport
  rules

Example
-------
Typical usage in the rest of the backend looks like:

    account = fetch_dropbox_current_account(access_token="...")
    folder_preview = fetch_dropbox_list_folder(
        access_token="...",
        path="",
        limit=25,
    )
    downloaded_file = download_dropbox_file(
        access_token="...",
        path="/tw394 = to CVR/Aman-Raja_cv-library.docx",
    )

In plain language:

- this module answers the questions:

    "Can the backend read the connected Dropbox account?"
    "Can the backend list a Dropbox folder after OAuth succeeds?"

- it does not build OAuth URLs
- it does not store tokens
- it does not persist files locally
- it only performs authenticated Dropbox reads and transient file downloads
"""

import json
from pathlib import PurePosixPath
from typing import Any

import httpx

DROPBOX_GET_CURRENT_ACCOUNT_URL = "https://api.dropboxapi.com/2/users/get_current_account"
DROPBOX_LIST_FOLDER_URL = "https://api.dropboxapi.com/2/files/list_folder"
DROPBOX_DOWNLOAD_FILE_URL = "https://content.dropboxapi.com/2/files/download"


class DropboxApiError(RuntimeError):
    """
    Raised when the backend cannot complete an authenticated Dropbox API read
    safely.

    Attributes
    ----------
    message : str
        Safe human-readable explanation of what failed.

    status_code : int | None
        HTTP status code returned by Dropbox, if a provider response existed.

    endpoint_url : str | None
        Provider endpoint URL associated with the failure, when known.

    response_body : dict[str, Any] | None
        Safe decoded provider response body when available.

    request_payload : dict[str, Any] | None
        Safe JSON payload that the backend attempted to send to Dropbox, when
        one existed.

    Notes
    -----
    - This exception is meant for backend control flow.
    - Route handlers can catch it and convert it into the project's normal API
      error shape.

    Example
    -------
    Callers may inspect:

        error.status_code
        error.endpoint_url
        error.response_body

    to distinguish between:

    - invalid or expired access tokens
    - missing scopes
    - malformed requests
    - general provider-side failures
    """

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        endpoint_url: str | None = None,
        response_body: dict[str, Any] | None = None,
        request_payload: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.endpoint_url = endpoint_url
        self.response_body = response_body
        self.request_payload = request_payload

    def __str__(self) -> str:
        """
        Return the human-readable error message.

        In plain language:

        - when this exception is printed
        - show the main message
        """

        return self.message


def fetch_dropbox_current_account(
    *,
    access_token: str,
    timeout_seconds: float = 30.0,
) -> dict[str, Any]:
    """
    Fetch the currently connected Dropbox account profile.

    Parameters
    ----------
    access_token : str
        Dropbox OAuth access token to use for the read.

    timeout_seconds : float
        HTTP timeout used for the provider request.

    Returns
    -------
    dict[str, Any]
        Normalized account payload containing:

        - `account`
        - `endpoint_url`
        - `raw_payload`

    Raises
    ------
    DropboxApiError
        If Dropbox rejects the request, returns invalid JSON, or cannot be
        reached safely.

    Example
    -------
    Calling:

        fetch_dropbox_current_account(access_token="...")

    returns a dictionary wrapping the provider account object so the route can
    add its own connection context around it.
    """
    # `users/get_current_account` is the smallest useful authenticated Dropbox
    # read we can make after OAuth succeeds.
    #
    # It answers the practical setup question:
    # - did Tom authorize the correct Dropbox account?
    # before we spend time inspecting any folder structure.
    payload = _post_to_dropbox_api(
        endpoint_url=DROPBOX_GET_CURRENT_ACCOUNT_URL,
        access_token=access_token,
        json_payload=None,
        timeout_seconds=timeout_seconds,
        provider_failure_message="Dropbox current-account read failed.",
    )

    return {
        "account": payload,
        "endpoint_url": DROPBOX_GET_CURRENT_ACCOUNT_URL,
        "raw_payload": payload,
    }


def fetch_dropbox_list_folder(
    *,
    access_token: str,
    path: str,
    recursive: bool = False,
    limit: int = 25,
    timeout_seconds: float = 30.0,
) -> dict[str, Any]:
    """
    Fetch a first-page preview of a Dropbox folder.

    Parameters
    ----------
    access_token : str
        Dropbox OAuth access token to use for the read.

    path : str
        Dropbox folder path to list.

        Use the empty string to list the root folder.

    recursive : bool
        Whether Dropbox should traverse subfolders recursively.

    limit : int
        Maximum number of entries to request in the first page.

    timeout_seconds : float
        HTTP timeout used for the provider request.

    Returns
    -------
    dict[str, Any]
        Normalized folder preview containing:

        - `path`
        - `entry_count`
        - `entries`
        - `cursor`
        - `has_more`
        - `endpoint_url`
        - `raw_payload`

    Raises
    ------
    DropboxApiError
        If Dropbox rejects the request, returns invalid JSON, or cannot be
        reached safely.

    Notes
    -----
    - This is intentionally a first-page preview helper, not yet a complete
      full-cursor traversal engine.
    - That keeps the first Dropbox source-review slice small and predictable.

    Example
    -------
    Calling:

        fetch_dropbox_list_folder(
            access_token="...",
            path="",
            limit=25,
        )

    returns a first-page preview of the root folder.
    """
    # Keep the first Dropbox folder read deliberately narrow.
    #
    # This route is for source-shape inspection, not full ingestion yet, so:
    # - one page is enough to prove access
    # - one page is enough to inspect naming and folder semantics
    # - we avoid prematurely building cursor-traversal logic before the actual
    #   source layout has been reviewed
    payload = _post_to_dropbox_api(
        endpoint_url=DROPBOX_LIST_FOLDER_URL,
        access_token=access_token,
        json_payload={
            "path": path,
            "recursive": recursive,
            "include_deleted": False,
            "include_has_explicit_shared_members": False,
            "include_mounted_folders": True,
            "limit": limit,
        },
        timeout_seconds=timeout_seconds,
        provider_failure_message="Dropbox folder listing failed.",
    )

    raw_entries = payload.get("entries")
    entries = raw_entries if isinstance(raw_entries, list) else []

    return {
        "path": path,
        "entry_count": len(entries),
        "entries": entries,
        "cursor": payload.get("cursor"),
        "has_more": bool(payload.get("has_more")),
        "endpoint_url": DROPBOX_LIST_FOLDER_URL,
        "raw_payload": payload,
    }


def download_dropbox_file(
    *,
    access_token: str,
    path: str,
    timeout_seconds: float = 60.0,
) -> dict[str, Any]:
    """
    Download one Dropbox file transiently into memory.

    Parameters
    ----------
    access_token : str
        Dropbox OAuth access token to use for the read.

    path : str
        Full Dropbox file path to download.

    timeout_seconds : float
        HTTP timeout used for the provider request.

    Returns
    -------
    dict[str, Any]
        Normalized transient file download containing:

        - `path`
        - `file_name`
        - `content_type`
        - `content_bytes`
        - `file_metadata`
        - `endpoint_url`

    Raises
    ------
    DropboxApiError
        If Dropbox rejects the request, cannot be reached safely, or returns
        malformed metadata for the download response.

    Notes
    -----
    - This helper is intentionally transient. It downloads the file into
      memory and returns the bytes to the caller.
    - It does not persist the file locally.
    - That keeps the first Dropbox CV-read slice aligned with the current
      JobAdder resume-download strategy.

    Example
    -------
    Calling:

        download_dropbox_file(
            access_token="...",
            path="/tw394 = to CVR/Aman-Raja_cv-library.docx",
        )

    returns the file bytes plus the small amount of metadata needed for later
    text extraction and provenance handling.
    """
    # This is the narrow primitive we need before full Dropbox ingestion:
    # - prove that the saved OAuth token can fetch real file bytes
    # - preserve enough metadata for later extraction
    # - keep the file transient so we do not introduce local file-management
    #   behavior before deciding the wider ingestion flow
    result = _post_to_dropbox_content_api(
        endpoint_url=DROPBOX_DOWNLOAD_FILE_URL,
        access_token=access_token,
        api_arg_payload={"path": path},
        timeout_seconds=timeout_seconds,
        provider_failure_message="Dropbox file download failed.",
    )

    response = result["response"]
    file_metadata = result["api_result_payload"]
    content_bytes = response.content
    content_type = response.headers.get("Content-Type")

    # Dropbox usually returns the file name in the structured metadata header.
    # Keep a path-based fallback anyway because later CV extraction and
    # provenance code should still have a sensible file name even if Dropbox
    # omits or degrades that metadata on an edge-case response.
    metadata_file_name = file_metadata.get("name")
    fallback_file_name = PurePosixPath(path).name
    file_name = (
        metadata_file_name
        if isinstance(metadata_file_name, str) and metadata_file_name.strip() != ""
        else fallback_file_name
    )

    return {
        "path": path,
        "file_name": file_name,
        "content_type": content_type,
        "content_bytes": content_bytes,
        "file_metadata": file_metadata,
        "endpoint_url": DROPBOX_DOWNLOAD_FILE_URL,
    }


def _post_to_dropbox_api(
    *,
    endpoint_url: str,
    access_token: str,
    json_payload: dict[str, Any] | None,
    timeout_seconds: float,
    provider_failure_message: str,
) -> dict[str, Any]:
    """
    Send one authenticated POST request to a Dropbox API endpoint and decode
    the JSON response.

    Parameters
    ----------
    endpoint_url : str
        Dropbox API endpoint URL to call.

    access_token : str
        Dropbox OAuth access token to use for the request.

    json_payload : dict[str, Any] | None
        Optional JSON body to send with the request.

    timeout_seconds : float
        HTTP timeout used for the provider request.

    provider_failure_message : str
        Message to use when Dropbox returns an HTTP error response.

    Returns
    -------
    dict[str, Any]
        Decoded JSON response body.

    Raises
    ------
    DropboxApiError
        If Dropbox rejects the request, returns invalid JSON, or cannot be
        reached safely.

    Example
    -------
    This helper powers both:

        fetch_dropbox_current_account(...)
        fetch_dropbox_list_folder(...)

    so those public helpers stay focused on resource-specific shaping rather
    than transport mechanics.
    """
    # Strip and validate the token locally first so obviously bad credential
    # state is surfaced as a local programming/storage problem rather than
    # blurred together with a provider-side auth failure.
    # The Dropbox content API differs from the JSON API:
    # - request arguments are passed via the `Dropbox-API-Arg` header
    # - the response body is raw file bytes, not JSON
    # - structured file metadata comes back in the `Dropbox-API-Result` header
    #
    # Keeping that shape in a dedicated helper stops the public
    # `download_dropbox_file(...)` function from having to mix:
    # - provider transport quirks
    # - raw byte handling
    # - file-specific output shaping
    cleaned_access_token = access_token.strip()

    if cleaned_access_token == "":
        raise DropboxApiError(
            "Dropbox API access token cannot be empty.",
            endpoint_url=endpoint_url,
            request_payload=json_payload,
        )

    request_headers = {
        "Accept": "application/json",
        "Authorization": f"Bearer {cleaned_access_token}",
    }
    request_kwargs: dict[str, Any] = {
        "headers": request_headers,
        "timeout": timeout_seconds,
    }

    # Some Dropbox endpoints, such as `users/get_current_account`, expect no
    # request body at all. Sending JSON `null` is still a body, and Dropbox
    # rejects that shape as malformed JSON input.
    if json_payload is not None:
        request_headers["Content-Type"] = "application/json"
        request_kwargs["json"] = json_payload

    try:
        response = httpx.post(
            endpoint_url,
            **request_kwargs,
        )
    except httpx.HTTPError as exc:
        raise DropboxApiError(
            "Could not reach the Dropbox API endpoint.",
            endpoint_url=endpoint_url,
            request_payload=json_payload,
        ) from exc

    response_payload = _decode_dropbox_json_response(response)

    if response.status_code >= 400:
        raise DropboxApiError(
            provider_failure_message,
            status_code=response.status_code,
            endpoint_url=endpoint_url,
            response_body=response_payload,
            request_payload=json_payload,
        )

    return response_payload


def _post_to_dropbox_content_api(
    *,
    endpoint_url: str,
    access_token: str,
    api_arg_payload: dict[str, Any],
    timeout_seconds: float,
    provider_failure_message: str,
) -> dict[str, Any]:
    """
    Send one authenticated Dropbox content-API request and return the raw HTTP
    response plus the decoded metadata header.

    Parameters
    ----------
    endpoint_url : str
        Dropbox content API endpoint URL to call.

    access_token : str
        Dropbox OAuth access token to use for the request.

    api_arg_payload : dict[str, Any]
        Payload to encode into the `Dropbox-API-Arg` header.

    timeout_seconds : float
        HTTP timeout used for the provider request.

    provider_failure_message : str
        Message to use when Dropbox returns an HTTP error response.

    Returns
    -------
    dict[str, Any]
        Dictionary containing:

        - `response`
        - `api_result_payload`

    Raises
    ------
    DropboxApiError
        If Dropbox rejects the request, cannot be reached safely, or returns
        malformed download metadata.

    Example
    -------
    This helper powers:

        download_dropbox_file(...)

    so the public helper can focus on file-specific shaping rather than the
    Dropbox content-API transport details.
    """
    cleaned_access_token = access_token.strip()

    if cleaned_access_token == "":
        raise DropboxApiError(
            "Dropbox API access token cannot be empty.",
            endpoint_url=endpoint_url,
            request_payload=api_arg_payload,
        )

    request_headers = {
        "Authorization": f"Bearer {cleaned_access_token}",
        "Dropbox-API-Arg": json.dumps(api_arg_payload),
    }

    try:
        response = httpx.post(
            endpoint_url,
            headers=request_headers,
            timeout=timeout_seconds,
        )
    except httpx.HTTPError as exc:
        raise DropboxApiError(
            "Could not reach the Dropbox content API endpoint.",
            endpoint_url=endpoint_url,
            request_payload=api_arg_payload,
        ) from exc

    if response.status_code >= 400:
        raise DropboxApiError(
            provider_failure_message,
            status_code=response.status_code,
            endpoint_url=endpoint_url,
            response_body=_decode_dropbox_json_response(response),
            request_payload=api_arg_payload,
        )

    api_result_payload = _decode_dropbox_api_result_header(
        response=response,
        endpoint_url=endpoint_url,
        request_payload=api_arg_payload,
    )

    return {
        "response": response,
        "api_result_payload": api_result_payload,
    }


def _decode_dropbox_json_response(response: httpx.Response) -> dict[str, Any]:
    """
    Decode a Dropbox API response body into a dictionary.

    Parameters
    ----------
    response : httpx.Response
        Raw HTTP response from Dropbox.

    Returns
    -------
    dict[str, Any]
        Decoded JSON object, or a small fallback dictionary when the response
        body was not valid JSON.

    Example
    -------
    If Dropbox returns valid JSON, this helper returns that decoded object.
    Otherwise it returns a small fallback payload such as:

        {"raw_text": "..."}
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


def _decode_dropbox_api_result_header(
    *,
    response: httpx.Response,
    endpoint_url: str,
    request_payload: dict[str, Any],
) -> dict[str, Any]:
    """
    Decode the Dropbox `Dropbox-API-Result` response header when present.

    Parameters
    ----------
    response : httpx.Response
        Raw HTTP response returned by Dropbox.

    endpoint_url : str
        Dropbox endpoint URL used for error context.

    request_payload : dict[str, Any]
        Safe request payload used for error context.

    Returns
    -------
    dict[str, Any]
        Decoded Dropbox metadata payload, or an empty dictionary when Dropbox
        omitted the header.

    Raises
    ------
    DropboxApiError
        If Dropbox returned a metadata header that was not valid JSON.

    Example
    -------
    A successful Dropbox download often includes metadata like:

        {"name": "Aman-Raja_cv-library.docx", "path_display": "/..."}

    in the `Dropbox-API-Result` header. This helper turns that into a normal
    Python dictionary for the caller.
    """
    raw_header_value = response.headers.get("Dropbox-API-Result")

    if raw_header_value is None or raw_header_value.strip() == "":
        return {}

    try:
        decoded = json.loads(raw_header_value)
    except ValueError as exc:
        raise DropboxApiError(
            "Dropbox file download returned invalid metadata.",
            endpoint_url=endpoint_url,
            request_payload=request_payload,
            response_body={"raw_dropbox_api_result": raw_header_value},
        ) from exc

    if isinstance(decoded, dict):
        return decoded

    return {
        "decoded_json": decoded,
    }


__all__ = [
    "DROPBOX_DOWNLOAD_FILE_URL",
    "DROPBOX_GET_CURRENT_ACCOUNT_URL",
    "DROPBOX_LIST_FOLDER_URL",
    "DropboxApiError",
    "download_dropbox_file",
    "fetch_dropbox_current_account",
    "fetch_dropbox_list_folder",
]
