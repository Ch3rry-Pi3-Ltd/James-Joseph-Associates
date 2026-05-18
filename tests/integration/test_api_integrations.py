"""
Integration tests for JobAdder-facing API routes.

These tests verify the real FastAPI route wiring for:

    GET /api/v1/integrations/jobadder/authorize
    GET /api/v1/integrations/jobadder/callback
    GET /api/v1/integrations/jobadder/accounts/{jobadder_account}/applications-preview
    GET /api/v1/integrations/jobadder/accounts/{jobadder_account}/jobads-preview
    GET /api/v1/integrations/jobadder/accounts/{jobadder_account}/jobads/{ad_id}/applications-preview
    GET /api/v1/integrations/jobadder/accounts/{jobadder_account}/candidates-preview
    GET /api/v1/integrations/jobadder/accounts/{jobadder_account}/candidates/{candidate_id}
    GET /api/v1/integrations/jobadder/accounts/{jobadder_account}/candidates/{candidate_id}/notes
    GET /api/v1/integrations/jobadder/accounts/{jobadder_account}/candidates/{candidate_id}/skills

The important question is:

    "Does the backend expose real JobAdder integration routes that behave
    clearly during setup and read operations?"

That matters because:

- the callback URI must be registered exactly in the JobAdder developer portal
- the OAuth setup routes need to point at live backend logic rather than
  invented placeholder paths
- the authenticated read routes need to turn stored JobAdder credentials into
  predictable API responses for the rest of the product

In plain language:

- prove the authorisation URL route exists
- prove the callback route exists
- prove the authenticated candidate read routes are wired correctly
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
JOBADDER_APPLICATIONS_PREVIEW_PATH_TEMPLATE = (
    "/api/v1/integrations/jobadder/accounts/{jobadder_account}/applications-preview"
)
JOBADDER_JOBADS_PREVIEW_PATH_TEMPLATE = (
    "/api/v1/integrations/jobadder/accounts/{jobadder_account}/jobads-preview"
)
JOBADDER_JOBAD_APPLICATIONS_PREVIEW_PATH_TEMPLATE = (
    "/api/v1/integrations/jobadder/accounts/{jobadder_account}/jobads/{ad_id}/applications-preview"
)
JOBADDER_CANDIDATES_PREVIEW_PATH_TEMPLATE = (
    "/api/v1/integrations/jobadder/accounts/{jobadder_account}/candidates-preview"
)
JOBADDER_CANDIDATE_DETAIL_PATH_TEMPLATE = (
    "/api/v1/integrations/jobadder/accounts/{jobadder_account}/candidates/{candidate_id}"
)
JOBADDER_CANDIDATE_NOTES_PATH_TEMPLATE = (
    "/api/v1/integrations/jobadder/accounts/{jobadder_account}/candidates/{candidate_id}/notes"
)
JOBADDER_CANDIDATE_SKILLS_PATH_TEMPLATE = (
    "/api/v1/integrations/jobadder/accounts/{jobadder_account}/candidates/{candidate_id}/skills"
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


def test_jobadder_applications_preview_returns_first_page_preview_successfully() -> None:
    """
    Verify that the generic applications preview route returns a bounded first
    page from the shared authenticated-read path.
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
            {"applicationId": 701, "status": "Active"},
            {"applicationId": 702, "status": "Rejected"},
        ],
        "item_count": 2,
        "total_count": 20,
        "links": {
            "first": "https://api.jobadder.com/v2/applications?page=1",
        },
        "endpoint_url": "https://api.jobadder.com/v2/applications",
        "raw_payload": {},
    }

    with patch(
        "backend.api.v1.integrations.get_jobadder_oauth_connection",
        return_value=fake_connection,
    ) as mock_get_connection:
        with patch(
            "backend.api.v1.integrations.fetch_jobadder_applications_preview",
            return_value=fake_preview,
        ) as mock_fetch_preview:
            response = client.get(
                JOBADDER_APPLICATIONS_PREVIEW_PATH_TEMPLATE.format(
                    jobadder_account=2236
                )
                + "?active_only=true"
            )

    assert response.status_code == status.HTTP_200_OK

    payload = response.json()

    assert payload["jobadder_account"] == 2236
    assert payload["jobadder_instance"] == "eu2"
    assert payload["api_url"] == "https://api.jobadder.com"
    assert payload["active_only"] is True
    assert payload["rejected_only"] is False
    assert payload["item_count"] == 2
    assert payload["total_count"] == 20
    assert payload["applications"] == [
        {"applicationId": 701, "status": "Active"},
        {"applicationId": 702, "status": "Rejected"},
    ]

    mock_get_connection.assert_called_once_with(2236)
    mock_fetch_preview.assert_called_once_with(
        api_url="https://api.jobadder.com",
        access_token="jobadder-access-token",
        item_limit=10,
        active_only=True,
        rejected_only=False,
    )


