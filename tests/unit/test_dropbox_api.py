"""
Unit tests for Dropbox API helper functions.

This module tests the small authenticated Dropbox-read helpers in
`backend.services.dropbox_api`.

It gives the rest of the repository a stable way to check:

- whether current-account reads omit a JSON body when Dropbox expects none
- whether folder-list reads still send the expected JSON payload
- whether file-download reads use the Dropbox content-API request shape
- whether provider responses are normalized into one small backend exception

In plain language:

- this module answers the question:

    "Does the backend call the Dropbox read endpoints in the shape Dropbox expects?"

- this now covers both Dropbox API families used by the backend:
  - the normal JSON API for account and folder reads
  - the content API for transient file downloads
"""

import httpx
import pytest

from backend.services.dropbox_api import (
    DROPBOX_CREATE_FOLDER_URL,
    DROPBOX_DOWNLOAD_FILE_URL,
    DROPBOX_GET_CURRENT_ACCOUNT_URL,
    DROPBOX_LIST_FOLDER_URL,
    DROPBOX_UPLOAD_FILE_URL,
    DropboxApiError,
    ensure_dropbox_folder,
    download_dropbox_file,
    fetch_dropbox_current_account,
    fetch_dropbox_list_folder,
    upload_dropbox_file,
)


def test_fetch_dropbox_current_account_omits_json_null_body() -> None:
    """
    Verify that the current-account helper does not send JSON `null`.

    Notes
    -----
    Dropbox rejects `users/get_current_account` if the request includes a JSON
    body containing `null`. The helper should therefore omit the body entirely
    for that endpoint.

    Example
    -------
    A successful request should still include:

    - the bearer-token header
    - the accept header

    but it should not include:

    - a `json=` request argument
    - a `Content-Type: application/json` header
    """

    captured_request: dict[str, object] = {}

    def fake_post(url, **kwargs):
        captured_request["url"] = url
        captured_request["kwargs"] = kwargs
        return httpx.Response(
            200,
            json={"account_id": "dbid:AAExample"},
        )

    original_post = httpx.post
    httpx.post = fake_post
    try:
        result = fetch_dropbox_current_account(access_token="test-token")
    finally:
        httpx.post = original_post

    assert result["account"]["account_id"] == "dbid:AAExample"
    assert captured_request["url"] == DROPBOX_GET_CURRENT_ACCOUNT_URL

    request_kwargs = captured_request["kwargs"]
    assert isinstance(request_kwargs, dict)
    assert "json" not in request_kwargs

    headers = request_kwargs["headers"]
    assert isinstance(headers, dict)
    assert headers["Authorization"] == "Bearer test-token"
    assert headers["Accept"] == "application/json"
    assert "Content-Type" not in headers


def test_fetch_dropbox_list_folder_still_sends_json_payload() -> None:
    """
    Verify that the folder-list helper still sends the expected JSON body.

    Example
    -------
    The helper should continue to send:

    - the `path`
    - the recursion flag
    - the `limit`

    in a JSON payload for `files/list_folder`.
    """

    captured_request: dict[str, object] = {}

    def fake_post(url, **kwargs):
        captured_request["url"] = url
        captured_request["kwargs"] = kwargs
        return httpx.Response(
            200,
            json={"entries": [], "cursor": "fake-cursor", "has_more": False},
        )

    original_post = httpx.post
    httpx.post = fake_post
    try:
        result = fetch_dropbox_list_folder(
            access_token="test-token",
            path="",
            limit=25,
        )
    finally:
        httpx.post = original_post

    assert result["entry_count"] == 0
    assert captured_request["url"] == DROPBOX_LIST_FOLDER_URL

    request_kwargs = captured_request["kwargs"]
    assert isinstance(request_kwargs, dict)
    assert request_kwargs["json"] == {
        "path": "",
        "recursive": False,
        "limit": 25,
    }

    headers = request_kwargs["headers"]
    assert isinstance(headers, dict)
    assert headers["Content-Type"] == "application/json"


def test_fetch_dropbox_current_account_raises_for_provider_http_error() -> None:
    """
    Verify that provider-side HTTP failures become `DropboxApiError`.

    Example
    -------
    If Dropbox rejects the request with a 400 response, the helper should
    raise a backend exception carrying the endpoint URL and provider status.
    """

    def fake_post(url, **kwargs):
        return httpx.Response(
            400,
            text='Error in call to API function "users/get_current_account"',
        )

    original_post = httpx.post
    httpx.post = fake_post
    try:
        with pytest.raises(DropboxApiError) as exc_info:
            fetch_dropbox_current_account(access_token="test-token")
    finally:
        httpx.post = original_post

    error = exc_info.value
    assert error.status_code == 400
    assert error.endpoint_url == DROPBOX_GET_CURRENT_ACCOUNT_URL


