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
- prove a successful callback can exchange and save a JobAdder connection
- prove failures are surfaced clearly at the exchange and persistence boundaries
"""

from collections.abc import Iterator
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest
from fastapi import status
from fastapi.testclient import TestClient

from backend.main import create_app
from backend.settings import get_settings
from backend.services.jobadder_api import JobAdderApiError
from backend.services.jobadder_oauth import JobAdderOAuthExchangeError

JOBADDER_AUTHORIZE_PATH = "/api/v1/integrations/jobadder/authorize"
JOBADDER_CALLBACK_PATH = "/api/v1/integrations/jobadder/callback"
JOBADDER_CANDIDATES_PREVIEW_PATH_TEMPLATE = (
    "/api/v1/integrations/jobadder/accounts/{jobadder_account}/candidates-preview"
)


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
    - The callback route now performs the full server-side completion step, so
      empty values should produce a clear "not configured" error rather than a
      silent partial success.
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


def test_jobadder_callback_rejects_missing_token_exchange_configuration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    Verify that the callback route fails clearly when token-exchange settings
    are missing.

    Notes
    -----
    - The route can only complete the OAuth flow when all three settings exist:
      - client ID
      - client secret
      - redirect URI
    - Empty values should fail before any exchange attempt is made.
    """

    client = create_test_client(monkeypatch)

    response = client.get(
        f"{JOBADDER_CALLBACK_PATH}?code=test-jobadder-code&state=connect-dev"
    )

    assert response.status_code == status.HTTP_401_UNAUTHORIZED

    payload = response.json()

    assert payload["error"]["code"] == "unauthorized"
    assert payload["error"]["message"] == "JobAdder token exchange is not configured."
    assert payload["error"]["details"] == [
        {
            "required_settings": [
                "JOBADDER_CLIENT_ID",
                "JOBADDER_CLIENT_SECRET",
                "JOBADDER_REDIRECT_URI",
            ]
        }
    ]


