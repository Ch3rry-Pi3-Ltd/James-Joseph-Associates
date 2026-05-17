"""
Unit tests for Dropbox API helper functions.

This module tests the small authenticated Dropbox-read helpers in
`backend.services.dropbox_api`.

It gives the rest of the repository a stable way to check:

- whether current-account reads omit a JSON body when Dropbox expects none
- whether folder-list reads still send the expected JSON payload
- whether provider responses are normalized into one small backend exception

In plain language:

- this module answers the question:

    "Does the backend call the Dropbox read endpoints in the shape Dropbox expects?"
"""

import httpx
import pytest

from backend.services.dropbox_api import (
    DROPBOX_GET_CURRENT_ACCOUNT_URL,
    DROPBOX_LIST_FOLDER_URL,
    DropboxApiError,
    fetch_dropbox_current_account,
    fetch_dropbox_list_folder,
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
    - the recursion flags
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
        "include_deleted": False,
        "include_has_explicit_shared_members": False,
        "include_mounted_folders": True,
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
