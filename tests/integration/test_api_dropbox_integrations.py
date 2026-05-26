"""
Integration tests for Dropbox-facing API routes.

These tests verify the FastAPI route wiring for:

    GET /api/v1/integrations/dropbox/authorize
    GET /api/v1/integrations/dropbox/callback
    GET /api/v1/integrations/dropbox/accounts/{dropbox_account_id}/current-account
    GET /api/v1/integrations/dropbox/accounts/{dropbox_account_id}/files/list-folder
    GET /api/v1/integrations/dropbox/accounts/{dropbox_account_id}/files/zip-members-preview

The important question is:

    "Does the backend expose real Dropbox integration routes that behave
    clearly during setup and first authenticated reads?"
"""

from collections.abc import Iterator
from datetime import datetime, timedelta, timezone
from io import BytesIO
from unittest.mock import MagicMock, patch
from zipfile import ZipFile

import pytest
from fastapi import status
from fastapi.testclient import TestClient

from backend.main import create_app
from backend.services.dropbox_api import DropboxApiError
from backend.services.dropbox_oauth import (
    DEFAULT_DROPBOX_SCOPE,
    DropboxOAuthExchangeError,
    DropboxTokenSet,
)
from backend.settings import get_settings

DROPBOX_AUTHORIZE_PATH = "/api/v1/integrations/dropbox/authorize"
DROPBOX_CALLBACK_PATH = "/api/v1/integrations/dropbox/callback"
DROPBOX_CURRENT_ACCOUNT_PATH_TEMPLATE = (
    "/api/v1/integrations/dropbox/accounts/{dropbox_account_id}/current-account"
)
DROPBOX_LIST_FOLDER_PATH_TEMPLATE = (
    "/api/v1/integrations/dropbox/accounts/{dropbox_account_id}/files/list-folder"
)
DROPBOX_ZIP_MEMBERS_PREVIEW_PATH_TEMPLATE = (
    "/api/v1/integrations/dropbox/accounts/{dropbox_account_id}/files/zip-members-preview"
)
DROPBOX_ZIP_JSON_MEMBER_PREVIEW_PATH_TEMPLATE = (
    "/api/v1/integrations/dropbox/accounts/{dropbox_account_id}/files/zip-json-member-preview"
)


@pytest.fixture(autouse=True)
def clear_settings_cache() -> Iterator[None]:
    """
    Clear cached settings before and after each test.

    Example
    -------
    These route tests override environment variables through `monkeypatch`, so
    the cached settings object must be cleared between tests to ensure each
    case sees the values it configured.
    """

    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def create_test_client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    """
    Create a test client with safe empty Dropbox OAuth settings by default.

    Example
    -------
    This helper deliberately blanks:

    - `DROPBOX_CLIENT_ID`
    - `DROPBOX_CLIENT_SECRET`
    - `DROPBOX_REDIRECT_URI`

    so tests start from an explicit "not configured" baseline unless they opt
    into real-looking settings values.
    """

    monkeypatch.setenv("DROPBOX_CLIENT_ID", "")
    monkeypatch.setenv("DROPBOX_CLIENT_SECRET", "")
    monkeypatch.setenv("DROPBOX_REDIRECT_URI", "")

    return TestClient(create_app())


