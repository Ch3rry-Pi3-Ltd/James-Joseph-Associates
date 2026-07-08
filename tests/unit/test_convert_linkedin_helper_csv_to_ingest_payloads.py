"""
Unit tests for Linked Helper CSV conversion helpers.
"""

from scripts.convert_linkedin_helper_csv_to_ingest_payloads import (
    build_payload_from_row,
    normalize_header,
)


def test_normalize_header_collapses_spacing_and_case() -> None:
    """
    Verify that CSV headers are normalized for loose alias matching.
    """

    assert normalize_header(" LinkedIn URL ") == "linkedin url"
    assert normalize_header("Current-Company_Name") == "current company name"


def test_build_payload_from_row_maps_common_linkedin_helper_columns() -> None:
    """
    Verify that one CSV row maps into the backend ingest payload shape.
    """

    row = {
        "Name": "Sarah Jones",
        "Email Address": "sarah@acme.test",
        "Profile URL": "https://www.linkedin.com/in/sarah-jones/",
        "Company": "Acme Hiring Ltd",
        "Job Title": "Head of Data",
    }
    normalized_header_map = {
        normalize_header(header): header
        for header in row
    }

    payload = build_payload_from_row(
        row=row,
        normalized_header_map=normalized_header_map,
        row_index=0,
        default_record_kind="hiring_manager",
        contact_type_override=None,
        is_hiring_manager=True,
    )

    assert payload["record_kind"] == "hiring_manager"
    assert payload["full_name"] == "Sarah Jones"
    assert payload["primary_email"] == "sarah@acme.test"
    assert payload["linkedin_url"] == "https://www.linkedin.com/in/sarah-jones/"
    assert payload["company_name"] == "Acme Hiring Ltd"
    assert payload["role_title"] == "Head of Data"
    assert payload["contact_type"] == "hiring_manager"
    assert payload["is_hiring_manager"] is True
