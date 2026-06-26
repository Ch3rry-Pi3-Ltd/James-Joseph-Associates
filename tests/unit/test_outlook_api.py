"""
Unit tests for Outlook / Microsoft Graph mail helper functions.

This module tests the narrow authenticated Outlook attachment-download helper
in `backend.services.outlook_api`.

It gives the rest of the repository a stable way to check:

- whether file-attachment reads use the expected Graph endpoint
- whether Graph file-attachment payloads decode into usable bytes
- whether child-folder reads use the expected Graph endpoint
- whether unsupported attachment types fail clearly

In plain language:

- this module answers the question:

    "Does the backend call the Outlook attachment endpoint in the shape we expect?"
"""

import httpx
import pytest

from backend.services.outlook_api import (
    GRAPH_ME_URL,
    OutlookApiError,
    download_outlook_message_file_attachment,
    fetch_outlook_child_mail_folders,
    fetch_outlook_messages,
)


def test_download_outlook_message_file_attachment_decodes_base64_payload() -> None:
    """
    Verify that the helper decodes Graph file-attachment content bytes.

    Example
    -------
    A successful request should:

    - hit the attachment detail endpoint
    - decode the `contentBytes` field
    - return file metadata plus raw bytes
    """

    captured_request: dict[str, object] = {}

    def fake_get(url, **kwargs):
        captured_request["url"] = url
        captured_request["kwargs"] = kwargs
        return httpx.Response(
            200,
            json={
                "@odata.type": "#microsoft.graph.fileAttachment",
                "id": "att-1",
                "name": "cv.pdf",
                "contentType": "application/pdf",
                "contentBytes": "ZmFrZS1wZGYtYnl0ZXM=",
            },
        )

    original_get = httpx.get
    httpx.get = fake_get
    try:
        result = download_outlook_message_file_attachment(
            access_token="test-token",
            message_id="msg-1",
            attachment_id="att-1",
        )
    finally:
        httpx.get = original_get

    assert captured_request["url"] == (
        f"{GRAPH_ME_URL}/messages/msg-1/attachments/att-1"
    )

    request_kwargs = captured_request["kwargs"]
    assert isinstance(request_kwargs, dict)
    headers = request_kwargs["headers"]
    assert isinstance(headers, dict)
    assert headers["Authorization"] == "Bearer test-token"
    assert headers["Accept"] == "application/json"

    assert result["file_name"] == "cv.pdf"
    assert result["content_type"] == "application/pdf"
    assert result["content_bytes"] == b"fake-pdf-bytes"


def test_download_outlook_message_file_attachment_rejects_non_file_attachment() -> None:
    """
    Verify that the helper rejects non-file attachments clearly.

    Example
    -------
    If Graph returns an `itemAttachment`, the helper should raise
    `OutlookApiError` instead of pretending the payload is a resume file.
    """

    def fake_get(url, **kwargs):
        return httpx.Response(
            200,
            json={
                "@odata.type": "#microsoft.graph.itemAttachment",
                "id": "att-1",
                "name": "forwarded-message.eml",
            },
        )

    original_get = httpx.get
    httpx.get = fake_get
    try:
        with pytest.raises(OutlookApiError) as exc_info:
            download_outlook_message_file_attachment(
                access_token="test-token",
                message_id="msg-1",
                attachment_id="att-1",
            )
    finally:
        httpx.get = original_get

    error = exc_info.value
    assert error.endpoint_url == f"{GRAPH_ME_URL}/messages/msg-1/attachments/att-1"
    assert error.response_body == {
        "@odata.type": "#microsoft.graph.itemAttachment",
        "id": "att-1",
        "name": "forwarded-message.eml",
    }


def test_fetch_outlook_child_mail_folders_uses_child_folders_endpoint() -> None:
    """
    Verify that the helper reads one direct child-folder level correctly.

    Example
    -------
    A successful request should:

    - hit the `childFolders` endpoint for the supplied parent folder
    - return the first-page folder objects under that parent
    """

    captured_request: dict[str, object] = {}

    def fake_get(url, **kwargs):
        captured_request["url"] = url
        captured_request["kwargs"] = kwargs
        return httpx.Response(
            200,
            json={
                "value": [
                    {"id": "folder-1", "displayName": "### DOMINIQUE FOLDER"},
                    {"id": "folder-2", "displayName": "Other"},
                ]
            },
        )

    original_get = httpx.get
    httpx.get = fake_get
    try:
        result = fetch_outlook_child_mail_folders(
            access_token="test-token",
            parent_folder_id="parent-123",
            mailbox=None,
            limit=100,
        )
    finally:
        httpx.get = original_get

    assert captured_request["url"] == (
        f"{GRAPH_ME_URL}/mailFolders/parent-123/childFolders?%24top=100"
    )
    assert result["parent_folder_id"] == "parent-123"
    assert result["folder_count"] == 2
    assert result["folders"][0]["displayName"] == "### DOMINIQUE FOLDER"


def test_fetch_outlook_messages_follows_graph_next_link_until_window_exhausted() -> None:
    """
    Verify that message reads paginate through the full bounded window.

    Example
    -------
    A successful request should:

    - hit the initial folder messages endpoint
    - follow `@odata.nextLink`
    - return one combined message list
    """

    captured_urls: list[str] = []

    def fake_get(url, **kwargs):
        captured_urls.append(url)
        if len(captured_urls) == 1:
            return httpx.Response(
                200,
                json={
                    "value": [
                        {"id": "msg-1", "subject": "First", "hasAttachments": False},
                        {"id": "msg-2", "subject": "Second", "hasAttachments": True},
                    ],
                    "@odata.nextLink": "https://graph.microsoft.com/v1.0/me/messages?page=2",
                },
            )

        return httpx.Response(
            200,
            json={
                "value": [
                    {"id": "msg-3", "subject": "Third", "hasAttachments": False},
                ]
            },
        )

    original_get = httpx.get
    httpx.get = fake_get
    try:
        result = fetch_outlook_messages(
            access_token="test-token",
            folder_id="inbox-folder",
            mailbox=None,
            limit=100,
        )
    finally:
        httpx.get = original_get

    assert captured_urls[0] == (
        f"{GRAPH_ME_URL}/mailFolders/inbox-folder/messages?"
        "%24top=100&%24select=id%2Csubject%2CreceivedDateTime%2Cfrom%2ChasAttachments%2CinternetMessageId%2CconversationId&%24orderby=receivedDateTime+desc"
    )
    assert captured_urls[1] == "https://graph.microsoft.com/v1.0/me/messages?page=2"
    assert result["message_page_size"] == 100
    assert result["page_count"] == 2
    assert result["message_count"] == 3
    assert [message["id"] for message in result["messages"]] == [
        "msg-1",
        "msg-2",
        "msg-3",
    ]
