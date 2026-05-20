"""
Integration tests for Outlook-facing API routes.

These tests verify the FastAPI route wiring for:

    GET /api/v1/integrations/outlook/authorize
    GET /api/v1/integrations/outlook/callback
    GET /api/v1/integrations/outlook/accounts/{microsoft_user_id}/current-user
    GET /api/v1/integrations/outlook/accounts/{microsoft_user_id}/mail-folders
    GET /api/v1/integrations/outlook/accounts/{microsoft_user_id}/messages
    GET /api/v1/integrations/outlook/accounts/{microsoft_user_id}/messages/{message_id}/attachments
"""

from collections.abc import Iterator
from datetime import datetime, timezone
from unittest.mock import patch

import pytest
from fastapi import status
from fastapi.testclient import TestClient

from backend.main import create_app
from backend.services.outlook_api import OutlookApiError
from backend.services.outlook_oauth import OutlookOAuthExchangeError, OutlookTokenSet
from backend.settings import get_settings

OUTLOOK_AUTHORIZE_PATH = "/api/v1/integrations/outlook/authorize"
OUTLOOK_CALLBACK_PATH = "/api/v1/integrations/outlook/callback"
OUTLOOK_CURRENT_USER_PATH_TEMPLATE = (
    "/api/v1/integrations/outlook/accounts/{microsoft_user_id}/current-user"
)
OUTLOOK_MAIL_FOLDERS_PATH_TEMPLATE = (
    "/api/v1/integrations/outlook/accounts/{microsoft_user_id}/mail-folders"
)
OUTLOOK_MESSAGES_PATH_TEMPLATE = (
    "/api/v1/integrations/outlook/accounts/{microsoft_user_id}/messages"
)
OUTLOOK_ATTACHMENTS_PATH_TEMPLATE = (
    "/api/v1/integrations/outlook/accounts/{microsoft_user_id}/messages/{message_id}/attachments"
)


@pytest.fixture(autouse=True)
def clear_settings_cache() -> Iterator[None]:
    """Clear cached settings before and after each test."""

    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def create_test_client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    """
    Create a test client with safe empty Outlook OAuth settings by default.
    """

    monkeypatch.setenv("MICROSOFT_CLIENT_ID", "")
    monkeypatch.setenv("MICROSOFT_CLIENT_SECRET", "")
    monkeypatch.setenv("MICROSOFT_REDIRECT_URI", "")

    return TestClient(create_app())


