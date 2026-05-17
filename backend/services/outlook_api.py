"""
Microsoft Graph mail helper functions for the intelligence backend.

This module contains the first authenticated Outlook / Microsoft Graph read
helpers used after OAuth succeeds.

It gives the rest of the repository a stable way to talk about:

- reading the connected Microsoft account profile
- listing mail folders from the signed-in or delegated mailbox
- listing messages from one mail folder
- listing attachments on one message

Example
-------
Typical usage in the rest of the backend looks like:

    current_user = fetch_outlook_current_user(access_token="...")
    folders = fetch_outlook_mail_folders(access_token="...", mailbox=None)
    messages = fetch_outlook_messages(
        access_token="...",
        folder_id="inbox",
        mailbox="recruitment@example.com",
    )

In plain language:

- this module answers the questions:

    "Can the backend read the connected Outlook account?"
    "Can the backend inspect mail folders and CV attachments through Graph?"

- it does not define API routes
- it does not store tokens
- it only performs authenticated Microsoft Graph reads
"""

from typing import Any
from urllib.parse import urlencode

import httpx

from backend.settings import get_settings

GRAPH_BASE_URL = "https://graph.microsoft.com/v1.0"
GRAPH_ME_URL = f"{GRAPH_BASE_URL}/me"


class OutlookApiError(RuntimeError):
    """
    Raised when the backend cannot complete an authenticated Microsoft Graph
    read safely.

    Example
    -------
    Route handlers may inspect:

        error.status_code
        error.endpoint_url

    to distinguish between authorization failures and malformed upstream
    responses.
    """

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        endpoint_url: str | None = None,
        response_body: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.endpoint_url = endpoint_url
        self.response_body = response_body

    def __str__(self) -> str:
        """Return the human-readable error message."""

        return self.message


def fetch_outlook_current_user(*, access_token: str) -> dict[str, Any]:
    """
    Fetch the currently connected Microsoft user profile.

    Example
    -------
    A successful result includes the decoded current-user object under the
    `user` key.
    """

    payload = _get_from_graph(
        endpoint_url=GRAPH_ME_URL,
        access_token=access_token,
        provider_failure_message="Outlook current-user read failed.",
    )

    return {
        "user": payload,
        "endpoint_url": GRAPH_ME_URL,
        "raw_payload": payload,
    }


def fetch_outlook_mail_folders(
    *,
    access_token: str,
    mailbox: str | None = None,
    limit: int = 25,
) -> dict[str, Any]:
    """
    Fetch a first-page preview of Outlook mail folders.

    Parameters
    ----------
    mailbox : str | None
        Optional mailbox identifier to read instead of the signed-in user's
        own mailbox. This supports shared or delegated mailbox reads when the
        delegated scopes have been approved.

    Example
    -------
    A call such as:

        fetch_outlook_mail_folders(
            access_token="...",
            mailbox="recruitment@example.com",
            limit=25,
        )

    reads folders from that mailbox through Graph.
    """

    query = urlencode({"$top": limit})
    endpoint_url = f"{_mailbox_base_path(mailbox=mailbox)}/mailFolders?{query}"
    payload = _get_from_graph(
        endpoint_url=endpoint_url,
        access_token=access_token,
        provider_failure_message="Outlook mail-folder read failed.",
    )

    folders = payload.get("value")
    if not isinstance(folders, list):
        folders = []

    return {
        "mailbox": mailbox,
        "folder_count": len(folders),
        "folders": folders,
        "raw_payload": payload,
        "endpoint_url": endpoint_url,
    }


def fetch_outlook_messages(
    *,
    access_token: str,
    folder_id: str,
    mailbox: str | None = None,
    limit: int = 25,
) -> dict[str, Any]:
    """
    Fetch a first-page preview of messages in one Outlook mail folder.

    Example
    -------
    A call such as:

        fetch_outlook_messages(
            access_token="...",
            folder_id="AAMkAGI2...",
            mailbox=None,
        )

    returns a first page of folder messages.
    """

    if not isinstance(folder_id, str) or folder_id.strip() == "":
        raise OutlookApiError("Outlook folder_id cannot be empty.")

    query = urlencode(
        {
            "$top": limit,
            "$select": (
                "id,subject,receivedDateTime,from,hasAttachments,"
                "internetMessageId,conversationId"
            ),
        }
    )
    endpoint_url = (
        f"{_mailbox_base_path(mailbox=mailbox)}/mailFolders/{folder_id}/messages?{query}"
    )

    payload = _get_from_graph(
        endpoint_url=endpoint_url,
        access_token=access_token,
        provider_failure_message="Outlook message-list read failed.",
    )

    messages = payload.get("value")
    if not isinstance(messages, list):
        messages = []

    return {
        "mailbox": mailbox,
        "folder_id": folder_id,
        "message_count": len(messages),
        "messages": messages,
        "raw_payload": payload,
        "endpoint_url": endpoint_url,
    }