def test_jobadder_callback_exchanges_and_saves_connection_successfully(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    Verify that the callback route exchanges the code and saves the returned
    token set successfully.

    Notes
    -----
    - This is the main happy-path integration test for the new callback
      behaviour.
    - External JobAdder HTTP is still mocked through the service helper patch.
    - Database persistence is also mocked through the DB helper patch.
    """

    monkeypatch.setenv("JOBADDER_CLIENT_ID", "jobadder-client-id")
    monkeypatch.setenv("JOBADDER_CLIENT_SECRET", "jobadder-client-secret")
    monkeypatch.setenv(
        "JOBADDER_REDIRECT_URI",
        "http://127.0.0.1:8000/api/v1/integrations/jobadder/callback",
    )

    client = TestClient(create_app())

    fake_token_set = MagicMock()
    fake_saved_connection = {
        "id": "11111111-1111-1111-1111-111111111111",
        "jobadder_account": 123456,
        "jobadder_instance": "jobadder-prod-au",
    }

    with patch(
        "backend.api.v1.integrations.exchange_jobadder_authorization_code",
        return_value=fake_token_set,
    ) as mock_exchange:
        with patch(
            "backend.api.v1.integrations.save_jobadder_oauth_connection",
            return_value=fake_saved_connection,
        ) as mock_save:
            response = client.get(
                f"{JOBADDER_CALLBACK_PATH}?code=test-jobadder-code&state=connect-dev"
            )

    assert response.status_code == status.HTTP_200_OK

    payload = response.json()

    assert payload["status"] == "connected"
    assert payload["message"] == "JobAdder connection completed successfully."
    assert payload["oauth_connection_id"] == "11111111-1111-1111-1111-111111111111"
    assert payload["jobadder_account"] == 123456
    assert payload["jobadder_instance"] == "jobadder-prod-au"
    assert payload["state"] == "connect-dev"
    assert "first authenticated JobAdder API read" in payload["next_step"]

    mock_exchange.assert_called_once_with(code="test-jobadder-code")
    mock_save.assert_called_once_with(fake_token_set)


def test_jobadder_callback_returns_bad_gateway_when_token_exchange_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    Verify that a token-exchange failure becomes a clear API error.

    Notes
    -----
    - The route should not pretend the connection succeeded when JobAdder
      rejected the code or returned an unusable response.
    """

    monkeypatch.setenv("JOBADDER_CLIENT_ID", "jobadder-client-id")
    monkeypatch.setenv("JOBADDER_CLIENT_SECRET", "jobadder-client-secret")
    monkeypatch.setenv(
        "JOBADDER_REDIRECT_URI",
        "http://127.0.0.1:8000/api/v1/integrations/jobadder/callback",
    )

    client = TestClient(create_app())

    with patch(
        "backend.api.v1.integrations.exchange_jobadder_authorization_code",
        side_effect=JobAdderOAuthExchangeError(
            "JobAdder token exchange failed.",
            status_code=400,
            provider_error="invalid_grant",
            provider_error_description="Authorization code has expired.",
        ),
    ):
        response = client.get(
            f"{JOBADDER_CALLBACK_PATH}?code=expired-code&state=connect-dev"
        )

    assert response.status_code == status.HTTP_502_BAD_GATEWAY

    payload = response.json()

    assert payload["error"]["code"] == "approval_required"
    assert payload["error"]["message"] == "JobAdder token exchange failed."
    assert payload["error"]["details"] == [
        {"provider_status_code": 400},
        {"provider_error": "invalid_grant"},
        {"provider_error_description": "Authorization code has expired."},
        {"state": "connect-dev"},
    ]


def test_jobadder_callback_returns_internal_error_when_save_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    Verify that a persistence failure after successful exchange is surfaced
    clearly.

    Notes
    -----
    - This protects the route from returning a false success when the token set
      could not actually be persisted.
    """

    monkeypatch.setenv("JOBADDER_CLIENT_ID", "jobadder-client-id")
    monkeypatch.setenv("JOBADDER_CLIENT_SECRET", "jobadder-client-secret")
    monkeypatch.setenv(
        "JOBADDER_REDIRECT_URI",
        "http://127.0.0.1:8000/api/v1/integrations/jobadder/callback",
    )

    client = TestClient(create_app())

    fake_token_set = MagicMock()

    with patch(
        "backend.api.v1.integrations.exchange_jobadder_authorization_code",
        return_value=fake_token_set,
    ):
        with patch(
            "backend.api.v1.integrations.save_jobadder_oauth_connection",
            side_effect=RuntimeError("Failed to save JobAdder OAuth connection."),
        ):
            response = client.get(
                f"{JOBADDER_CALLBACK_PATH}?code=test-jobadder-code&state=connect-dev"
            )

    assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR

    payload = response.json()

    assert payload["error"]["code"] == "internal_error"
    assert (
        payload["error"]["message"]
        == "JobAdder token exchange succeeded, but the connection could not be saved."
    )
    assert payload["error"]["details"] == [
        {"reason": "Failed to save JobAdder OAuth connection."},
        {"state": "connect-dev"},
    ]


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


def test_jobadder_candidates_preview_returns_first_page_preview_successfully() -> None:
    """
    Verify that the new preview route loads the stored connection and returns a
    small first-page candidate preview from the JobAdder API service helper.

    Notes
    -----
    - This is the first route-level proof that the backend can take a stored
      OAuth connection and turn it into an authenticated provider read.
    - The database lookup and provider call are still mocked here because this
      test is about FastAPI route wiring and response behaviour, not live
      external I/O.
    """

    client = TestClient(create_app())

    fake_connection = {
        "jobadder_account": 2236,
        "jobadder_instance": "eu2",
        "api_url": "https://api.jobadder.com",
        "access_token": "jobadder-access-token",
        "refresh_token": "jobadder-refresh-token",
        "obtained_at": datetime.now(timezone.utc),
        "expires_in_seconds": 3600,
    }

    fake_preview = {
        "items": [
            {"candidateId": 1, "firstName": "Alice"},
            {"candidateId": 2, "firstName": "Ben"},
        ],
        "item_count": 2,
        "total_count": 25,
        "links": {
            "first": "https://api.jobadder.com/v2/candidates?page=1",
        },
        "endpoint_url": "https://api.jobadder.com/v2/candidates",
        "raw_payload": {},
    }

    with patch(
        "backend.api.v1.integrations.get_jobadder_oauth_connection",
        return_value=fake_connection,
    ) as mock_get_connection:
        with patch(
            "backend.api.v1.integrations.fetch_jobadder_candidates_preview",
            return_value=fake_preview,
        ) as mock_fetch_preview:
            response = client.get(
                JOBADDER_CANDIDATES_PREVIEW_PATH_TEMPLATE.format(
                    jobadder_account=2236
                )
            )

    assert response.status_code == status.HTTP_200_OK

    payload = response.json()

    assert payload["jobadder_account"] == 2236
    assert payload["jobadder_instance"] == "eu2"
    assert payload["api_url"] == "https://api.jobadder.com"
    assert payload["item_count"] == 2
    assert payload["total_count"] == 25
    assert payload["links"] == {
        "first": "https://api.jobadder.com/v2/candidates?page=1",
    }
    assert payload["candidates"] == [
        {"candidateId": 1, "firstName": "Alice"},
        {"candidateId": 2, "firstName": "Ben"},
    ]

    mock_get_connection.assert_called_once_with(2236)
    mock_fetch_preview.assert_called_once_with(
        api_url="https://api.jobadder.com",
        access_token="jobadder-access-token",
        item_limit=10,
    )


def test_jobadder_candidates_preview_returns_not_found_when_connection_is_missing() -> None:
    """
    Verify that the preview route fails clearly when the stored JobAdder
    connection row does not exist.

    In plain language:

    - pretend there is no saved JobAdder connection for the supplied account
    - call the route
    - confirm it returns a clean 404 instead of attempting a provider read
    """

    client = TestClient(create_app())

    with patch(
        "backend.api.v1.integrations.get_jobadder_oauth_connection",
        return_value=None,
    ):
        response = client.get(
            JOBADDER_CANDIDATES_PREVIEW_PATH_TEMPLATE.format(
                jobadder_account=2236
            )
        )

    assert response.status_code == status.HTTP_404_NOT_FOUND

    payload = response.json()

    assert payload["error"]["code"] == "not_found"
    assert payload["error"]["message"] == "Stored JobAdder connection was not found."
    assert payload["error"]["details"] == [
        {"jobadder_account": 2236},
    ]


def test_jobadder_candidates_preview_returns_bad_gateway_when_jobadder_read_fails() -> None:
    """
    Verify that a provider-side failure during the candidate read is surfaced
    clearly through the API route.

    Notes
    -----
    - This covers the case where the stored connection exists locally, but the
      upstream JobAdder API request itself fails.
    - The route should preserve the useful provider context that the service
      helper exposes, especially HTTP status and retry timing information.
    """

    client = TestClient(create_app())

    fake_connection = {
        "jobadder_account": 2236,
        "jobadder_instance": "eu2",
        "api_url": "https://api.jobadder.com",
        "access_token": "jobadder-access-token",
        "refresh_token": "jobadder-refresh-token",
        "obtained_at": datetime.now(timezone.utc) - timedelta(minutes=5),
        "expires_in_seconds": 3600,
    }

    with patch(
        "backend.api.v1.integrations.get_jobadder_oauth_connection",
        return_value=fake_connection,
    ):
        with patch(
            "backend.api.v1.integrations.fetch_jobadder_candidates_preview",
            side_effect=JobAdderApiError(
                "JobAdder candidate read failed.",
                status_code=429,
                retry_after="40",
                endpoint_url="https://api.jobadder.com/v2/candidates",
            ),
        ):
            response = client.get(
                JOBADDER_CANDIDATES_PREVIEW_PATH_TEMPLATE.format(
                    jobadder_account=2236
                )
            )

    assert response.status_code == status.HTTP_502_BAD_GATEWAY

    payload = response.json()

    assert payload["error"]["code"] == "internal_error"
    assert payload["error"]["message"] == "JobAdder candidate read failed."
    assert payload["error"]["details"] == [
        {"jobadder_account": 2236},
        {"provider_status_code": 429},
        {"retry_after_seconds": "40"},
        {"endpoint_url": "https://api.jobadder.com/v2/candidates"},
    ]