def test_jobadder_applications_preview_rejects_mutually_exclusive_filters() -> None:
    """
    Verify that the route rejects `active_only` and `rejected_only` together.
    """

    client = TestClient(create_app())

    response = client.get(
        JOBADDER_APPLICATIONS_PREVIEW_PATH_TEMPLATE.format(jobadder_account=2236)
        + "?active_only=true&rejected_only=true"
    )

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT

    payload = response.json()
    assert payload["error"]["code"] == "validation_error"
    assert "cannot request both active_only and rejected_only" in payload["error"][
        "message"
    ]


def test_jobadder_jobads_preview_returns_first_page_preview_successfully() -> None:
    """
    Verify that the job-ad preview route returns a small first-page JobAdder
    job-ad preview through the shared authenticated-read path.
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
            {"adId": 101, "title": "Platform Engineer"},
            {"adId": 102, "title": "Data Engineer"},
        ],
        "item_count": 2,
        "total_count": 8,
        "links": {
            "first": "https://api.jobadder.com/v2/jobads?page=1",
        },
        "endpoint_url": "https://api.jobadder.com/v2/jobads",
        "raw_payload": {},
    }

    with patch(
        "backend.api.v1.integrations.get_jobadder_oauth_connection",
        return_value=fake_connection,
    ) as mock_get_connection:
        with patch(
            "backend.api.v1.integrations.fetch_jobadder_jobads_preview",
            return_value=fake_preview,
        ) as mock_fetch_preview:
            response = client.get(
                JOBADDER_JOBADS_PREVIEW_PATH_TEMPLATE.format(jobadder_account=2236)
            )

    assert response.status_code == status.HTTP_200_OK

    payload = response.json()

    assert payload["jobadder_account"] == 2236
    assert payload["jobadder_instance"] == "eu2"
    assert payload["api_url"] == "https://api.jobadder.com"
    assert payload["item_count"] == 2
    assert payload["total_count"] == 8
    assert payload["links"] == {
        "first": "https://api.jobadder.com/v2/jobads?page=1",
    }
    assert payload["jobads"] == [
        {"adId": 101, "title": "Platform Engineer"},
        {"adId": 102, "title": "Data Engineer"},
    ]

    mock_get_connection.assert_called_once_with(2236)
    mock_fetch_preview.assert_called_once_with(
        api_url="https://api.jobadder.com",
        access_token="jobadder-access-token",
        item_limit=10,
    )


def test_jobadder_jobad_applications_preview_returns_first_page_successfully() -> None:
    """
    Verify that the job-ad applications preview route returns a bounded
    applications list for one JobAdder ad.
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
            {"applicationId": 501, "status": "Active"},
            {"applicationId": 502, "status": "Active"},
        ],
        "item_count": 2,
        "total_count": 12,
        "links": {
            "first": "https://api.jobadder.com/v2/jobads/101/applications/active?page=1",
        },
        "endpoint_url": "https://api.jobadder.com/v2/jobads/101/applications/active",
        "raw_payload": {},
    }

    with patch(
        "backend.api.v1.integrations.get_jobadder_oauth_connection",
        return_value=fake_connection,
    ) as mock_get_connection:
        with patch(
            "backend.api.v1.integrations.fetch_jobadder_jobad_applications_preview",
            return_value=fake_preview,
        ) as mock_fetch_preview:
            response = client.get(
                JOBADDER_JOBAD_APPLICATIONS_PREVIEW_PATH_TEMPLATE.format(
                    jobadder_account=2236,
                    ad_id=101,
                )
                + "?active_only=true"
            )

    assert response.status_code == status.HTTP_200_OK

    payload = response.json()

    assert payload["jobadder_account"] == 2236
    assert payload["jobadder_instance"] == "eu2"
    assert payload["api_url"] == "https://api.jobadder.com"
    assert payload["ad_id"] == 101
    assert payload["active_only"] is True
    assert payload["item_count"] == 2
    assert payload["total_count"] == 12
    assert payload["links"] == {
        "first": "https://api.jobadder.com/v2/jobads/101/applications/active?page=1",
    }
    assert payload["applications"] == [
        {"applicationId": 501, "status": "Active"},
        {"applicationId": 502, "status": "Active"},
    ]

    mock_get_connection.assert_called_once_with(2236)
    mock_fetch_preview.assert_called_once_with(
        api_url="https://api.jobadder.com",
        access_token="jobadder-access-token",
        ad_id=101,
        item_limit=10,
        active_only=True,
    )


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