def fetch_outlook_message_attachments(
    *,
    access_token: str,
    message_id: str,
    mailbox: str | None = None,
    limit: int = 50,
) -> dict[str, Any]:
    """
    Fetch a first-page preview of attachments on one Outlook message.

    Example
    -------
    A call such as:

        fetch_outlook_message_attachments(
            access_token="...",
            message_id="AAMkAGI2...",
            mailbox="recruitment@example.com",
        )

    returns the attachment metadata for that message.
    """

    if not isinstance(message_id, str) or message_id.strip() == "":
        raise OutlookApiError("Outlook message_id cannot be empty.")

    query = urlencode({"$top": limit})
    endpoint_url = (
        f"{_mailbox_base_path(mailbox=mailbox)}/messages/{message_id}/attachments?{query}"
    )
    payload = _get_from_graph(
        endpoint_url=endpoint_url,
        access_token=access_token,
        provider_failure_message="Outlook attachment-list read failed.",
    )

    attachments = payload.get("value")
    if not isinstance(attachments, list):
        attachments = []

    return {
        "mailbox": mailbox,
        "message_id": message_id,
        "attachment_count": len(attachments),
        "attachments": attachments,
        "raw_payload": payload,
        "endpoint_url": endpoint_url,
    }


def _mailbox_base_path(*, mailbox: str | None) -> str:
    """
    Return the Graph mailbox base path for the signed-in or delegated mailbox.

    Example
    -------
    If `mailbox` is blank, this helper returns:

        https://graph.microsoft.com/v1.0/me

    If `mailbox` is `tom@example.com`, it returns:

        https://graph.microsoft.com/v1.0/users/tom@example.com
    """

    if isinstance(mailbox, str) and mailbox.strip() != "":
        return f"{GRAPH_BASE_URL}/users/{mailbox.strip()}"

    return GRAPH_ME_URL


def _get_from_graph(
    *,
    endpoint_url: str,
    access_token: str,
    provider_failure_message: str,
) -> dict[str, Any]:
    """
    Send one authenticated GET request to Microsoft Graph and decode the
    response.
    """

    if not isinstance(access_token, str) or access_token.strip() == "":
        raise OutlookApiError("Outlook API access token cannot be empty.")

    settings = get_settings()

    try:
        response = httpx.get(
            endpoint_url,
            headers={
                "Authorization": f"Bearer {access_token}",
                "Accept": "application/json",
            },
            timeout=settings.llm_timeout_seconds,
        )
    except httpx.HTTPError as exc:
        raise OutlookApiError(
            "Could not reach the Microsoft Graph API endpoint.",
            endpoint_url=endpoint_url,
        ) from exc

    response_payload = _decode_graph_json_response(response)

    if response.status_code >= 400:
        raise OutlookApiError(
            provider_failure_message,
            status_code=response.status_code,
            endpoint_url=endpoint_url,
            response_body=response_payload,
        )

    return response_payload


def _decode_graph_json_response(response: httpx.Response) -> dict[str, Any]:
    """
    Decode a Microsoft Graph response body into a dictionary.

    Example
    -------
    If Graph returns valid JSON, this helper returns that decoded object.
    """

    try:
        decoded = response.json()
    except ValueError:
        return {}

    if isinstance(decoded, dict):
        return decoded

    return {}


__all__ = [
    "GRAPH_BASE_URL",
    "GRAPH_ME_URL",
    "OutlookApiError",
    "fetch_outlook_current_user",
    "fetch_outlook_mail_folders",
    "fetch_outlook_message_attachments",
    "fetch_outlook_messages",
]
