"""
Unit tests for Dropbox OAuth helper functions.

This module tests the small OAuth URL-building and token-exchange helpers in
`backend.services.dropbox_oauth`.

It gives the rest of the repository a stable way to check:

- whether the backend correctly detects minimum Dropbox OAuth configuration
- whether the authorization URL is built correctly
- whether optional state values are included correctly
- whether missing settings fail clearly
- whether the token-exchange payload is built correctly
- whether successful and failing Dropbox token responses are handled clearly

In plain language:

- this module answers the question:

    "Does the backend build the Dropbox approval link and token request correctly?"
"""

from urllib.parse import parse_qs, urlparse

import httpx
import pytest

from backend.services.dropbox_oauth import (
    DEFAULT_DROPBOX_SCOPE,
    DROPBOX_AUTHORIZE_URL,
    DROPBOX_TOKEN_URL,
    DropboxOAuthExchangeError,
    DropboxTokenSet,
    build_dropbox_authorization_url,
    build_dropbox_token_exchange_payload,
    exchange_dropbox_authorization_code,
    has_dropbox_oauth_configuration,
    has_dropbox_token_exchange_configuration,
)
from backend.settings import get_settings


def test_has_dropbox_oauth_configuration_returns_true_when_minimum_values_exist(
    monkeypatch,
) -> None:
    """
    Verify that the helper reports configured state when app key and redirect
    URI exist.

    Example
    -------
    If:

    - `DROPBOX_CLIENT_ID` is set
    - `DROPBOX_REDIRECT_URI` is set

    then the helper should return `True` even before the client secret is
    configured.
    """

    get_settings.cache_clear()

    monkeypatch.setenv("DROPBOX_CLIENT_ID", "fake-dropbox-client-id")
    monkeypatch.setenv(
        "DROPBOX_REDIRECT_URI",
        "https://example.com/api/v1/integrations/dropbox/callback",
    )

    assert has_dropbox_oauth_configuration() is True

    get_settings.cache_clear()


def test_has_dropbox_token_exchange_configuration_returns_false_when_secret_is_missing(
    monkeypatch,
) -> None:
    """
    Verify that token exchange is not considered ready without the client
    secret.

    Example
    -------
    This covers the common partial-setup case where:

    - the app key exists
    - the redirect URI exists
    - but the app secret has not been configured yet
    """

    get_settings.cache_clear()

    monkeypatch.setenv("DROPBOX_CLIENT_ID", "fake-dropbox-client-id")
    monkeypatch.setenv("DROPBOX_CLIENT_SECRET", "")
    monkeypatch.setenv(
        "DROPBOX_REDIRECT_URI",
        "https://example.com/api/v1/integrations/dropbox/callback",
    )

    assert has_dropbox_token_exchange_configuration() is False

    get_settings.cache_clear()


def test_build_dropbox_authorization_url_returns_expected_base_and_parameters(
    monkeypatch,
) -> None:
    """
    Verify that the helper builds the expected Dropbox authorization URL.

    Example
    -------
    A correctly built URL should include:

    - `response_type=code`
    - the configured app key
    - the configured redirect URI
    - `token_access_type=offline`
    - the requested scope string
    """

    get_settings.cache_clear()

    monkeypatch.setenv("DROPBOX_CLIENT_ID", "fake-dropbox-client-id")
    monkeypatch.setenv(
        "DROPBOX_REDIRECT_URI",
        "https://example.com/api/v1/integrations/dropbox/callback",
    )

    url = build_dropbox_authorization_url(state="connect-dropbox-dev")

    parsed = urlparse(url)
    query = parse_qs(parsed.query)

    assert f"{parsed.scheme}://{parsed.netloc}{parsed.path}" == DROPBOX_AUTHORIZE_URL
    assert query["response_type"] == ["code"]
    assert query["client_id"] == ["fake-dropbox-client-id"]
    assert query["redirect_uri"] == [
        "https://example.com/api/v1/integrations/dropbox/callback"
    ]
    assert query["token_access_type"] == ["offline"]
    assert query["scope"] == [DEFAULT_DROPBOX_SCOPE]
    assert query["state"] == ["connect-dropbox-dev"]
    assert "scope=account_info.read%20files.metadata.read" in url

    get_settings.cache_clear()


def test_build_dropbox_authorization_url_raises_when_required_settings_are_missing(
    monkeypatch,
) -> None:
    """
    Verify that the helper fails clearly when required settings are missing.

    Example
    -------
    If both the app key and redirect URI are blank, the helper should fail
    before any caller tries to send Tom to a broken approval URL.
    """

    get_settings.cache_clear()

    monkeypatch.setenv("DROPBOX_CLIENT_ID", "")
    monkeypatch.setenv("DROPBOX_REDIRECT_URI", "")

    with pytest.raises(ValueError) as exc_info:
        build_dropbox_authorization_url()

    assert str(exc_info.value) == (
        "Dropbox OAuth is not configured. "
        "Set DROPBOX_CLIENT_ID and DROPBOX_REDIRECT_URI."
    )

    get_settings.cache_clear()


