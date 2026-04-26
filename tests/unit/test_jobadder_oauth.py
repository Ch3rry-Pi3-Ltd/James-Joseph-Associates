"""
Unit tests for JobAdder OAuth helper functions.

This module tests the small OAuth URL-building and token-exchange helpers in
`backend.services.jobadder_oauth`.

It gives the rest of the repository a stable way to check:

- whether the backend correctly detects minimum JobAdder OAuth configuration
- whether the authorisation URL is built correctly
- whether optional state values are included correctly
- whether missing settings fail clearly
- whether the token-exchange payload is built correctly
- whether successful and failing JobAdder token responses are handled clearly
- whether the helper can be tested without calling a real JobAdder account

Keeping these tests small makes the OAuth setup layer easier to trust because:

- route handlers do not need to be the first place where URL construction bugs
  are found
- service code does not need a live JobAdder account to prove its behaviour
- tests can validate token-response parsing without spending real OAuth codes
- the backend can grow the OAuth flow one small step at a time

In plain language:

- this module answers the question:

    "Does the backend build the JobAdder approval link and token request correctly?"

- it does not call the real JobAdder service
- it does not store tokens
- it does not require a live callback
- it only tests local Python behaviour around the helper functions
"""

from urllib.parse import parse_qs, urlparse

import httpx
import pytest

from backend.services.jobadder_oauth import (
    JOBADDER_AUTHORIZE_URL,
    JOBADDER_TOKEN_URL,
    JobAdderOAuthExchangeError,
    JobAdderTokenSet,
    build_jobadder_authorization_url,
    build_jobadder_token_exchange_payload,
    exchange_jobadder_authorization_code,
    has_jobadder_oauth_configuration,
    has_jobadder_token_exchange_configuration,
)
from backend.settings import get_settings


def test_has_jobadder_oauth_configuration_returns_true_when_minimum_values_exist(
    monkeypatch,
) -> None:
    """
    Verify that the helper reports configured state when client ID and redirect
    URI exist.

    In plain language:

    - set fake JobAdder config
    - ask the helper whether setup exists
    - confirm it says yes
    """

    get_settings.cache_clear()

    monkeypatch.setenv("JOBADDER_CLIENT_ID", "fake-client-id")
    monkeypatch.setenv(
        "JOBADDER_REDIRECT_URI",
        "https://example.com/api/v1/integrations/jobadder/callback",
    )

    assert has_jobadder_oauth_configuration() is True

    get_settings.cache_clear()


def test_has_jobadder_oauth_configuration_returns_false_when_values_are_missing(
    monkeypatch,
) -> None:
    """
    Verify that the helper reports unconfigured state when required values are
    blank.

    In plain language:

    - blank out the needed config
    - ask the helper whether setup exists
    - confirm it says no
    """

    get_settings.cache_clear()

    monkeypatch.setenv("JOBADDER_CLIENT_ID", "")
    monkeypatch.setenv("JOBADDER_REDIRECT_URI", "")

    assert has_jobadder_oauth_configuration() is False

    get_settings.cache_clear()


def test_has_jobadder_token_exchange_configuration_returns_true_when_all_values_exist(
    monkeypatch,
) -> None:
    """
    Verify that the stricter token-exchange config check needs all three values.

    In plain language:

    - set fake client ID, client secret, and redirect URI
    - confirm the backend now says token exchange is ready
    """

    get_settings.cache_clear()

    monkeypatch.setenv("JOBADDER_CLIENT_ID", "fake-client-id")
    monkeypatch.setenv("JOBADDER_CLIENT_SECRET", "fake-client-secret")
    monkeypatch.setenv(
        "JOBADDER_REDIRECT_URI",
        "https://example.com/api/v1/integrations/jobadder/callback",
    )

    assert has_jobadder_token_exchange_configuration() is True

    get_settings.cache_clear()


def test_has_jobadder_token_exchange_configuration_returns_false_when_client_secret_is_missing(
    monkeypatch,
) -> None:
    """
    Verify that token exchange is not considered ready without the client secret.

    In plain language:

    - set only part of the config
    - confirm the stricter exchange check still says no
    """

    get_settings.cache_clear()

    monkeypatch.setenv("JOBADDER_CLIENT_ID", "fake-client-id")
    monkeypatch.setenv("JOBADDER_CLIENT_SECRET", "")
    monkeypatch.setenv(
        "JOBADDER_REDIRECT_URI",
        "https://example.com/api/v1/integrations/jobadder/callback",
    )

    assert has_jobadder_token_exchange_configuration() is False

    get_settings.cache_clear()


