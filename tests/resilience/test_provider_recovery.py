"""Provider retry and degraded-upstream resilience coverage."""

from __future__ import annotations

import json
from unittest.mock import patch

from fastapi.responses import JSONResponse

from backend.api.v1.integrations import (
    _perform_dropbox_read_with_refresh_retry,
    _perform_jobadder_read_with_refresh_retry,
    _perform_outlook_read_with_refresh_retry,
)
from backend.services.dropbox_api import DropboxApiError
from backend.services.jobadder_api import JobAdderApiError
from backend.services.outlook_api import OutlookApiError


def _response_payload(response: JSONResponse) -> dict:
    return json.loads(bytes(response.body))


def test_jobadder_401_refreshes_once_and_retries_with_new_credentials() -> None:
    calls: list[tuple[str, str]] = []

    def read(*, api_url: str, access_token: str) -> dict:
        calls.append((api_url, access_token))
        if access_token == "expired-token":
            raise JobAdderApiError("expired", status_code=401)
        return {"items": [1]}

    with patch(
        "backend.api.v1.integrations._refresh_jobadder_stored_connection",
        return_value={
            "access_token": "fresh-token",
            "api_url": "https://fresh.example.test",
            "jobadder_instance": "fresh-instance",
        },
    ) as refresh:
        result = _perform_jobadder_read_with_refresh_retry(
            jobadder_account=7,
            stored_connection={
                "access_token": "expired-token",
                "refresh_token": "refresh-token",
                "api_url": "https://old.example.test",
                "jobadder_instance": "old-instance",
            },
            read_callable=read,
            provider_failure_message="JobAdder read failed.",
        )

    assert result == (
        {"items": [1]},
        "https://fresh.example.test",
        "fresh-instance",
    )
    assert calls == [
        ("https://old.example.test", "expired-token"),
        ("https://fresh.example.test", "fresh-token"),
    ]
    refresh.assert_called_once()


def test_dropbox_401_refreshes_once_and_retries_with_new_credentials() -> None:
    calls: list[str] = []

    def read(*, access_token: str) -> dict:
        calls.append(access_token)
        if access_token == "expired-token":
            raise DropboxApiError("expired", status_code=401)
        return {"entries": [1]}

    with patch(
        "backend.api.v1.integrations._refresh_dropbox_stored_connection",
        return_value={"access_token": "fresh-token"},
    ) as refresh:
        result = _perform_dropbox_read_with_refresh_retry(
            dropbox_account_id="dbid:account",
            stored_connection={
                "access_token": "expired-token",
                "refresh_token": "refresh-token",
                "scope": "files.metadata.read",
            },
            read_callable=read,
            provider_failure_message="Dropbox read failed.",
        )

    assert result == {"entries": [1]}
    assert calls == ["expired-token", "fresh-token"]
    refresh.assert_called_once()


def test_outlook_401_refreshes_once_and_retries_with_new_credentials() -> None:
    calls: list[str] = []

    def read(*, access_token: str) -> dict:
        calls.append(access_token)
        if access_token == "expired-token":
            raise OutlookApiError("expired", status_code=401)
        return {"messages": [1]}

    with patch(
        "backend.api.v1.integrations._refresh_outlook_stored_connection",
        return_value={"access_token": "fresh-token"},
    ) as refresh:
        result = _perform_outlook_read_with_refresh_retry(
            microsoft_user_id="user-id",
            stored_connection={
                "access_token": "expired-token",
                "refresh_token": "refresh-token",
            },
            read_callable=read,
            provider_failure_message="Outlook read failed.",
        )

    assert result == {"messages": [1]}
    assert calls == ["expired-token", "fresh-token"]
    refresh.assert_called_once()


def test_provider_retry_is_bounded_and_returns_safe_gateway_failure() -> None:
    calls: list[str] = []

    def read(*, access_token: str) -> dict:
        calls.append(access_token)
        raise DropboxApiError(
            "private provider response must not become the public message",
            status_code=401,
            endpoint_url="https://api.dropboxapi.com/test",
        )

    with patch(
        "backend.api.v1.integrations._refresh_dropbox_stored_connection",
        return_value={"access_token": "fresh-token"},
    ) as refresh:
        result = _perform_dropbox_read_with_refresh_retry(
            dropbox_account_id="dbid:account",
            stored_connection={
                "access_token": "expired-token",
                "refresh_token": "refresh-token",
                "scope": "files.metadata.read",
            },
            read_callable=read,
            provider_failure_message="Dropbox read failed.",
        )

    assert isinstance(result, JSONResponse)
    assert result.status_code == 502
    assert _response_payload(result)["error"]["message"] == "Dropbox read failed."
    assert calls == ["expired-token", "fresh-token"]
    refresh.assert_called_once()


def test_non_auth_provider_failure_does_not_trigger_credential_refresh() -> None:
    def read(*, access_token: str) -> dict:
        raise OutlookApiError("throttled", status_code=429)

    with patch(
        "backend.api.v1.integrations._refresh_outlook_stored_connection"
    ) as refresh:
        result = _perform_outlook_read_with_refresh_retry(
            microsoft_user_id="user-id",
            stored_connection={"access_token": "live-token"},
            read_callable=read,
            provider_failure_message="Outlook read failed.",
        )

    assert isinstance(result, JSONResponse)
    assert result.status_code == 502
    refresh.assert_not_called()
