"""
Integration tests for Linked Helper integration routes.
"""

from collections.abc import Iterator
from unittest.mock import patch

import pytest
from fastapi import status
from fastapi.testclient import TestClient

from backend.main import create_app
from backend.settings import get_settings

LINKED_HELPER_INGEST_PATH = "/api/v1/integrations/linkedin-helper/admin/ingest-person"


@pytest.fixture(autouse=True)
def clear_settings_cache() -> Iterator[None]:
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def create_test_client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("MAKE_API_TOKEN", "test-admin-token")
    return TestClient(create_app())


def test_linkedin_helper_ingest_requires_valid_bearer_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    Verify that the protected Linked Helper ingest route rejects missing auth.
    """

    client = create_test_client(monkeypatch)

    response = client.post(
        LINKED_HELPER_INGEST_PATH,
        json={
            "source_payload": {"profileUrl": "https://www.linkedin.com/in/sarah-jones/"},
            "record_kind": "hiring_manager",
            "full_name": "Sarah Jones",
        },
    )

    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    assert response.json()["error"]["code"] == "unauthorized"


def test_linkedin_helper_ingest_runs_successfully(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    Verify that the protected Linked Helper ingest route delegates cleanly.
    """

    client = create_test_client(monkeypatch)

    fake_persisted = {
        "source_record_id": "source-1",
        "person_id": "person-1",
        "company_id": "company-1",
        "contact_id": "contact-1",
        "candidate_id": None,
        "person_company_role_id": "role-1",
        "record_kind": "hiring_manager",
    }

    with patch(
        "backend.api.v1.integrations.ingest_linkedin_helper_person",
        return_value=fake_persisted,
    ) as mock_ingest_linkedin_helper_person:
        response = client.post(
            LINKED_HELPER_INGEST_PATH,
            headers={"Authorization": "Bearer test-admin-token"},
            json={
                "source_payload": {
                    "profileUrl": "https://www.linkedin.com/in/sarah-jones/",
                    "company": "Acme Hiring Ltd",
                },
                "record_kind": "hiring_manager",
                "full_name": "Sarah Jones",
                "primary_email": "sarah@acme.test",
                "linkedin_url": "https://www.linkedin.com/in/sarah-jones/",
                "company_name": "Acme Hiring Ltd",
                "role_title": "Head of Data",
            },
        )

    assert response.status_code == status.HTTP_200_OK
    payload = response.json()
    assert payload["status"] == "completed"
    assert payload["persisted"]["person_id"] == "person-1"
    mock_ingest_linkedin_helper_person.assert_called_once()


def test_linkedin_helper_ingest_returns_bad_gateway_for_persistence_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    Verify that service-layer failures become standard API errors.
    """

    client = create_test_client(monkeypatch)

    with patch(
        "backend.api.v1.integrations.ingest_linkedin_helper_person",
        side_effect=RuntimeError("Company row could not be resolved."),
    ):
        response = client.post(
            LINKED_HELPER_INGEST_PATH,
            headers={"Authorization": "Bearer test-admin-token"},
            json={
                "source_payload": {"profileUrl": "https://www.linkedin.com/in/sarah-jones/"},
                "record_kind": "hiring_manager",
                "full_name": "Sarah Jones",
            },
        )

    assert response.status_code == status.HTTP_502_BAD_GATEWAY
    payload = response.json()
    assert payload["error"]["code"] == "integration_connection_invalid"
    assert payload["error"]["message"] == "Linked Helper person ingest failed."