def test_jobadder_candidate_detail_returns_full_candidate_successfully() -> None:
    """
    Verify that the candidate-detail route returns one full candidate payload
    from the JobAdder API helper.

    In plain language:

    - pretend the stored JobAdder connection exists
    - pretend the provider helper returned one full candidate object
    - confirm the route returns that object in the expected typed response
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

    fake_candidate_detail = {
        "candidate": {
            "candidateId": 13812978,
            "firstName": "Tom",
            "lastName": "Owens",
            "email": "tom@example.com",
        },
        "endpoint_url": "https://api.jobadder.com/v2/candidates/13812978",
        "raw_payload": {},
    }

    with patch(
        "backend.api.v1.integrations.get_jobadder_oauth_connection",
        return_value=fake_connection,
    ):
        with patch(
            "backend.api.v1.integrations.fetch_jobadder_candidate_detail",
            return_value=fake_candidate_detail,
        ) as mock_fetch_detail:
            response = client.get(
                JOBADDER_CANDIDATE_DETAIL_PATH_TEMPLATE.format(
                    jobadder_account=2236,
                    candidate_id=13812978,
                )
            )

    assert response.status_code == status.HTTP_200_OK

    payload = response.json()

    assert payload["jobadder_account"] == 2236
    assert payload["jobadder_instance"] == "eu2"
    assert payload["api_url"] == "https://api.jobadder.com"
    assert payload["candidate_id"] == 13812978
    assert payload["candidate"] == {
        "candidateId": 13812978,
        "firstName": "Tom",
        "lastName": "Owens",
        "email": "tom@example.com",
    }

    mock_fetch_detail.assert_called_once_with(
        api_url="https://api.jobadder.com",
        access_token="jobadder-access-token",
        candidate_id=13812978,
    )


def test_jobadder_candidate_notes_returns_notes_successfully() -> None:
    """
    Verify that the candidate-notes route returns the dedicated JobAdder notes
    payload cleanly.

    Notes
    -----
    - This is the route-level proof that the backend can pull real candidate
      notes rather than only exposing the notes link from the candidate record.
    - The route still relies on mocks here because the purpose of this test is
      FastAPI wiring and response contract behaviour, not live provider I/O.

    Example
    -------
    We simulate:

    - a stored JobAdder connection
    - a provider helper returning one candidate note

    and confirm the route exposes:

    - account context
    - candidate ID
    - note count
    - the notes list itself

    In plain language:

    - pretend the candidate notes read succeeded
    - confirm the route returns the expected typed wrapper
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

    fake_notes = {
        "notes": [
            {
                "noteId": "11111111-1111-1111-1111-111111111111",
                "type": "General",
                "textPartial": "Candidate called back",
                "text": "Candidate called back and is available next Tuesday.",
                "createdAt": "2026-04-30T10:00:00Z",
            }
        ],
        "note_count": 1,
        "total_count": 1,
        "links": {
            "self": "https://api.jobadder.com/v2/candidates/13812978/notes"
        },
        "endpoint_url": "https://api.jobadder.com/v2/candidates/13812978/notes",
        "raw_payload": {},
    }

    with patch(
        "backend.api.v1.integrations.get_jobadder_oauth_connection",
        return_value=fake_connection,
    ):
        with patch(
            "backend.api.v1.integrations.fetch_jobadder_candidate_notes",
            return_value=fake_notes,
        ) as mock_fetch_notes:
            response = client.get(
                JOBADDER_CANDIDATE_NOTES_PATH_TEMPLATE.format(
                    jobadder_account=2236,
                    candidate_id=13812978,
                )
            )

    assert response.status_code == status.HTTP_200_OK

    payload = response.json()

    assert payload["jobadder_account"] == 2236
    assert payload["jobadder_instance"] == "eu2"
    assert payload["api_url"] == "https://api.jobadder.com"
    assert payload["candidate_id"] == 13812978
    assert payload["note_count"] == 1
    assert payload["total_count"] == 1
    assert payload["links"] == {
        "self": "https://api.jobadder.com/v2/candidates/13812978/notes"
    }
    assert payload["notes"] == [
        {
            "noteId": "11111111-1111-1111-1111-111111111111",
            "type": "General",
            "textPartial": "Candidate called back",
            "text": "Candidate called back and is available next Tuesday.",
            "createdAt": "2026-04-30T10:00:00Z",
        }
    ]

    mock_fetch_notes.assert_called_once_with(
        api_url="https://api.jobadder.com",
        access_token="jobadder-access-token",
        candidate_id=13812978,
        item_limit=25,
    )


