"""
Integration tests for JobAdder-facing API routes.

These tests verify the real FastAPI route wiring for:

    GET /api/v1/integrations/jobadder/authorize
    GET /api/v1/integrations/jobadder/callback

The important question is:

    "Does the backend expose real JobAdder OAuth routes that behave clearly
    during setup?"

That matters because the callback URI must be registered exactly in the
JobAdder developer portal, and both routes need to point at live backend logic
rather than invented placeholder paths.

In plain language:

- prove the authorisation URL route exists
- prove the callback route exists
- prove JobAdder OAuth error queries are handled clearly
- prove a successful callback can reach the backend already
- prove the routes report whether OAuth settings are ready for the next step
"""

from collections.abc import Iterator

import pytest
from fastapi import status
from fastapi.testclient import TestClient

from backend.main import create_app
from backend.settings import get_settings

JOBADDER_AUTHORIZE_PATH = "/api/v1/integrations/jobadder/authorize"
JOBADDER_CALLBACK_PATH = "/api/v1/integrations/jobadder/callback"


@pytest.fixture(autouse=True)
def clear_settings_cache() -> Iterator[None]:
    """
    Clear cached settings before and after each test.

    Notes
    -----
    - `get_settings()` is cached.
    - These tests deliberately override environment variables with
      `monkeypatch`.
    - Clearing the cache ensures each test sees the environment values it set.
    """

    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def create_test_client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    """
    Create a test client with safe empty JobAdder OAuth settings by default.

    Notes
    -----
    - The callback route should still work even when OAuth credentials have not
      been configured yet.
    - Empty values make that setup stage explicit and predictable.
    """

    monkeypatch.setenv("JOBADDER_CLIENT_ID", "")
    monkeypatch.setenv("JOBADDER_CLIENT_SECRET", "")
    monkeypatch.setenv("JOBADDER_REDIRECT_URI", "")

    return TestClient(create_app())


def test_jobadder_authorize_returns_url_when_minimum_oauth_settings_exist(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    Verify that the authorise route returns a usable approval URL.

    Notes
    -----
    - This is the route that lets us generate the URL to send to the client-side
      approver.
    - Only the client ID and redirect URI are needed to build that link.
    """

    monkeypatch.setenv("JOBADDER_CLIENT_ID", "jobadder-client-id")
    monkeypatch.setenv(
        "JOBADDER_REDIRECT_URI",
        "https://james-joseph-associates.vercel.app/api/v1/integrations/jobadder/callback",
    )

    client = TestClient(create_app())

    response = client.get(f"{JOBADDER_AUTHORIZE_PATH}?state=connect-jobadder-dev")

    assert response.status_code == status.HTTP_200_OK

    payload = response.json()

    assert payload["oauth_configuration_ready"] is True
    assert payload["state"] == "connect-jobadder-dev"
    assert payload["authorization_url"].startswith(
        "https://id.jobadder.com/connect/authorize?"
    )
    assert "client_id=jobadder-client-id" in payload["authorization_url"]


def test_jobadder_authorize_rejects_missing_required_oauth_settings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    Verify that the authorise route fails clearly when settings are missing.

    Notes
    -----
    - This protects the route from returning a broken approval link.
    - The expected behaviour here is a standard API error response.
    """

    client = create_test_client(monkeypatch)

    response = client.get(JOBADDER_AUTHORIZE_PATH)

    assert response.status_code == status.HTTP_401_UNAUTHORIZED

    payload = response.json()

    assert payload["error"]["code"] == "unauthorized"
    assert payload["error"]["message"] == "JobAdder OAuth is not configured."
    assert payload["error"]["details"] == [
        {
            "required_settings": [
                "JOBADDER_CLIENT_ID",
                "JOBADDER_REDIRECT_URI",
            ]
        }
    ]


def test_jobadder_callback_accepts_authorization_code_when_oauth_settings_are_not_ready(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    Verify that the callback route is live even before OAuth settings exist.

    Notes
    -----
    - This is the important "the redirect URI is real" test.
    - The backend has no JobAdder client ID, secret, or redirect URI configured.
    - The route should still accept the callback and explain that the next setup
      step is to configure those values.
    """

    client = create_test_client(monkeypatch)

    response = client.get(
        f"{JOBADDER_CALLBACK_PATH}?code=test-jobadder-code&state=connect-dev"
    )

    assert response.status_code == status.HTTP_200_OK

    payload = response.json()

    assert payload["status"] == "received"
    assert payload["message"] == "JobAdder authorization callback received."
    assert payload["authorization_code_received"] is True
    assert payload["oauth_configuration_ready"] is False
    assert payload["state"] == "connect-dev"
    assert "JOBADDER_CLIENT_ID" in payload["next_step"]


def test_jobadder_callback_reports_oauth_configuration_ready_when_required_settings_exist(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    Verify that the callback route reports readiness once OAuth settings exist.

    Notes
    -----
    - The route still does not exchange the code yet.
    - It does need to recognise when the backend has the minimum settings
      required for that later step.
    """

    monkeypatch.setenv("JOBADDER_CLIENT_ID", "jobadder-client-id")
    monkeypatch.setenv("JOBADDER_CLIENT_SECRET", "jobadder-client-secret")
    monkeypatch.setenv(
        "JOBADDER_REDIRECT_URI",
        "http://127.0.0.1:8000/api/v1/integrations/jobadder/callback",
    )

    client = TestClient(create_app())

    response = client.get(f"{JOBADDER_CALLBACK_PATH}?code=test-jobadder-code")

    assert response.status_code == status.HTTP_200_OK

    payload = response.json()

    assert payload["status"] == "received"
    assert payload["authorization_code_received"] is True
    assert payload["oauth_configuration_ready"] is True
    assert "token exchange and token storage" in payload["next_step"]


def test_jobadder_callback_rejects_provider_error_query() -> None:
    """
    Verify that provider-side OAuth errors are returned clearly.

    Notes
    -----
    - JobAdder may redirect back with `error=...` instead of `code=...`.
    - The route should surface that as a standard API error rather than
      pretending the callback was successful.
    """

    client = TestClient(create_app())

    response = client.get(
        (
            f"{JOBADDER_CALLBACK_PATH}?"
            "error=access_denied&error_description=User%20cancelled&state=connect-dev"
        )
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST

    payload = response.json()

    assert payload["error"]["code"] == "unauthorized"
    assert payload["error"]["message"] == "JobAdder authorization was not completed."
    assert payload["error"]["details"] == [
        {"provider": "jobadder", "error": "access_denied"},
        {"provider_error_description": "User cancelled"},
        {"state": "connect-dev"},
    ]


def test_jobadder_callback_requires_authorization_code_when_no_provider_error_exists() -> None:
    """
    Verify that the callback rejects requests with neither `code` nor `error`.

    Notes
    -----
    - A valid callback should contain one or the other.
    - This protects the route from ambiguous or incomplete setup requests.
    """

    client = TestClient(create_app())

    response = client.get(JOBADDER_CALLBACK_PATH)

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT

    payload = response.json()

    assert payload["error"]["code"] == "validation_error"
    assert payload["error"]["message"] == "JobAdder authorization code is required."
    assert payload["error"]["details"] == [
        {"query_param": "code", "reason": "missing_or_empty"},
    ]