def test_build_jobadder_authorization_url_returns_expected_base_and_parameters(
    monkeypatch,
) -> None:
    """
    Verify that the helper builds the expected JobAdder authorisation URL.

    Notes
    -----
    - This test does not compare one giant URL string directly.
    - Instead, it parses the result and checks the important parts separately.
    - That makes the test easier to read and less fragile.

    In plain language:

    - build the approval URL
    - split it apart
    - check the key pieces are correct
    """

    get_settings.cache_clear()

    monkeypatch.setenv("JOBADDER_CLIENT_ID", "fake-client-id")
    monkeypatch.setenv(
        "JOBADDER_REDIRECT_URI",
        "https://example.com/api/v1/integrations/jobadder/callback",
    )

    url = build_jobadder_authorization_url()

    parsed = urlparse(url)
    query = parse_qs(parsed.query)

    assert f"{parsed.scheme}://{parsed.netloc}{parsed.path}" == JOBADDER_AUTHORIZE_URL
    assert query["response_type"] == ["code"]
    assert query["client_id"] == ["fake-client-id"]
    assert query["scope"] == ["read write offline_access"]
    assert query["redirect_uri"] == [
        "https://example.com/api/v1/integrations/jobadder/callback"
    ]
    assert "scope=read%20write%20offline_access" in url

    get_settings.cache_clear()


def test_build_jobadder_authorization_url_includes_state_when_supplied(
    monkeypatch,
) -> None:
    """
    Verify that a supplied state value is included in the URL.

    In plain language:

    - build the URL with a state value
    - confirm the state comes back in the query
    """

    get_settings.cache_clear()

    monkeypatch.setenv("JOBADDER_CLIENT_ID", "fake-client-id")
    monkeypatch.setenv(
        "JOBADDER_REDIRECT_URI",
        "https://example.com/api/v1/integrations/jobadder/callback",
    )

    url = build_jobadder_authorization_url(state="connect-jobadder-dev")

    parsed = urlparse(url)
    query = parse_qs(parsed.query)

    assert query["state"] == ["connect-jobadder-dev"]

    get_settings.cache_clear()


def test_build_jobadder_authorization_url_raises_when_required_settings_are_missing(
    monkeypatch,
) -> None:
    """
    Verify that the helper fails clearly when required settings are missing.

    In plain language:

    - remove the required config
    - try to build the URL
    - confirm the helper raises a clear error
    """

    get_settings.cache_clear()

    monkeypatch.setenv("JOBADDER_CLIENT_ID", "")
    monkeypatch.setenv("JOBADDER_REDIRECT_URI", "")

    try:
        build_jobadder_authorization_url()
    except ValueError as exc:
        assert str(exc) == (
            "JobAdder OAuth is not configured. "
            "Set JOBADDER_CLIENT_ID and JOBADDER_REDIRECT_URI."
        )
    else:
        raise AssertionError("Expected ValueError to be raised.")

    get_settings.cache_clear()


def test_build_jobadder_token_exchange_payload_returns_expected_form_fields(
    monkeypatch,
) -> None:
    """
    Verify that the token-exchange payload contains the standard OAuth fields.

    In plain language:

    - give the helper a fake code
    - confirm the returned form data is what JobAdder should receive
    """

    get_settings.cache_clear()

    monkeypatch.setenv("JOBADDER_CLIENT_ID", "fake-client-id")
    monkeypatch.setenv("JOBADDER_CLIENT_SECRET", "fake-client-secret")
    monkeypatch.setenv(
        "JOBADDER_REDIRECT_URI",
        "https://example.com/api/v1/integrations/jobadder/callback",
    )

    payload = build_jobadder_token_exchange_payload(code="test-auth-code")

    assert payload == {
        "grant_type": "authorization_code",
        "code": "test-auth-code",
        "client_id": "fake-client-id",
        "client_secret": "fake-client-secret",
        "redirect_uri": "https://example.com/api/v1/integrations/jobadder/callback",
    }

    get_settings.cache_clear()


def test_build_jobadder_token_exchange_payload_raises_when_code_is_blank(
    monkeypatch,
) -> None:
    """
    Verify that the payload helper rejects an empty authorisation code.

    In plain language:

    - pass a blank code
    - confirm the helper fails early
    """

    get_settings.cache_clear()

    monkeypatch.setenv("JOBADDER_CLIENT_ID", "fake-client-id")
    monkeypatch.setenv("JOBADDER_CLIENT_SECRET", "fake-client-secret")
    monkeypatch.setenv(
        "JOBADDER_REDIRECT_URI",
        "https://example.com/api/v1/integrations/jobadder/callback",
    )

    with pytest.raises(ValueError) as exc_info:
        build_jobadder_token_exchange_payload(code="   ")

    assert str(exc_info.value) == "JobAdder authorization code cannot be empty."

    get_settings.cache_clear()