def test_outlook_authorize_returns_url_when_minimum_oauth_settings_exist(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify that the authorize route returns a usable Microsoft approval URL."""

    monkeypatch.setenv("MICROSOFT_CLIENT_ID", "microsoft-client-id")
    monkeypatch.setenv(
        "MICROSOFT_REDIRECT_URI",
        "https://example.com/api/v1/integrations/outlook/callback",
    )

    client = TestClient(create_app())
    response = client.get(f"{OUTLOOK_AUTHORIZE_PATH}?state=connect-outlook-dev")

    assert response.status_code == status.HTTP_200_OK
    payload = response.json()
    assert payload["oauth_configuration_ready"] is True
    assert payload["state"] == "connect-outlook-dev"
    assert payload["authorization_url"].startswith(
        "https://login.microsoftonline.com/organizations/oauth2/v2.0/authorize?"
    )


def test_outlook_callback_exchanges_and_saves_connection_successfully(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify that the callback route exchanges the code and saves the token set."""

    monkeypatch.setenv("MICROSOFT_CLIENT_ID", "microsoft-client-id")
    monkeypatch.setenv("MICROSOFT_CLIENT_SECRET", "microsoft-client-secret")
    monkeypatch.setenv(
        "MICROSOFT_REDIRECT_URI",
        "http://127.0.0.1:8000/api/v1/integrations/outlook/callback",
    )

    client = TestClient(create_app())

    fake_token_set = OutlookTokenSet(
        access_token="microsoft-access-token",
        token_type="Bearer",
        expires_in=3600,
        refresh_token="microsoft-refresh-token",
        scope="offline_access User.Read Mail.Read Mail.Read.Shared",
        microsoft_user_id="aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
        tenant_id="ffffffff-1111-2222-3333-444444444444",
        user_principal_name="tom@example.com",
        raw_payload={"access_token": "microsoft-access-token"},
    )
    fake_saved_connection = {
        "id": "11111111-1111-1111-1111-111111111111",
        "microsoft_user_id": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
        "tenant_id": "ffffffff-1111-2222-3333-444444444444",
        "user_principal_name": "tom@example.com",
    }

    with patch(
        "backend.api.v1.integrations.exchange_outlook_authorization_code",
        return_value=fake_token_set,
    ) as mock_exchange:
        with patch(
            "backend.api.v1.integrations.save_outlook_oauth_connection",
            return_value=fake_saved_connection,
        ) as mock_save:
            response = client.get(
                f"{OUTLOOK_CALLBACK_PATH}?code=test-outlook-code&state=connect-dev"
            )

    assert response.status_code == status.HTTP_200_OK
    payload = response.json()
    assert payload["status"] == "connected"
    assert payload["microsoft_user_id"] == "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
    assert payload["user_principal_name"] == "tom@example.com"
    mock_exchange.assert_called_once_with(code="test-outlook-code")
    mock_save.assert_called_once_with(fake_token_set)


def test_outlook_callback_resolves_current_user_when_token_payload_lacks_oid(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    Verify that the callback falls back to Graph `/me` when Microsoft does not
    include a usable user identifier in the token response itself.
    """

    monkeypatch.setenv("MICROSOFT_CLIENT_ID", "microsoft-client-id")
    monkeypatch.setenv("MICROSOFT_CLIENT_SECRET", "microsoft-client-secret")
    monkeypatch.setenv(
        "MICROSOFT_REDIRECT_URI",
        "http://127.0.0.1:8000/api/v1/integrations/outlook/callback",
    )

    client = TestClient(create_app())

    token_without_oid = OutlookTokenSet(
        access_token="microsoft-access-token",
        token_type="Bearer",
        expires_in=3600,
        refresh_token="microsoft-refresh-token",
        scope="offline_access User.Read Mail.Read Mail.Read.Shared",
        microsoft_user_id=None,
        tenant_id="ffffffff-1111-2222-3333-444444444444",
        user_principal_name=None,
        raw_payload={"access_token": "microsoft-access-token"},
    )
    fake_saved_connection = {
        "id": "11111111-1111-1111-1111-111111111111",
        "microsoft_user_id": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
        "tenant_id": "ffffffff-1111-2222-3333-444444444444",
        "user_principal_name": "tom@example.com",
    }

    with patch(
        "backend.api.v1.integrations.exchange_outlook_authorization_code",
        return_value=token_without_oid,
    ) as mock_exchange:
        with patch(
            "backend.api.v1.integrations.fetch_outlook_current_user",
            return_value={
                "user": {
                    "id": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
                    "userPrincipalName": "tom@example.com",
                    "mail": "tom@example.com",
                },
                "raw_payload": {},
                "endpoint_url": "https://graph.microsoft.com/v1.0/me",
            },
        ) as mock_fetch_current_user:
            with patch(
                "backend.api.v1.integrations.save_outlook_oauth_connection",
                return_value=fake_saved_connection,
            ) as mock_save:
                response = client.get(
                    f"{OUTLOOK_CALLBACK_PATH}?code=test-outlook-code&state=connect-dev"
                )

    assert response.status_code == status.HTTP_200_OK
    payload = response.json()
    assert payload["status"] == "connected"
    assert payload["microsoft_user_id"] == "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
    assert payload["user_principal_name"] == "tom@example.com"
    mock_exchange.assert_called_once_with(code="test-outlook-code")
    mock_fetch_current_user.assert_called_once_with(
        access_token="microsoft-access-token"
    )
    saved_token_set = mock_save.call_args.args[0]
    assert saved_token_set.microsoft_user_id == "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
    assert saved_token_set.user_principal_name == "tom@example.com"


def test_outlook_callback_returns_bad_gateway_when_token_exchange_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify that a token-exchange failure becomes a clear API error."""

    monkeypatch.setenv("MICROSOFT_CLIENT_ID", "microsoft-client-id")
    monkeypatch.setenv("MICROSOFT_CLIENT_SECRET", "microsoft-client-secret")
    monkeypatch.setenv(
        "MICROSOFT_REDIRECT_URI",
        "http://127.0.0.1:8000/api/v1/integrations/outlook/callback",
    )

    client = TestClient(create_app())

    with patch(
        "backend.api.v1.integrations.exchange_outlook_authorization_code",
        side_effect=OutlookOAuthExchangeError(
            "Outlook token exchange failed.",
            status_code=400,
            provider_error="invalid_grant",
            provider_error_description="Authorization code has expired.",
        ),
    ):
        response = client.get(
            f"{OUTLOOK_CALLBACK_PATH}?code=expired-code&state=connect-dev"
        )

    assert response.status_code == status.HTTP_502_BAD_GATEWAY
    payload = response.json()
    assert payload["error"]["code"] == "approval_required"
    assert payload["error"]["message"] == "Outlook token exchange failed."


def test_outlook_current_user_returns_user_successfully() -> None:
    """Verify that the current-user route returns one user payload cleanly."""

    client = TestClient(create_app())

    fake_connection = {
        "microsoft_user_id": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
        "access_token": "microsoft-access-token",
        "refresh_token": "microsoft-refresh-token",
        "obtained_at": datetime.now(timezone.utc),
        "expires_in_seconds": 3600,
    }
    fake_user = {
        "user": {
            "id": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
            "displayName": "Tom Example",
            "mail": "tom@example.com",
        },
        "raw_payload": {},
        "endpoint_url": "https://graph.microsoft.com/v1.0/me",
    }

    with patch(
        "backend.api.v1.integrations.get_outlook_oauth_connection",
        return_value=fake_connection,
    ):
        with patch(
            "backend.api.v1.integrations.fetch_outlook_current_user",
            return_value=fake_user,
        ) as mock_fetch_user:
            response = client.get(
                OUTLOOK_CURRENT_USER_PATH_TEMPLATE.format(
                    microsoft_user_id="aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
                )
            )

    assert response.status_code == status.HTTP_200_OK
    payload = response.json()
    assert payload["microsoft_user_id"] == "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
    assert payload["user"]["mail"] == "tom@example.com"
    mock_fetch_user.assert_called_once_with(access_token="microsoft-access-token")


def test_outlook_mail_folders_returns_preview_successfully() -> None:
    """Verify that the mail-folders route returns a first-page folder preview."""

    client = TestClient(create_app())

    fake_connection = {
        "microsoft_user_id": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
        "access_token": "microsoft-access-token",
        "refresh_token": "microsoft-refresh-token",
        "obtained_at": datetime.now(timezone.utc),
        "expires_in_seconds": 3600,
    }
    fake_folders = {
        "mailbox": "recruitment@example.com",
        "folder_count": 2,
        "folders": [
            {"id": "Inbox", "displayName": "Inbox"},
            {"id": "Archive", "displayName": "Archive"},
        ],
        "raw_payload": {},
        "endpoint_url": "https://graph.microsoft.com/v1.0/users/recruitment@example.com/mailFolders?$top=25",
    }

    with patch(
        "backend.api.v1.integrations.get_outlook_oauth_connection",
        return_value=fake_connection,
    ):
        with patch(
            "backend.api.v1.integrations.fetch_outlook_mail_folders",
            return_value=fake_folders,
        ) as mock_fetch_folders:
            response = client.get(
                OUTLOOK_MAIL_FOLDERS_PATH_TEMPLATE.format(
                    microsoft_user_id="aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
                )
                + "?mailbox=recruitment@example.com"
            )

    assert response.status_code == status.HTTP_200_OK
    payload = response.json()
    assert payload["folder_count"] == 2
    assert payload["mailbox"] == "recruitment@example.com"
    mock_fetch_folders.assert_called_once_with(
        access_token="microsoft-access-token",
        mailbox="recruitment@example.com",
        limit=25,
    )


def test_outlook_messages_returns_preview_successfully() -> None:
    """Verify that the messages route returns a first-page message preview."""

    client = TestClient(create_app())

    fake_connection = {
        "microsoft_user_id": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
        "access_token": "microsoft-access-token",
        "refresh_token": "microsoft-refresh-token",
        "obtained_at": datetime.now(timezone.utc),
        "expires_in_seconds": 3600,
    }
    fake_messages = {
        "mailbox": None,
        "folder_id": "Inbox",
        "message_count": 1,
        "messages": [{"id": "msg-1", "subject": "Candidate CV", "hasAttachments": True}],
        "raw_payload": {},
        "endpoint_url": "https://graph.microsoft.com/v1.0/me/mailFolders/Inbox/messages?$top=25",
    }

    with patch(
        "backend.api.v1.integrations.get_outlook_oauth_connection",
        return_value=fake_connection,
    ):
        with patch(
            "backend.api.v1.integrations.fetch_outlook_messages",
            return_value=fake_messages,
        ) as mock_fetch_messages:
            response = client.get(
                OUTLOOK_MESSAGES_PATH_TEMPLATE.format(
                    microsoft_user_id="aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
                )
                + "?folder_id=Inbox"
            )

    assert response.status_code == status.HTTP_200_OK
    payload = response.json()
    assert payload["message_count"] == 1
    assert payload["folder_id"] == "Inbox"
    mock_fetch_messages.assert_called_once_with(
        access_token="microsoft-access-token",
        folder_id="Inbox",
        mailbox=None,
        limit=25,
    )


def test_outlook_attachments_returns_preview_successfully() -> None:
    """Verify that the attachments route returns a first-page attachment preview."""

    client = TestClient(create_app())

    fake_connection = {
        "microsoft_user_id": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
        "access_token": "microsoft-access-token",
        "refresh_token": "microsoft-refresh-token",
        "obtained_at": datetime.now(timezone.utc),
        "expires_in_seconds": 3600,
    }
    fake_attachments = {
        "mailbox": None,
        "message_id": "msg-1",
        "attachment_count": 1,
        "attachments": [{"id": "att-1", "name": "cv.pdf", "@odata.type": "#microsoft.graph.fileAttachment"}],
        "raw_payload": {},
        "endpoint_url": "https://graph.microsoft.com/v1.0/me/messages/msg-1/attachments?$top=50",
    }

    with patch(
        "backend.api.v1.integrations.get_outlook_oauth_connection",
        return_value=fake_connection,
    ):
        with patch(
            "backend.api.v1.integrations.fetch_outlook_message_attachments",
            return_value=fake_attachments,
        ) as mock_fetch_attachments:
            response = client.get(
                OUTLOOK_ATTACHMENTS_PATH_TEMPLATE.format(
                    microsoft_user_id="aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
                    message_id="msg-1",
                )
            )

    assert response.status_code == status.HTTP_200_OK
    payload = response.json()
    assert payload["attachment_count"] == 1
    assert payload["message_id"] == "msg-1"
    mock_fetch_attachments.assert_called_once_with(
        access_token="microsoft-access-token",
        message_id="msg-1",
        mailbox=None,
        limit=50,
    )


def test_outlook_messages_returns_bad_gateway_for_provider_failure() -> None:
    """Verify that a Graph read failure becomes a clear API error."""

    client = TestClient(create_app())

    fake_connection = {
        "microsoft_user_id": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
        "access_token": "microsoft-access-token",
        "refresh_token": "microsoft-refresh-token",
        "obtained_at": datetime.now(timezone.utc),
        "expires_in_seconds": 3600,
    }

    with patch(
        "backend.api.v1.integrations.get_outlook_oauth_connection",
        return_value=fake_connection,
    ):
        with patch(
            "backend.api.v1.integrations.fetch_outlook_messages",
            side_effect=OutlookApiError(
                "Outlook message-list read failed.",
                status_code=403,
                endpoint_url="https://graph.microsoft.com/v1.0/me/mailFolders/Inbox/messages",
            ),
        ):
            response = client.get(
                OUTLOOK_MESSAGES_PATH_TEMPLATE.format(
                    microsoft_user_id="aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
                )
                + "?folder_id=Inbox"
            )

    assert response.status_code == status.HTTP_502_BAD_GATEWAY
    payload = response.json()
    assert payload["error"]["message"] == "Outlook message-list read failed."