def test_download_dropbox_file_sends_dropbox_api_arg_and_returns_bytes() -> None:
    """
    Verify that the file-download helper uses the Dropbox content-API request
    shape and returns transient file bytes plus metadata.

    Example
    -------
    The helper should:

    - send the bearer token
    - send a `Dropbox-API-Arg` header containing the target path
    - avoid a JSON request body
    - return file bytes, file name, and decoded metadata
    """

    captured_request: dict[str, object] = {}

    def fake_post(url, **kwargs):
        captured_request["url"] = url
        captured_request["kwargs"] = kwargs
        return httpx.Response(
            200,
            headers={
                "Content-Type": (
                    "application/vnd.openxmlformats-officedocument."
                    "wordprocessingml.document"
                ),
                "Dropbox-API-Result": (
                    '{"name":"Aman-Raja_cv-library.docx",'
                    '"path_display":"/tw394 = to CVR/Aman-Raja_cv-library.docx"}'
                ),
            },
            content=b"PK\x03\x04 fake docx bytes",
        )

    original_post = httpx.post
    httpx.post = fake_post
    try:
        result = download_dropbox_file(
            access_token="test-token",
            path="/tw394 = to CVR/Aman-Raja_cv-library.docx",
        )
    finally:
        httpx.post = original_post

    assert captured_request["url"] == DROPBOX_DOWNLOAD_FILE_URL

    request_kwargs = captured_request["kwargs"]
    assert isinstance(request_kwargs, dict)
    assert "json" not in request_kwargs

    headers = request_kwargs["headers"]
    assert isinstance(headers, dict)
    assert headers["Authorization"] == "Bearer test-token"
    assert headers["Dropbox-API-Arg"] == (
        '{"path": "/tw394 = to CVR/Aman-Raja_cv-library.docx"}'
    )

    assert result["file_name"] == "Aman-Raja_cv-library.docx"
    assert result["content_type"] == (
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )
    assert result["content_bytes"] == b"PK\x03\x04 fake docx bytes"
    assert result["file_metadata"]["path_display"] == (
        "/tw394 = to CVR/Aman-Raja_cv-library.docx"
    )


def test_download_dropbox_file_raises_when_metadata_header_is_invalid() -> None:
    """
    Verify that an invalid `Dropbox-API-Result` header becomes a normalized
    backend error instead of being ignored silently.

    Example
    -------
    If Dropbox returns a malformed metadata header, the helper should raise
    `DropboxApiError` with the endpoint and safe request payload attached.
    """

    def fake_post(url, **kwargs):
        return httpx.Response(
            200,
            headers={
                "Dropbox-API-Result": "not-json",
            },
            content=b"fake-bytes",
        )

    original_post = httpx.post
    httpx.post = fake_post
    try:
        with pytest.raises(DropboxApiError) as exc_info:
            download_dropbox_file(
                access_token="test-token",
                path="/tw394 = to CVR/Broken.docx",
            )
    finally:
        httpx.post = original_post

    error = exc_info.value
    assert error.endpoint_url == DROPBOX_DOWNLOAD_FILE_URL
    assert error.request_payload == {"path": "/tw394 = to CVR/Broken.docx"}
    assert error.response_body == {"raw_dropbox_api_result": "not-json"}


def test_ensure_dropbox_folder_treats_existing_folder_conflict_as_success() -> None:
    """
    Verify that an existing Dropbox folder does not fail the helper.
    """

    def fake_post(url, **kwargs):
        return httpx.Response(
            409,
            json={"error_summary": "path/conflict/folder/.."},
        )

    original_post = httpx.post
    httpx.post = fake_post
    try:
        result = ensure_dropbox_folder(
            access_token="test-token",
            path="/Exports/Email CVs",
        )
    finally:
        httpx.post = original_post

    assert result["created"] is False
    assert result["path"] == "/Exports/Email CVs"
    assert result["endpoint_url"] == DROPBOX_CREATE_FOLDER_URL


def test_upload_dropbox_file_sends_content_api_request() -> None:
    """
    Verify that the upload helper sends Dropbox content bytes with API-Arg metadata.
    """

    captured_calls: list[tuple[str, dict[str, object]]] = []

    def fake_post(url, **kwargs):
        captured_calls.append((url, kwargs))
        if url == DROPBOX_CREATE_FOLDER_URL:
            return httpx.Response(200, json={"metadata": {"path_display": "/Exports"}})
        return httpx.Response(
            200,
            json={"name": "resume.pdf", "path_display": "/Exports/resume.pdf"},
        )

    original_post = httpx.post
    httpx.post = fake_post
    try:
        result = upload_dropbox_file(
            access_token="test-token",
            path="/Exports/resume.pdf",
            content_bytes=b"%PDF-test%",
        )
    finally:
        httpx.post = original_post

    assert result["path"] == "/Exports/resume.pdf"
    assert result["endpoint_url"] == DROPBOX_UPLOAD_FILE_URL
    assert len(captured_calls) == 2

    upload_url, upload_kwargs = captured_calls[1]
    assert upload_url == DROPBOX_UPLOAD_FILE_URL
    headers = upload_kwargs["headers"]
    assert isinstance(headers, dict)
    assert headers["Authorization"] == "Bearer test-token"
    assert headers["Content-Type"] == "application/octet-stream"
    assert upload_kwargs["content"] == b"%PDF-test%"