def test_build_dropbox_token_exchange_payload_returns_expected_form_fields(
    monkeypatch,
) -> None:
    """
    Verify that the token-exchange payload contains the standard OAuth fields.

    Example
    -------
    The outgoing form payload should contain:

    - `grant_type=authorization_code`
    - the one-time code
    - the configured app key
    - the configured app secret
    - the configured redirect URI
    """

    get_settings.cache_clear()

    monkeypatch.setenv("DROPBOX_CLIENT_ID", "fake-dropbox-client-id")
    monkeypatch.setenv("DROPBOX_CLIENT_SECRET", "fake-dropbox-client-secret")
    monkeypatch.setenv(
        "DROPBOX_REDIRECT_URI",
        "https://example.com/api/v1/integrations/dropbox/callback",
    )

    payload = build_dropbox_token_exchange_payload(code="test-auth-code")

    assert payload == {
        "grant_type": "authorization_code",
        "code": "test-auth-code",
        "client_id": "fake-dropbox-client-id",
        "client_secret": "fake-dropbox-client-secret",
        "redirect_uri": "https://example.com/api/v1/integrations/dropbox/callback",
    }

    get_settings.cache_clear()


def test_exchange_dropbox_authorization_code_returns_token_set_when_dropbox_accepts_request(
    monkeypatch,
) -> None:
    """
    Verify that a successful Dropbox response is normalized correctly.

    Example
    -------
    A successful Dropbox token response should become a `DropboxTokenSet`
    carrying:

    - `access_token`
    - `refresh_token`
    - `expires_in`
    - `scope`
    - `account_id`
    """

    get_settings.cache_clear()

    monkeypatch.setenv("DROPBOX_CLIENT_ID", "fake-dropbox-client-id")
    monkeypatch.setenv("DROPBOX_CLIENT_SECRET", "fake-dropbox-client-secret")
    monkeypatch.setenv(
        "DROPBOX_REDIRECT_URI",
        "https://example.com/api/v1/integrations/dropbox/callback",
    )

    captured_request: dict[str, object] = {}

    def fake_post(url, data, headers, timeout):
        captured_request["url"] = url
        captured_request["data"] = data
        captured_request["headers"] = headers
        captured_request["timeout"] = timeout

        return httpx.Response(
            200,
            json={
                "access_token": "dropbox-access-token",
                "token_type": "bearer",
                "expires_in": "14400",
                "refresh_token": "dropbox-refresh-token",
                "scope": DEFAULT_DROPBOX_SCOPE,
                "account_id": "dbid:AAExample",
            },
        )

    monkeypatch.setattr(httpx, "post", fake_post)

    token_set = exchange_dropbox_authorization_code(code="realistic-auth-code")

    assert isinstance(token_set, DropboxTokenSet)
    assert token_set.access_token == "dropbox-access-token"
    assert token_set.token_type == "bearer"
    assert token_set.expires_in == 14400
    assert token_set.refresh_token == "dropbox-refresh-token"
    assert token_set.scope == DEFAULT_DROPBOX_SCOPE
    assert token_set.account_id == "dbid:AAExample"
    assert captured_request["url"] == DROPBOX_TOKEN_URL

    get_settings.cache_clear()


def test_exchange_dropbox_authorization_code_raises_for_provider_error_response(
    monkeypatch,
) -> None:
    """
    Verify that provider-side OAuth failures become a structured local error.

    Example
    -------
    If Dropbox returns something like:

        {
            "error": "invalid_grant",
            "error_description": "Authorization code has expired."
        }

    then the helper should raise `DropboxOAuthExchangeError` with those values
    preserved for the route layer.
    """

    get_settings.cache_clear()

    monkeypatch.setenv("DROPBOX_CLIENT_ID", "fake-dropbox-client-id")
    monkeypatch.setenv("DROPBOX_CLIENT_SECRET", "fake-dropbox-client-secret")
    monkeypatch.setenv(
        "DROPBOX_REDIRECT_URI",
        "https://example.com/api/v1/integrations/dropbox/callback",
    )

    def fake_post(url, data, headers, timeout):
        return httpx.Response(
            400,
            json={
                "error": "invalid_grant",
                "error_description": "Authorization code has expired.",
            },
        )

    monkeypatch.setattr(httpx, "post", fake_post)

    with pytest.raises(DropboxOAuthExchangeError) as exc_info:
        exchange_dropbox_authorization_code(code="expired-code")

    error = exc_info.value

    assert str(error) == "Dropbox token exchange failed."
    assert error.status_code == 400
    assert error.provider_error == "invalid_grant"
    assert error.provider_error_description == "Authorization code has expired."

    get_settings.cache_clear()
