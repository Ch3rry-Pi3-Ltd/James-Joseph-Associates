"""
Unit tests for JobAdder OAuth helper functions.

This module tests the small OAuth URL-building helpers in
`backend.services.jobadder_oauth`.

It gives the rest of the repository a stable way to check:

- whether the backend correctly detects minimum JobAdder OAuth configuration
- whether the authorisation URL is built correctly
- whether optional state values are included correctly
- whether missing settings fail clearly
- whether the helper can be tested without calling JobAdder

Keeping these tests small makes the OAuth setup layer easier to trust because:

- route handlers do not need to be the first place where URL construction bugs
  are found
- tests can validate the exact query pieces without needing a live JobAdder
  account
- the backend can grow the OAuth flow one small step at a time

In plain language:

- this module answers the question:

    "Does the backend build the JobAdder approval link correctly?"

- it does not call JobAdder
- it does not exchange tokens
- it does not require a live callback
- it only tests local Python behaviour around the helper functions
"""

from urllib.parse import parse_qs, urlparse

from backend.services.jobadder_oauth import (
    JOBADDER_AUTHORIZE_URL,
    build_jobadder_authorization_url,
    has_jobadder_oauth_configuration,
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
