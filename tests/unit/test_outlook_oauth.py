"""
Unit tests for Outlook OAuth helper functions.

This module tests the small OAuth URL-building and token-exchange helpers in
`backend.services.outlook_oauth`.
"""

from urllib.parse import parse_qs, urlparse

import httpx
import pytest

from backend.services.outlook_oauth import (
    DEFAULT_OUTLOOK_SCOPE,
    OutlookOAuthExchangeError,
    OutlookTokenSet,
    build_outlook_authorization_url,
    build_outlook_token_exchange_payload,
    exchange_outlook_authorization_code,
    has_outlook_oauth_configuration,
    has_outlook_token_exchange_configuration,
)
from backend.settings import get_settings


def test_has_outlook_oauth_configuration_returns_true_when_minimum_values_exist(
    monkeypatch,
) -> None:
    """
    Verify that the helper reports configured state when client ID and redirect
    URI exist.

    Example
    -------
    If:

    - `MICROSOFT_CLIENT_ID` is set
    - `MICROSOFT_REDIRECT_URI` is set

    then the helper should return `True` even before the client secret is
    configured.
    """

    get_settings.cache_clear()

    monkeypatch.setenv("MICROSOFT_CLIENT_ID", "fake-microsoft-client-id")
    monkeypatch.setenv(
        "MICROSOFT_REDIRECT_URI",
        "https://example.com/api/v1/integrations/outlook/callback",
    )

    assert has_outlook_oauth_configuration() is True

    get_settings.cache_clear()


def test_has_outlook_token_exchange_configuration_returns_false_when_secret_is_missing(
    monkeypatch,
) -> None:
    """
    Verify that token exchange is not considered ready without the client
    secret.
    """

    get_settings.cache_clear()

    monkeypatch.setenv("MICROSOFT_CLIENT_ID", "fake-microsoft-client-id")
    monkeypatch.setenv("MICROSOFT_CLIENT_SECRET", "")
    monkeypatch.setenv(
        "MICROSOFT_REDIRECT_URI",
        "https://example.com/api/v1/integrations/outlook/callback",
    )

    assert has_outlook_token_exchange_configuration() is False

    get_settings.cache_clear()


def test_build_outlook_authorization_url_returns_expected_parameters(
    monkeypatch,
) -> None:
    """
    Verify that the helper builds the expected Microsoft authorization URL.
    """

    get_settings.cache_clear()

    monkeypatch.setenv("MICROSOFT_CLIENT_ID", "fake-microsoft-client-id")
    monkeypatch.setenv("MICROSOFT_TENANT_ID", "organizations")
    monkeypatch.setenv(
        "MICROSOFT_REDIRECT_URI",
        "https://example.com/api/v1/integrations/outlook/callback",
    )

    url = build_outlook_authorization_url(state="connect-outlook-dev")

    parsed = urlparse(url)
    query = parse_qs(parsed.query)

    assert f"{parsed.scheme}://{parsed.netloc}{parsed.path}" == (
        "https://login.microsoftonline.com/organizations/oauth2/v2.0/authorize"
    )
    assert query["response_type"] == ["code"]
    assert query["client_id"] == ["fake-microsoft-client-id"]
    assert query["redirect_uri"] == [
        "https://example.com/api/v1/integrations/outlook/callback"
    ]
    assert query["scope"] == [DEFAULT_OUTLOOK_SCOPE]
    assert query["state"] == ["connect-outlook-dev"]

    get_settings.cache_clear()


