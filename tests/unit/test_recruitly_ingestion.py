from backend.services.recruitly_ingestion import (
    build_recruitly_company_persistence_payload,
    build_recruitly_contact_persistence_payload,
)


def test_build_recruitly_company_persistence_payload_maps_live_shape() -> None:
    payload = {
        "id": "company-1",
        "name": "GridBeyond",
        "website": "https://gridbeyond.com",
        "sectorName": "Renewable Energy",
        "location": "Dublin 24, Ireland",
        "statusName": "Active",
        "createdOn": "01/07/2026 18:38:09",
        "updatedOn": "01/07/2026 18:53:33",
    }

    persistence_payload = build_recruitly_company_persistence_payload(
        payload,
        import_run_id="run-1",
    )

    assert persistence_payload["source_record_id"] == "company-1"
    assert persistence_payload["import_run_id"] == "run-1"
    assert persistence_payload["company_name"] == "GridBeyond"
    assert persistence_payload["company_domain"] == "gridbeyond.com"
    assert persistence_payload["company_website_url"] == "https://gridbeyond.com"
    assert persistence_payload["industry"] == "Renewable Energy"
    assert persistence_payload["location"] == "Dublin 24, Ireland"
    assert persistence_payload["status"] == "Active"
    assert persistence_payload["created_at"].isoformat() == "2026-07-01T18:38:09+00:00"
    assert persistence_payload["updated_at"].isoformat() == "2026-07-01T18:53:33+00:00"


def test_build_recruitly_contact_persistence_payload_maps_live_shape() -> None:
    payload = {
        "id": "contact-1",
        "firstName": "Aidan",
        "lastName": "Downes",
        "email": "aidand107@gmail.com",
        "alternateEmail": "",
        "mobile": "+353873642603",
        "workPhone": "",
        "jobTitle": "Delivering Demand Side Response Services Globally",
        "linkedIn": "https://www.linkedin.com/in/aidan-downes-4ba2b340/",
        "location": "Dublin 24, Ireland",
        "companyId": "company-1",
        "companyName": "GridBeyond",
        "description": "Relationship note",
    }

    persistence_payload = build_recruitly_contact_persistence_payload(
        payload,
        import_run_id="run-2",
    )

    assert persistence_payload["source_record_id"] == "contact-1"
    assert persistence_payload["import_run_id"] == "run-2"
    assert persistence_payload["company_source_record_id"] == "company-1"
    assert persistence_payload["company_name"] == "GridBeyond"
    assert persistence_payload["full_name"] == "Aidan Downes"
    assert persistence_payload["primary_email"] == "aidand107@gmail.com"
    assert persistence_payload["primary_phone"] == "+353873642603"
    assert persistence_payload["linkedin_url"] == (
        "https://www.linkedin.com/in/aidan-downes-4ba2b340/"
    )
    assert persistence_payload["headline"] == "Delivering Demand Side Response Services Globally"
    assert persistence_payload["summary"] == "Relationship note"
    assert persistence_payload["role_title"] == "Delivering Demand Side Response Services Globally"
    assert persistence_payload["contact_type"] == "client_contact"
    assert persistence_payload["is_current_company"] is True