def test_dropbox_authorize_returns_url_when_minimum_oauth_settings_exist(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    Verify that the authorize route returns a usable Dropbox approval URL.

    Example
    -------
    This simulates the setup state where the backend has:

    - a Dropbox app key
    - a Dropbox redirect URI

    and confirms the route responds with a concrete approval URL to send to
    Tom.
    """

    monkeypatch.setenv("DROPBOX_CLIENT_ID", "dropbox-client-id")
    monkeypatch.setenv(
        "DROPBOX_REDIRECT_URI",
        "https://example.com/api/v1/integrations/dropbox/callback",
    )

    client = TestClient(create_app())

    response = client.get(f"{DROPBOX_AUTHORIZE_PATH}?state=connect-dropbox-dev")

    assert response.status_code == status.HTTP_200_OK

    payload = response.json()

    assert payload["oauth_configuration_ready"] is True
    assert payload["state"] == "connect-dropbox-dev"
    assert payload["authorization_url"].startswith(
        "https://www.dropbox.com/oauth2/authorize?"
    )
    assert "client_id=dropbox-client-id" in payload["authorization_url"]


def test_dropbox_callback_exchanges_and_saves_connection_successfully(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    Verify that the callback route exchanges the code and saves the returned
    token set successfully.

    Example
    -------
    This is the main happy-path callback test:

    - Dropbox returns a usable authorization code
    - the backend exchanges it
    - the backend saves the normalized token set
    - the route returns a connection-complete response
    """

    monkeypatch.setenv("DROPBOX_CLIENT_ID", "dropbox-client-id")
    monkeypatch.setenv("DROPBOX_CLIENT_SECRET", "dropbox-client-secret")
    monkeypatch.setenv(
        "DROPBOX_REDIRECT_URI",
        "http://127.0.0.1:8000/api/v1/integrations/dropbox/callback",
    )

    client = TestClient(create_app())

    fake_token_set = MagicMock()
    fake_token_set.scope = DEFAULT_DROPBOX_SCOPE
    fake_saved_connection = {
        "id": "11111111-1111-1111-1111-111111111111",
        "dropbox_account_id": "dbid:AAExample",
    }

    with patch(
        "backend.api.v1.integrations.exchange_dropbox_authorization_code",
        return_value=fake_token_set,
    ) as mock_exchange:
        with patch(
            "backend.api.v1.integrations.save_dropbox_oauth_connection",
            return_value=fake_saved_connection,
        ) as mock_save:
            response = client.get(
                f"{DROPBOX_CALLBACK_PATH}?code=test-dropbox-code&state=connect-dev"
            )

    assert response.status_code == status.HTTP_200_OK

    payload = response.json()

    assert payload["status"] == "connected"
    assert payload["message"] == "Dropbox connection completed successfully."
    assert payload["oauth_connection_id"] == "11111111-1111-1111-1111-111111111111"
    assert payload["dropbox_account_id"] == "dbid:AAExample"
    assert payload["requested_scope"] == DEFAULT_DROPBOX_SCOPE
    assert payload["granted_scope"] == DEFAULT_DROPBOX_SCOPE
    assert payload["missing_requested_scopes"] == []
    assert payload["state"] == "connect-dev"

    mock_exchange.assert_called_once_with(code="test-dropbox-code")
    mock_save.assert_called_once_with(fake_token_set)


def test_dropbox_callback_returns_bad_gateway_when_token_exchange_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    Verify that a token-exchange failure becomes a clear API error.

    Example
    -------
    If Dropbox rejects the authorization code, the route should surface that
    as a provider-facing failure rather than pretending the connection was
    completed.
    """

    monkeypatch.setenv("DROPBOX_CLIENT_ID", "dropbox-client-id")
    monkeypatch.setenv("DROPBOX_CLIENT_SECRET", "dropbox-client-secret")
    monkeypatch.setenv(
        "DROPBOX_REDIRECT_URI",
        "http://127.0.0.1:8000/api/v1/integrations/dropbox/callback",
    )

    client = TestClient(create_app())

    with patch(
        "backend.api.v1.integrations.exchange_dropbox_authorization_code",
        side_effect=DropboxOAuthExchangeError(
            "Dropbox token exchange failed.",
            status_code=400,
            provider_error="invalid_grant",
            provider_error_description="Authorization code has expired.",
        ),
    ):
        response = client.get(
            f"{DROPBOX_CALLBACK_PATH}?code=expired-code&state=connect-dev"
        )

    assert response.status_code == status.HTTP_502_BAD_GATEWAY

    payload = response.json()

    assert payload["error"]["code"] == "approval_required"
    assert payload["error"]["message"] == "Dropbox token exchange failed."


def test_dropbox_current_account_returns_account_successfully() -> None:
    """
    Verify that the current-account route returns one account payload from the
    Dropbox API helper.

    Example
    -------
    We simulate:

    - one stored Dropbox OAuth connection
    - one successful `users/get_current_account` helper call

    and confirm the route returns the wrapped account object cleanly.
    """

    client = TestClient(create_app())

    fake_connection = {
        "dropbox_account_id": "dbid:AAExample",
        "access_token": "dropbox-access-token",
        "refresh_token": "dropbox-refresh-token",
        "obtained_at": datetime.now(timezone.utc),
        "expires_in_seconds": 14400,
    }

    fake_account = {
        "account": {
            "account_id": "dbid:AAExample",
            "name": {"display_name": "Tom Example"},
            "email": "tom@example.com",
        },
        "endpoint_url": "https://api.dropboxapi.com/2/users/get_current_account",
        "raw_payload": {},
    }

    with patch(
        "backend.api.v1.integrations.get_dropbox_oauth_connection",
        return_value=fake_connection,
    ):
        with patch(
            "backend.api.v1.integrations.fetch_dropbox_current_account",
            return_value=fake_account,
        ) as mock_fetch_account:
            response = client.get(
                DROPBOX_CURRENT_ACCOUNT_PATH_TEMPLATE.format(
                    dropbox_account_id="dbid:AAExample"
                )
            )

    assert response.status_code == status.HTTP_200_OK

    payload = response.json()

    assert payload["dropbox_account_id"] == "dbid:AAExample"
    assert payload["account"]["account_id"] == "dbid:AAExample"
    assert payload["account"]["email"] == "tom@example.com"

    mock_fetch_account.assert_called_once_with(access_token="dropbox-access-token")


def test_dropbox_list_folder_returns_preview_successfully() -> None:
    """
    Verify that the folder-preview route returns a first-page folder preview
    cleanly.

    Example
    -------
    We simulate a first-page listing containing folders such as `ADV-CVR` and
    confirm the route exposes:

    - the requested path
    - the entry count
    - the cursor
    - the entries themselves
    """

    client = TestClient(create_app())

    fake_connection = {
        "dropbox_account_id": "dbid:AAExample",
        "access_token": "dropbox-access-token",
        "refresh_token": "dropbox-refresh-token",
        "obtained_at": datetime.now(timezone.utc),
        "expires_in_seconds": 14400,
    }

    fake_folder_result = {
        "path": "",
        "entry_count": 2,
        "entries": [
            {".tag": "folder", "name": "ADV-CVR", "path_display": "/ADV-CVR"},
            {".tag": "folder", "name": "Archive", "path_display": "/Archive"},
        ],
        "cursor": "fake-cursor",
        "has_more": False,
        "endpoint_url": "https://api.dropboxapi.com/2/files/list_folder",
        "raw_payload": {},
    }

    with patch(
        "backend.api.v1.integrations.get_dropbox_oauth_connection",
        return_value=fake_connection,
    ):
        with patch(
            "backend.api.v1.integrations.fetch_dropbox_list_folder",
            return_value=fake_folder_result,
        ) as mock_fetch_folder:
            response = client.get(
                DROPBOX_LIST_FOLDER_PATH_TEMPLATE.format(
                    dropbox_account_id="dbid:AAExample"
                )
            )

    assert response.status_code == status.HTTP_200_OK

    payload = response.json()

    assert payload["dropbox_account_id"] == "dbid:AAExample"
    assert payload["path"] == ""
    assert payload["entry_count"] == 2
    assert payload["has_more"] is False
    assert payload["cursor"] == "fake-cursor"
    assert payload["entries"][0]["name"] == "ADV-CVR"

    mock_fetch_folder.assert_called_once_with(
        access_token="dropbox-access-token",
        path="",
        recursive=False,
        limit=25,
    )


def test_dropbox_list_folder_forwards_public_folder_path_query() -> None:
    """
    Verify that the public `folder_path` query parameter is forwarded unchanged
    to the Dropbox folder-read helper.

    Example
    -------
    A request such as:

        GET .../files/list-folder?folder_path=/ADV-CVR

    should pass `/ADV-CVR` into the provider helper rather than the backend API
    route path.
    """

    client = TestClient(create_app())

    fake_connection = {
        "dropbox_account_id": "dbid:AAExample",
        "access_token": "dropbox-access-token",
        "refresh_token": "dropbox-refresh-token",
        "obtained_at": datetime.now(timezone.utc),
        "expires_in_seconds": 14400,
    }

    fake_folder_result = {
        "path": "/ADV-CVR",
        "entry_count": 1,
        "entries": [
            {".tag": "folder", "name": "tw394", "path_display": "/ADV-CVR/tw394"}
        ],
        "cursor": "fake-cursor",
        "has_more": False,
        "endpoint_url": "https://api.dropboxapi.com/2/files/list_folder",
        "raw_payload": {},
    }

    with patch(
        "backend.api.v1.integrations.get_dropbox_oauth_connection",
        return_value=fake_connection,
    ):
        with patch(
            "backend.api.v1.integrations.fetch_dropbox_list_folder",
            return_value=fake_folder_result,
        ) as mock_fetch_folder:
            response = client.get(
                DROPBOX_LIST_FOLDER_PATH_TEMPLATE.format(
                    dropbox_account_id="dbid:AAExample"
                ),
                params={"folder_path": "/ADV-CVR"},
            )

    assert response.status_code == status.HTTP_200_OK
    assert response.json()["path"] == "/ADV-CVR"

    mock_fetch_folder.assert_called_once_with(
        access_token="dropbox-access-token",
        path="/ADV-CVR",
        recursive=False,
        limit=25,
    )


def test_dropbox_list_folder_returns_bad_gateway_when_provider_read_fails() -> None:
    """
    Verify that a provider-side failure during folder listing is surfaced
    clearly through the API route.

    Example
    -------
    If Dropbox rejects the folder read, the route should return a clear 502
    wrapper rather than leaking provider exceptions directly.
    """

    client = TestClient(create_app())

    fake_connection = {
        "dropbox_account_id": "dbid:AAExample",
        "access_token": "dropbox-access-token",
        "refresh_token": "dropbox-refresh-token",
        "obtained_at": datetime.now(timezone.utc),
        "expires_in_seconds": 14400,
    }

    with patch(
        "backend.api.v1.integrations.get_dropbox_oauth_connection",
        return_value=fake_connection,
    ):
        with patch(
            "backend.api.v1.integrations.fetch_dropbox_list_folder",
            side_effect=DropboxApiError(
                "Dropbox folder listing failed.",
                status_code=403,
                endpoint_url="https://api.dropboxapi.com/2/files/list_folder",
            ),
        ):
            response = client.get(
                DROPBOX_LIST_FOLDER_PATH_TEMPLATE.format(
                    dropbox_account_id="dbid:AAExample"
                )
            )

    assert response.status_code == status.HTTP_502_BAD_GATEWAY

    payload = response.json()

    assert payload["error"]["code"] == "internal_error"
    assert payload["error"]["message"] == "Dropbox folder listing failed."


def test_dropbox_list_folder_error_includes_provider_request_and_response_details() -> None:
    """
    Verify that a Dropbox folder-list failure returns the provider request and
    response payload details when they are available.

    Example
    -------
    This keeps the live review route diagnostic enough to fix real Dropbox
    request-shape failures without needing blind guesswork.
    """

    client = TestClient(create_app())

    fake_connection = {
        "dropbox_account_id": "dbid:AAExample",
        "access_token": "dropbox-access-token",
        "refresh_token": "dropbox-refresh-token",
        "obtained_at": datetime.now(timezone.utc),
        "expires_in_seconds": 14400,
    }

    with patch(
        "backend.api.v1.integrations.get_dropbox_oauth_connection",
        return_value=fake_connection,
    ):
        with patch(
            "backend.api.v1.integrations.fetch_dropbox_list_folder",
            side_effect=DropboxApiError(
                "Dropbox folder listing failed.",
                status_code=400,
                endpoint_url="https://api.dropboxapi.com/2/files/list_folder",
                response_body={"error_summary": "path/not_found/..."},
                request_payload={"path": "", "recursive": False, "limit": 25},
            ),
        ):
            response = client.get(
                DROPBOX_LIST_FOLDER_PATH_TEMPLATE.format(
                    dropbox_account_id="dbid:AAExample"
                )
            )

    assert response.status_code == status.HTTP_502_BAD_GATEWAY

    payload = response.json()
    details = payload["error"]["details"]

    assert {"provider_response_body": {"error_summary": "path/not_found/..."}} in details
    assert {
        "provider_request_payload": {"path": "", "recursive": False, "limit": 25}
    } in details


def test_dropbox_zip_members_preview_returns_structural_summary() -> None:
    """
    Verify that the ZIP-preview route returns archive structure without
    exposing raw bytes.

    Example
    -------
    A Recruiterflow-style backup ZIP may contain flat CSV files plus nested
    attachment folders. The route should surface those top-level names and a
    bounded preview of members.
    """

    client = TestClient(create_app())

    fake_connection = {
        "dropbox_account_id": "dbid:AAExample",
        "access_token": "dropbox-access-token",
        "refresh_token": "dropbox-refresh-token",
        "obtained_at": datetime.now(timezone.utc),
        "expires_in_seconds": 14400,
    }

    archive_buffer = BytesIO()
    with ZipFile(archive_buffer, mode="w") as archive:
        archive.writestr("candidates.csv", "id,name\n1,Ada Lovelace\n")
        archive.writestr("attachments/resume.pdf", b"%PDF-1.7 fake pdf bytes")

    fake_download_result = {
        "path": "/exports/Recruiterflow.zip",
        "file_name": "Recruiterflow.zip",
        "content_type": "application/zip",
        "content_bytes": archive_buffer.getvalue(),
        "file_metadata": {"name": "Recruiterflow.zip"},
        "endpoint_url": "https://content.dropboxapi.com/2/files/download",
    }

    with patch(
        "backend.api.v1.integrations.get_dropbox_oauth_connection",
        return_value=fake_connection,
    ):
        with patch(
            "backend.api.v1.integrations.download_dropbox_file",
            return_value=fake_download_result,
        ) as mock_download:
            response = client.get(
                DROPBOX_ZIP_MEMBERS_PREVIEW_PATH_TEMPLATE.format(
                    dropbox_account_id="dbid:AAExample"
                ),
                params={"file_path": "/exports/Recruiterflow.zip", "limit": 10},
            )

    assert response.status_code == status.HTTP_200_OK

    payload = response.json()

    assert payload["dropbox_account_id"] == "dbid:AAExample"
    assert payload["file_path"] == "/exports/Recruiterflow.zip"
    assert payload["file_name"] == "Recruiterflow.zip"
    assert payload["entry_count"] == 2
    assert payload["top_level_entries"] == ["attachments", "candidates.csv"]
    assert payload["preview_entries"][0]["name"] == "candidates.csv"
    assert payload["preview_entries"][1]["name"] == "attachments/resume.pdf"

    mock_download.assert_called_once_with(
        access_token="dropbox-access-token",
        path="/exports/Recruiterflow.zip",
    )


def test_dropbox_zip_members_preview_filters_by_member_prefix() -> None:
    """
    Verify that the ZIP-preview route can narrow the member list by prefix.

    Example
    -------
    Filtering to `job/` should let us inspect the first job chunk names without
    paging through thousands of candidate attachment paths first.
    """

    client = TestClient(create_app())

    fake_connection = {
        "dropbox_account_id": "dbid:AAExample",
        "access_token": "dropbox-access-token",
        "refresh_token": "dropbox-refresh-token",
        "obtained_at": datetime.now(timezone.utc),
        "expires_in_seconds": 14400,
    }

    archive_buffer = BytesIO()
    with ZipFile(archive_buffer, mode="w") as archive:
        archive.writestr("candidate/1.100.json", '[{"id": 1}]')
        archive.writestr("job/1.100.json", '[{"id": 10}]')
        archive.writestr("job/101.200.json", '[{"id": 11}]')

    fake_download_result = {
        "path": "/exports/Recruiterflow.zip",
        "file_name": "Recruiterflow.zip",
        "content_type": "application/zip",
        "content_bytes": archive_buffer.getvalue(),
        "file_metadata": {"name": "Recruiterflow.zip"},
        "endpoint_url": "https://content.dropboxapi.com/2/files/download",
    }

    with patch(
        "backend.api.v1.integrations.get_dropbox_oauth_connection",
        return_value=fake_connection,
    ):
        with patch(
            "backend.api.v1.integrations.download_dropbox_file",
            return_value=fake_download_result,
        ):
            response = client.get(
                DROPBOX_ZIP_MEMBERS_PREVIEW_PATH_TEMPLATE.format(
                    dropbox_account_id="dbid:AAExample"
                ),
                params={
                    "file_path": "/exports/Recruiterflow.zip",
                    "member_prefix": "job/",
                    "limit": 10,
                },
            )

    assert response.status_code == status.HTTP_200_OK

    payload = response.json()

    assert payload["entry_count"] == 2
    assert payload["top_level_entries"] == ["job"]
    assert payload["preview_entries"][0]["name"] == "job/1.100.json"
    assert payload["preview_entries"][1]["name"] == "job/101.200.json"


def test_dropbox_zip_json_member_preview_returns_bounded_payload() -> None:
    """
    Verify that the JSON-member preview route exposes a bounded schema-mapping
    preview for one ZIP member.

    Example
    -------
    A candidate chunk such as `candidate/1.100.json` should return:

    - the member path
    - list size
    - keys from the first object item
    - a small payload preview
    """

    client = TestClient(create_app())

    fake_connection = {
        "dropbox_account_id": "dbid:AAExample",
        "access_token": "dropbox-access-token",
        "refresh_token": "dropbox-refresh-token",
        "obtained_at": datetime.now(timezone.utc),
        "expires_in_seconds": 14400,
    }

    archive_buffer = BytesIO()
    with ZipFile(archive_buffer, mode="w") as archive:
        archive.writestr(
            "candidate/1.100.json",
            (
                '[{"id": 1, "name": "Ada Lovelace", "email": "ada@example.com"}, '
                '{"id": 2, "name": "Grace Hopper", "email": "grace@example.com"}]'
            ),
        )

    fake_download_result = {
        "path": "/exports/Recruiterflow.zip",
        "file_name": "Recruiterflow.zip",
        "content_type": "application/zip",
        "content_bytes": archive_buffer.getvalue(),
        "file_metadata": {"name": "Recruiterflow.zip"},
        "endpoint_url": "https://content.dropboxapi.com/2/files/download",
    }

    with patch(
        "backend.api.v1.integrations.get_dropbox_oauth_connection",
        return_value=fake_connection,
    ):
        with patch(
            "backend.api.v1.integrations.download_dropbox_file",
            return_value=fake_download_result,
        ) as mock_download:
            response = client.get(
                DROPBOX_ZIP_JSON_MEMBER_PREVIEW_PATH_TEMPLATE.format(
                    dropbox_account_id="dbid:AAExample"
                ),
                params={
                    "file_path": "/exports/Recruiterflow.zip",
                    "member_name": "candidate/1.100.json",
                    "preview_limit": 1,
                },
            )

    assert response.status_code == status.HTTP_200_OK

    payload = response.json()

    assert payload["member_name"] == "candidate/1.100.json"
    assert payload["top_level_type"] == "list"
    assert payload["entry_count"] == 2
    assert payload["sample_item_keys"] == ["id", "name", "email"]
    assert payload["preview_payload"] == [
        {"id": 1, "name": "Ada Lovelace", "email": "ada@example.com"}
    ]

    mock_download.assert_called_once_with(
        access_token="dropbox-access-token",
        path="/exports/Recruiterflow.zip",
    )


def test_dropbox_current_account_refresh_preserves_account_id_and_scope() -> None:
    """
    Verify that a Dropbox token refresh preserves stable stored metadata when
    the refresh response omits it.

    Example
    -------
    Dropbox refresh responses often omit:

    - `account_id`
    - `scope`
    - `refresh_token`

    This test proves the route-side refresh path merges the fresh access-token
    fields with the stable stored metadata before saving the refreshed row.
    """

    client = TestClient(create_app())

    fake_connection = {
        "dropbox_account_id": "dbid:AAExample",
        "access_token": "expired-access-token",
        "refresh_token": "stored-refresh-token",
        "scope": "account_info.read files.metadata.read",
        "obtained_at": datetime.now(timezone.utc) - timedelta(hours=5),
        "expires_in_seconds": 60,
    }

    saved_connection = {
        "id": "11111111-1111-1111-1111-111111111111",
        "dropbox_account_id": "dbid:AAExample",
        "access_token": "fresh-access-token",
        "refresh_token": "stored-refresh-token",
        "token_type": "bearer",
        "expires_in_seconds": 14400,
        "obtained_at": datetime.now(timezone.utc),
        "scope": "account_info.read files.metadata.read",
    }

    fake_refreshed_token_set = DropboxTokenSet(
        access_token="fresh-access-token",
        token_type="bearer",
        expires_in=14400,
        refresh_token=None,
        scope=None,
        account_id=None,
        raw_payload={},
    )

    fake_account = {
        "account": {
            "account_id": "dbid:AAExample",
            "email": "tom@example.com",
        },
        "endpoint_url": "https://api.dropboxapi.com/2/users/get_current_account",
        "raw_payload": {},
    }

    with patch(
        "backend.api.v1.integrations.get_dropbox_oauth_connection",
        return_value=fake_connection,
    ):
        with patch(
            "backend.api.v1.integrations.refresh_dropbox_access_token",
            return_value=fake_refreshed_token_set,
        ):
            with patch(
                "backend.api.v1.integrations.save_dropbox_oauth_connection",
                return_value=saved_connection,
            ) as mock_save:
                with patch(
                    "backend.api.v1.integrations.fetch_dropbox_current_account",
                    return_value=fake_account,
                ):
                    response = client.get(
                        DROPBOX_CURRENT_ACCOUNT_PATH_TEMPLATE.format(
                            dropbox_account_id="dbid:AAExample"
                        )
                    )

    assert response.status_code == status.HTTP_200_OK

    saved_token_set = mock_save.call_args.args[0]

    assert saved_token_set.account_id == "dbid:AAExample"
    assert saved_token_set.refresh_token == "stored-refresh-token"
    assert saved_token_set.scope == "account_info.read files.metadata.read"
