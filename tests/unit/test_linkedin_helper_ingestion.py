"""
Unit tests for Linked Helper ingestion helpers.
"""

from backend.services.linkedin_helper_ingestion import (
    build_linkedin_helper_person_persistence_payload,
)


def test_build_linkedin_helper_person_persistence_payload_defaults_contact_type() -> None:
    """
    Verify that hiring-manager rows get sensible normalized defaults.
    """

    payload = build_linkedin_helper_person_persistence_payload(
        {
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
        }
    )

    assert payload["record_kind"] == "hiring_manager"
    assert payload["contact_type"] == "hiring_manager"
    assert payload["is_hiring_manager"] is True
    assert payload["full_name"] == "Sarah Jones"
    assert payload["source_record_id"] is not None
    assert payload["source_payload_hash"]


def test_build_linkedin_helper_person_persistence_payload_builds_name_from_parts() -> None:
    """
    Verify that a missing full_name is built from first/last-name parts.
    """

    payload = build_linkedin_helper_person_persistence_payload(
        {
            "source_payload": {"row": 7},
            "record_kind": "candidate",
            "first_name": "Roger",
            "last_name": "Campbell",
            "primary_email": "roger@example.com",
        }
    )

    assert payload["full_name"] == "Roger Campbell"
    assert payload["contact_type"] is None
    assert payload["source_record_id"] is not None