def test_exchange_jobadder_authorization_code_returns_token_set_when_jobadder_accepts_request(
    monkeypatch,
) -> None:
    """
    Verify that a successful JobAdder response is normalised correctly.

    Notes
    -----
    - This test does not call the real JobAdder token endpoint.
    - It replaces `httpx.post(...)` with a small fake function.
    - That lets the test inspect the outgoing request and control the returned
      payload.

    In plain language:

    - pretend JobAdder accepted the exchange
    - confirm the backend builds the right request
    - confirm the returned token object is correct
    """

    get_settings.cache_clear()

    monkeypatch.setenv("JOBADDER_CLIENT_ID", "fake-client-id")
    monkeypatch.setenv("JOBADDER_CLIENT_SECRET", "fake-client-secret")
    monkeypatch.setenv(
        "JOBADDER_REDIRECT_URI",
        "https://example.com/api/v1/integrations/jobadder/callback",
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
                "access_token": "jobadder-access-token",
                "token_type": "Bearer",
                "expires_in": 3600,
                "refresh_token": "jobadder-refresh-token",
                "scope": "read write offline_access",
            },
        )

    monkeypatch.setattr(httpx, "post", fake_post)

    token_set = exchange_jobadder_authorization_code(code="realistic-auth-code")

    assert isinstance(token_set, JobAdderTokenSet)
    assert token_set.access_token == "jobadder-access-token"
    assert token_set.token_type == "Bearer"
    assert token_set.expires_in == 3600
    assert token_set.refresh_token == "jobadder-refresh-token"
    assert token_set.scope == "read write offline_access"
    assert token_set.raw_payload["access_token"] == "jobadder-access-token"

    assert captured_request["url"] == JOBADDER_TOKEN_URL
    assert captured_request["data"] == {
        "grant_type": "authorization_code",
        "code": "realistic-auth-code",
        "client_id": "fake-client-id",
        "client_secret": "fake-client-secret",
        "redirect_uri": "https://example.com/api/v1/integrations/jobadder/callback",
    }
    assert captured_request["headers"] == {
        "Accept": "application/json",
    }
    assert captured_request["timeout"] == 30.0

    get_settings.cache_clear()


def test_exchange_jobadder_authorization_code_raises_for_provider_error_response(
    monkeypatch,
) -> None:
    """
    Verify that provider-side OAuth failures become a structured local error.

    In plain language:

    - pretend JobAdder rejected the exchange
    - confirm the helper raises a clear backend exception
    """

    get_settings.cache_clear()

    monkeypatch.setenv("JOBADDER_CLIENT_ID", "fake-client-id")
    monkeypatch.setenv("JOBADDER_CLIENT_SECRET", "fake-client-secret")
    monkeypatch.setenv(
        "JOBADDER_REDIRECT_URI",
        "https://example.com/api/v1/integrations/jobadder/callback",
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

    with pytest.raises(JobAdderOAuthExchangeError) as exc_info:
        exchange_jobadder_authorization_code(code="expired-code")

    error = exc_info.value

    assert str(error) == "JobAdder token exchange failed."
    assert error.status_code == 400
    assert error.provider_error == "invalid_grant"
    assert error.provider_error_description == "Authorization code has expired."
    assert error.response_body == {
        "error": "invalid_grant",
        "error_description": "Authorization code has expired.",
    }

    get_settings.cache_clear()


def test_exchange_jobadder_authorization_code_raises_when_success_response_is_missing_access_token(
    monkeypatch,
) -> None:
    """
    Verify that an incomplete provider success payload is rejected clearly.

    In plain language:

    - pretend JobAdder returned 200
    - but left out the access token
    - confirm the helper rejects the response
    """

    get_settings.cache_clear()

    monkeypatch.setenv("JOBADDER_CLIENT_ID", "fake-client-id")
    monkeypatch.setenv("JOBADDER_CLIENT_SECRET", "fake-client-secret")
    monkeypatch.setenv(
        "JOBADDER_REDIRECT_URI",
        "https://example.com/api/v1/integrations/jobadder/callback",
    )

    def fake_post(url, data, headers, timeout):
        return httpx.Response(
            200,
            json={
                "token_type": "Bearer",
                "expires_in": 3600,
            },
        )

    monkeypatch.setattr(httpx, "post", fake_post)

    with pytest.raises(JobAdderOAuthExchangeError) as exc_info:
        exchange_jobadder_authorization_code(code="broken-success-payload")

    error = exc_info.value

    assert (
        str(error)
        == "JobAdder token response did not include an access token."
    )
    assert error.status_code == 200
    assert error.response_body == {
        "token_type": "Bearer",
        "expires_in": 3600,
    }

    get_settings.cache_clear()


def test_exchange_jobadder_authorization_code_raises_for_network_failure(
    monkeypatch,
) -> None:
    """
    Verify that transport-level failures are surfaced clearly.

    In plain language:

    - pretend the backend could not reach JobAdder at all
    - confirm the helper raises a clear exchange error
    """

    get_settings.cache_clear()

    monkeypatch.setenv("JOBADDER_CLIENT_ID", "fake-client-id")
    monkeypatch.setenv("JOBADDER_CLIENT_SECRET", "fake-client-secret")
    monkeypatch.setenv(
        "JOBADDER_REDIRECT_URI",
        "https://example.com/api/v1/integrations/jobadder/callback",
    )

    def fake_post(url, data, headers, timeout):
        raise httpx.ConnectError("Network failure")

    monkeypatch.setattr(httpx, "post", fake_post)

    with pytest.raises(JobAdderOAuthExchangeError) as exc_info:
        exchange_jobadder_authorization_code(code="realistic-auth-code")

    assert str(exc_info.value) == "Could not reach the JobAdder token endpoint."

    get_settings.cache_clear()