def test_jobadder_candidate_skills_returns_structured_skills_successfully() -> None:
    """
    Verify that the candidate-skills route returns the structured skills tree
    from the JobAdder API helper.

    In plain language:

    - pretend the stored JobAdder connection exists
    - pretend the provider helper returned one category tree
    - confirm the route exposes that structure cleanly
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

    fake_skills = {
        "categories": [
            {
                "categoryId": 1,
                "name": "Engineering",
                "subCategories": [
                    {
                        "subCategoryId": 2,
                        "name": "Backend",
                        "skills": [{"skillId": 3, "name": "Python"}],
                    }
                ],
            }
        ],
        "category_count": 1,
        "links": {},
        "endpoint_url": "https://api.jobadder.com/v2/candidates/13812978/skills",
        "raw_payload": {},
    }

    with patch(
        "backend.api.v1.integrations.get_jobadder_oauth_connection",
        return_value=fake_connection,
    ):
        with patch(
            "backend.api.v1.integrations.fetch_jobadder_candidate_skills",
            return_value=fake_skills,
        ) as mock_fetch_skills:
            response = client.get(
                JOBADDER_CANDIDATE_SKILLS_PATH_TEMPLATE.format(
                    jobadder_account=2236,
                    candidate_id=13812978,
                )
            )

    assert response.status_code == status.HTTP_200_OK

    payload = response.json()

    assert payload["jobadder_account"] == 2236
    assert payload["jobadder_instance"] == "eu2"
    assert payload["api_url"] == "https://api.jobadder.com"
    assert payload["candidate_id"] == 13812978
    assert payload["category_count"] == 1
    assert payload["categories"] == [
        {
            "categoryId": 1,
            "name": "Engineering",
            "subCategories": [
                {
                    "subCategoryId": 2,
                    "name": "Backend",
                    "skills": [{"skillId": 3, "name": "Python"}],
                }
            ],
        }
    ]

    mock_fetch_skills.assert_called_once_with(
        api_url="https://api.jobadder.com",
        access_token="jobadder-access-token",
        candidate_id=13812978,
    )
