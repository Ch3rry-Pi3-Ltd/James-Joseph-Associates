"""
Microsoft Graph mail helper functions for the intelligence backend.

This module contains the first authenticated Outlook / Microsoft Graph read
helpers used after OAuth succeeds.

It gives the rest of the repository a stable way to talk about:

- reading the connected Microsoft account profile
- listing mail folders from the signed-in or delegated mailbox
- listing messages from one mail folder
- listing attachments on one message
- downloading one file attachment transiently for later extraction work

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
    downloaded_attachment = download_outlook_message_file_attachment(
        access_token="...",
        message_id="AAMkAGI2...",
        attachment_id="AAMkAGI2...AAABEgAQ...",
    )

In plain language:

- this module answers the questions:

    "Can the backend read the connected Outlook account?"
    "Can the backend inspect mail folders and CV attachments through Graph?"

- it does not define API routes
- it does not store tokens
- it only performs authenticated Microsoft Graph reads
"""

from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlencode
import base64

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

    # Keep the first slice intentionally to one page so we can prove mailbox
    # access and inspect source shape before adding cursor / pagination state.
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


def fetch_outlook_child_mail_folders(
    *,
    access_token: str,
    parent_folder_id: str,
    mailbox: str | None = None,
    limit: int = 100,
) -> dict[str, Any]:
    """
    Fetch a first-page preview of child folders under one Outlook folder.

    Parameters
    ----------
    parent_folder_id : str
        Parent mail folder identifier whose direct child folders should be
        listed.

    mailbox : str | None
        Optional mailbox identifier to read instead of the signed-in user's
        own mailbox. This supports shared or delegated mailbox reads when the
        delegated scopes have been approved.

    Example
    -------
    A call such as:

        fetch_outlook_child_mail_folders(
            access_token="...",
            parent_folder_id="AAMkAGI2...",
            mailbox="recruitment@example.com",
            limit=100,
        )

    reads the next folder level through Graph.

    In practice, this is the helper used when a human-readable path such as
    `Inbox > # ADV-CVR > ### DOMINIQUE FOLDER > tw394` needs to be resolved
    one level at a time.
    """

    if (
        not isinstance(parent_folder_id, str)
        or parent_folder_id.strip() == ""
    ):
        raise OutlookApiError("Outlook parent_folder_id cannot be empty.")

    # Keep the first path-resolution slice intentionally to one page. The goal
    # here is operational folder discovery, not full recursive mailbox sync.
    query = urlencode({"$top": limit})
    endpoint_url = (
        f"{_mailbox_base_path(mailbox=mailbox)}/mailFolders/"
        f"{parent_folder_id}/childFolders?{query}"
    )
    payload = _get_from_graph(
        endpoint_url=endpoint_url,
        access_token=access_token,
        provider_failure_message="Outlook child-folder read failed.",
    )

    folders = payload.get("value")
    if not isinstance(folders, list):
        folders = []

    return {
        "mailbox": mailbox,
        "parent_folder_id": parent_folder_id,
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
    received_from: datetime | None = None,
    received_to: datetime | None = None,
) -> dict[str, Any]:
    """
    Fetch the full bounded message slice from one Outlook mail folder.

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

    if limit <= 0:
        raise OutlookApiError("Outlook message page size must be positive.")

    if (
        isinstance(received_from, datetime)
        and isinstance(received_to, datetime)
        and received_from > received_to
    ):
        raise OutlookApiError(
            "Outlook received_from cannot be later than received_to."
        )

    # Request only the message fields needed for early CV-ingestion discovery.
    # `limit` here is the Graph page size, not the total number of messages we
    # are willing to inspect in the bounded date window.
    query_params: dict[str, Any] = {
        "$top": limit,
        "$select": (
            "id,subject,receivedDateTime,from,hasAttachments,"
            "internetMessageId,conversationId"
        ),
        "$orderby": "receivedDateTime desc",
    }
    filter_parts: list[str] = []
    if isinstance(received_from, datetime):
        filter_parts.append(
            f"receivedDateTime ge {_format_graph_datetime(received_from)}"
        )
    if isinstance(received_to, datetime):
        filter_parts.append(
            f"receivedDateTime le {_format_graph_datetime(received_to)}"
        )
    if filter_parts:
        query_params["$filter"] = " and ".join(filter_parts)
    query = urlencode(query_params)
    endpoint_url = (
        f"{_mailbox_base_path(mailbox=mailbox)}/mailFolders/{folder_id}/messages?{query}"
    )

    messages: list[dict[str, Any]] = []
    page_count = 0
    next_endpoint_url: str | None = endpoint_url
    seen_next_links: set[str] = set()
    last_payload: dict[str, Any] = {}

    while isinstance(next_endpoint_url, str) and next_endpoint_url.strip() != "":
        if next_endpoint_url in seen_next_links:
            raise OutlookApiError(
                "Outlook message-list pagination returned a repeated nextLink.",
                endpoint_url=next_endpoint_url,
            )

        seen_next_links.add(next_endpoint_url)
        payload = _get_from_graph(
            endpoint_url=next_endpoint_url,
            access_token=access_token,
            provider_failure_message="Outlook message-list read failed.",
        )
        last_payload = payload
        page_count += 1

        page_messages = payload.get("value")
        if isinstance(page_messages, list):
            messages.extend(
                message for message in page_messages if isinstance(message, dict)
            )

        raw_next_link = payload.get("@odata.nextLink")
        next_endpoint_url = (
            raw_next_link.strip()
            if isinstance(raw_next_link, str) and raw_next_link.strip() != ""
            else None
        )

    return {
        "mailbox": mailbox,
        "folder_id": folder_id,
        "message_page_size": limit,
        "page_count": page_count,
        "received_from": _format_graph_datetime(received_from)
        if isinstance(received_from, datetime)
        else None,
        "received_to": _format_graph_datetime(received_to)
        if isinstance(received_to, datetime)
        else None,
        "message_count": len(messages),
        "messages": messages,
        "raw_payload": last_payload,
        "endpoint_url": endpoint_url,
    }


def _format_graph_datetime(value: datetime) -> str:
    """
    Format one Python datetime into a Graph-safe ISO-8601 timestamp.
    """

    if value.tzinfo is None:
        return value.isoformat(timespec="seconds") + "Z"

    normalized_value = value.astimezone(timezone.utc)
    return normalized_value.isoformat(timespec="seconds").replace("+00:00", "Z")


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

    # Like the folder and message reads, this attachment read is intentionally
    # a preview. The goal of the first slice is to prove delegated mailbox
    # access and attachment visibility before we add full download workflows.
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


def download_outlook_message_file_attachment(
    *,
    access_token: str,
    message_id: str,
    attachment_id: str,
    mailbox: str | None = None,
) -> dict[str, Any]:
    """
    Download one Outlook file attachment transiently into memory.

    Parameters
    ----------
    access_token : str
        Delegated Microsoft Graph access token to use for the read.

    message_id : str
        Outlook message identifier that owns the attachment.

    attachment_id : str
        Outlook attachment identifier to fetch.

    mailbox : str | None
        Optional mailbox identifier to read instead of the signed-in user's
        own mailbox. This supports shared or delegated mailbox reads when the
        delegated scopes have been approved.

    Returns
    -------
    dict[str, Any]
        Normalized transient file download containing:

        - `mailbox`
        - `message_id`
        - `attachment_id`
        - `file_name`
        - `content_type`
        - `content_bytes`
        - `attachment_metadata`
        - `endpoint_url`

    Raises
    ------
    OutlookApiError
        If Graph rejects the request, returns malformed attachment data, or
        the attachment is not a file attachment.

    Notes
    -----
    - This helper is intentionally narrow.
    - It only supports `#microsoft.graph.fileAttachment`.
    - That is the right first slice for CV ingestion because we care about
      real attached files, not item attachments or cloud references yet.

    Example
    -------
    A call such as:

        download_outlook_message_file_attachment(
            access_token="...",
            message_id="AAMkAGI2...",
            attachment_id="AAMkAGI2...AAABEgAQ...",
            mailbox=None,
        )

    returns the raw file bytes plus the small amount of metadata needed for
    later text extraction and provenance handling.

    For advert-response CV ingestion, this is the step that turns:

    - one Graph message ID
    - one Graph attachment ID

    into the transient file payload consumed by the existing resume-text
    extraction path.
    """

    if not isinstance(message_id, str) or message_id.strip() == "":
        raise OutlookApiError("Outlook message_id cannot be empty.")

    if not isinstance(attachment_id, str) or attachment_id.strip() == "":
        raise OutlookApiError("Outlook attachment_id cannot be empty.")

    # Fetch the attachment metadata object first because Graph already gives us
    # the attachment name, media type, and base64 payload for file
    # attachments.
    #
    # Keeping the first implementation on that route avoids introducing a
    # second `$value` transport path before we know it is needed.
    endpoint_url = (
        f"{_mailbox_base_path(mailbox=mailbox)}/messages/{message_id}"
        f"/attachments/{attachment_id}"
    )
    payload = _get_from_graph(
        endpoint_url=endpoint_url,
        access_token=access_token,
        provider_failure_message="Outlook attachment download failed.",
    )

    attachment_type = payload.get("@odata.type")
    if attachment_type != "#microsoft.graph.fileAttachment":
        raise OutlookApiError(
            "Outlook attachment download currently supports only file attachments.",
            endpoint_url=endpoint_url,
            response_body=payload,
        )

    raw_content_bytes = payload.get("contentBytes")
    if not isinstance(raw_content_bytes, str) or raw_content_bytes.strip() == "":
        raise OutlookApiError(
            "Outlook file attachment payload did not include usable content bytes.",
            endpoint_url=endpoint_url,
            response_body=payload,
        )

    try:
        content_bytes = base64.b64decode(raw_content_bytes, validate=True)
    except (ValueError, TypeError) as exc:
        raise OutlookApiError(
            "Outlook file attachment payload contained invalid base64 content.",
            endpoint_url=endpoint_url,
            response_body=payload,
        ) from exc

    # Keep the file-name normalization explicit here instead of silently
    # passing through blank provider values.
    #
    # Downstream extraction and provenance code can work without a file name,
    # but an empty-string name is more misleading than a deliberate `None`.
    raw_name = payload.get("name")
    file_name = (
        raw_name
        if isinstance(raw_name, str) and raw_name.strip() != ""
        else None
    )
    content_type = payload.get("contentType")

    return {
        "mailbox": mailbox,
        "message_id": message_id,
        "attachment_id": attachment_id,
        "file_name": file_name,
        "content_type": content_type,
        "content_bytes": content_bytes,
        "attachment_metadata": payload,
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

    Parameters
    ----------
    endpoint_url : str
        Fully assembled Microsoft Graph endpoint URL to call.

    access_token : str
        Delegated bearer token previously obtained through Outlook OAuth.

    provider_failure_message : str
        Route-safe message to surface if Graph rejects the request.

    Returns
    -------
    dict[str, Any]
        Decoded JSON object returned by Microsoft Graph.

    Notes
    -----
    - This helper owns the repetitive HTTP pieces shared by every first-pass
      Outlook read:
        - bearer-token header
        - JSON accept header
        - standard timeout
        - provider error normalization
    - The higher-level helpers stay focused on mailbox semantics rather than
      repeating the raw HTTP mechanics.

    Example
    -------
    This helper is used internally by calls such as:

        _get_from_graph(
            endpoint_url="https://graph.microsoft.com/v1.0/me",
            access_token="...",
            provider_failure_message="Outlook current-user read failed.",
        )
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
    "download_outlook_message_file_attachment",
    "fetch_outlook_child_mail_folders",
    "fetch_outlook_current_user",
    "fetch_outlook_mail_folders",
    "fetch_outlook_message_attachments",
    "fetch_outlook_messages",
]
