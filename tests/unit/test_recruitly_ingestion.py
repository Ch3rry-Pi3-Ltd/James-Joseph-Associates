from backend.services.recruitly_ingestion import (
    build_recruitly_company_persistence_payload,
    build_recruitly_contact_persistence_payload,
    build_recruitly_job_persistence_payload,
    build_recruitly_journal_persistence_payload,
    build_recruitly_opportunity_persistence_payload,
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


def test_build_recruitly_job_persistence_payload_maps_live_shape() -> None:
    payload = {
        "id": "job-1",
        "reference": "JB-1",
        "title": "Senior Data Engineer",
        "internalDescription": "Build modern data pipelines",
        "companyId": "company-1",
        "companyName": "Acme Hiring Ltd",
        "contactId": "contact-1",
        "location": "London, United Kingdom",
        "remoteWorking": True,
        "employmentTypeName": "Permanent",
        "minPay": 125000,
        "maxPay": 150000,
        "payCurrency": "GBP",
        "statusName": "Open",
        "dateOpened": "04/06/2026 09:43:29",
        "updatedOn": "08/07/2026 16:25:02",
    }

    persistence_payload = build_recruitly_job_persistence_payload(
        payload,
        import_run_id="run-3",
    )

    assert persistence_payload["source_record_id"] == "job-1"
    assert persistence_payload["import_run_id"] == "run-3"
    assert persistence_payload["company_source_record_id"] == "company-1"
    assert persistence_payload["contact_source_record_id"] == "contact-1"
    assert persistence_payload["company_name"] == "Acme Hiring Ltd"
    assert persistence_payload["title"] == "Senior Data Engineer"
    assert persistence_payload["description"] == "Build modern data pipelines"
    assert persistence_payload["location"] == "London, United Kingdom"
    assert persistence_payload["workplace_type"] == "remote"
    assert persistence_payload["employment_type"] == "Permanent"
    assert persistence_payload["salary_min"] == 125000.0
    assert persistence_payload["salary_max"] == 150000.0
    assert persistence_payload["currency"] == "GBP"
    assert persistence_payload["status"] == "Open"
    assert persistence_payload["opened_at"].isoformat() == "2026-06-04T09:43:29+00:00"
    assert (
        persistence_payload["updated_from_source_at"].isoformat()
        == "2026-07-08T16:25:02+00:00"
    )


def test_build_recruitly_opportunity_persistence_payload_maps_live_shape() -> None:
    payload = {
        "id": "opp-1",
        "name": "Data Platform Expansion",
        "reference": "OP-1",
        "description": "Strategic expansion of the data platform",
        "companyId": "company-1",
        "companyName": "Acme Hiring Ltd",
        "contactId": "contact-1",
        "stateName": "Qualified",
        "forecastedClosingDate": "2026-09-01",
        "updatedOn": "04/07/2026 11:15:12",
        "bidValue": 250000,
    }

    persistence_payload = build_recruitly_opportunity_persistence_payload(
        payload,
        import_run_id="run-4",
    )

    assert persistence_payload["source_record_id"] == "opp-1"
    assert persistence_payload["import_run_id"] == "run-4"
    assert persistence_payload["company_source_record_id"] == "company-1"
    assert persistence_payload["contact_source_record_id"] == "contact-1"
    assert persistence_payload["company_name"] == "Acme Hiring Ltd"
    assert persistence_payload["title"] == "Data Platform Expansion"
    assert persistence_payload["smart_summary"] == "Strategic expansion of the data platform"
    assert persistence_payload["stage"] == "Qualified"
    assert persistence_payload["last_contact_at"].isoformat() == "2026-07-04T11:15:12+00:00"
    assert persistence_payload["next_task_at"].isoformat() == "2026-09-01T00:00:00+00:00"
    assert persistence_payload["value"] == 250000.0


def test_build_recruitly_journal_persistence_payload_maps_generic_rows() -> None:
    entries = [
        {
            "id": "journal-1",
            "subject": "Candidate call",
            "description": "Discussed availability and salary expectations.",
            "createdOn": "05/07/2026 10:30:00",
        }
    ]

    persistence_payload = build_recruitly_journal_persistence_payload(
        entries,
        record_type="contact",
        record_source_record_id="contact-1",
        import_run_id="run-5",
    )

    assert persistence_payload["record_type"] == "contact"
    assert persistence_payload["record_source_record_id"] == "contact-1"
    assert persistence_payload["import_run_id"] == "run-5"
    assert len(persistence_payload["entries"]) == 1
    entry = persistence_payload["entries"][0]
    assert entry["source_record_id"] == "journal-1"
    assert entry["interaction_type"] == "recruitly_contact_journal_entry"
    assert entry["subject"] == "Candidate call"
    assert entry["body"] == "Discussed availability and salary expectations."
    assert entry["occurred_at"].isoformat() == "2026-07-05T10:30:00+00:00"