def test_build_outlook_token_exchange_payload_returns_expected_fields(
    monkeypatch,
) -> None:
    """
    Verify that the token-exchange payload contains the expected OAuth fields.
    """

    get_settings.cache_clear()

    monkeypatch.setenv("MICROSOFT_CLIENT_ID", "fake-microsoft-client-id")
    monkeypatch.setenv("MICROSOFT_CLIENT_SECRET", "fake-microsoft-client-secret")
    monkeypatch.setenv(
        "MICROSOFT_REDIRECT_URI",
        "https://example.com/api/v1/integrations/outlook/callback",
    )

    payload = build_outlook_token_exchange_payload(code="test-auth-code")

    assert payload == {
        "client_id": "fake-microsoft-client-id",
        "client_secret": "fake-microsoft-client-secret",
        "code": "test-auth-code",
        "grant_type": "authorization_code",
        "redirect_uri": "https://example.com/api/v1/integrations/outlook/callback",
    }

    get_settings.cache_clear()


def test_exchange_outlook_authorization_code_returns_token_set_when_provider_accepts_request(
    monkeypatch,
) -> None:
    """
    Verify that a successful Microsoft response is normalized correctly.
    """

    get_settings.cache_clear()

    monkeypatch.setenv("MICROSOFT_CLIENT_ID", "fake-microsoft-client-id")
    monkeypatch.setenv("MICROSOFT_CLIENT_SECRET", "fake-microsoft-client-secret")
    monkeypatch.setenv(
        "MICROSOFT_REDIRECT_URI",
        "https://example.com/api/v1/integrations/outlook/callback",
    )

    def fake_post(url, data, headers, timeout):
        assert url == (
            "https://login.microsoftonline.com/organizations/oauth2/v2.0/token"
        )
        return httpx.Response(
            200,
            json={
                "access_token": "microsoft-access-token",
                "token_type": "Bearer",
                "expires_in": "3600",
                "refresh_token": "microsoft-refresh-token",
                "scope": DEFAULT_OUTLOOK_SCOPE,
                "id_token": (
                    "aaa."
                    "eyJvaWQiOiJhYWFhYWFhLWJiYmItY2NjYy1kZGRkLWVlZWVlZWVlZWVlZSIs"
                    "InRpZCI6ImZmZmZmZmZmLTExMTEtMjIyMi0zMzMzLTQ0NDQ0NDQ0NDQ0NCIs"
                    "InByZWZlcnJlZF91c2VybmFtZSI6InRvbUBleGFtcGxlLmNvbSJ9."
                    "bbb"
                ),
            },
        )

    monkeypatch.setattr(httpx, "post", fake_post)

    token_set = exchange_outlook_authorization_code(code="realistic-auth-code")

    assert isinstance(token_set, OutlookTokenSet)
    assert token_set.access_token == "microsoft-access-token"
    assert token_set.refresh_token == "microsoft-refresh-token"
    assert token_set.expires_in == 3600
    assert token_set.microsoft_user_id == "aaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
    assert token_set.tenant_id == "ffffffff-1111-2222-3333-444444444444"
    assert token_set.user_principal_name == "tom@example.com"

    get_settings.cache_clear()


def test_exchange_outlook_authorization_code_raises_for_provider_error_response(
    monkeypatch,
) -> None:
    """
    Verify that a failing Microsoft response becomes a typed exchange error.
    """

    get_settings.cache_clear()

    monkeypatch.setenv("MICROSOFT_CLIENT_ID", "fake-microsoft-client-id")
    monkeypatch.setenv("MICROSOFT_CLIENT_SECRET", "fake-microsoft-client-secret")
    monkeypatch.setenv(
        "MICROSOFT_REDIRECT_URI",
        "https://example.com/api/v1/integrations/outlook/callback",
    )

    def fake_post(url, data, headers, timeout):
        return httpx.Response(
            400,
            json={
                "error": "invalid_grant",
                "error_description": "Authorization code was already redeemed.",
            },
        )

    monkeypatch.setattr(httpx, "post", fake_post)

    with pytest.raises(OutlookOAuthExchangeError) as exc_info:
        exchange_outlook_authorization_code(code="already-used-code")

    assert exc_info.value.status_code == 400
    assert exc_info.value.provider_error == "invalid_grant"
    assert exc_info.value.provider_error_description == (
        "Authorization code was already redeemed."
    )

    get_settings.cache_clear()
