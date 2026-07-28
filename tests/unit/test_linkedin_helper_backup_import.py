"""Tests for controlled native Linked Helper backup import orchestration."""

from backend.services import linkedin_helper_backup_import as subject


def _person_payload(*, source_record_id: str, name: str) -> dict[str, object]:
    return {
        "source_record_id": source_record_id,
        "source_payload": {
            "skills": ["Python"],
            "employment_history": [
                {
                    "title": "Engineer",
                    "company_name": "Acme Ltd",
                    "company_id": "42",
                    "start_year": 2020,
                    "start_month": 2,
                    "end": None,
                    "end_year": None,
                    "end_month": None,
                    "is_default": 1,
                }
            ],
            "source_name_company_count": 1,
        },
        "import_run_id": "test-run",
        "record_kind": "candidate",
        "full_name": name,
        "first_name": name,
        "last_name": None,
        "primary_email": None,
        "primary_phone": None,
        "linkedin_url": f"https://www.linkedin.com/in/{name.casefold()}/",
        "location": None,
        "headline": None,
        "summary": None,
        "company_name": "Acme Ltd",
        "company_domain": None,
        "company_website_url": None,
        "company_linkedin_url": None,
        "role_title": "Engineer",
        "is_current_company": True,
    }


def _company_payload() -> dict[str, object]:
    return {
        "source_record_id": "lhd2-organization:42",
        "source_payload": {
            "original_id": "42",
            "source_name_count": 1,
        },
        "import_run_id": "test-run",
        "name": "Acme Ltd",
        "domain": "acme.test",
        "website_url": "https://acme.test",
        "linkedin_url": "https://www.linkedin.com/company/acme/",
        "industry": None,
        "size_range": "11-50",
        "location": "London",
        "description": None,
        "status": None,
    }


def test_build_import_plan_excludes_ambiguous_people(monkeypatch) -> None:
    people = [
        _person_payload(source_record_id="lhd2-person:1", name="Ada"),
        _person_payload(source_record_id="lhd2-person:2", name="Grace"),
    ]
    monkeypatch.setattr(
        subject,
        "map_linkedin_helper_backup_people",
        lambda *args, **kwargs: people,
    )
    monkeypatch.setattr(
        subject,
        "map_linkedin_helper_backup_companies",
        lambda *args, **kwargs: [_company_payload()],
    )
    people_snapshot = {
        "people": [
            {
                "person_id": "person-a",
                "full_name": "Grace",
                "linkedin_url": "https://www.linkedin.com/in/grace/",
                "company_names": ["Acme Ltd"],
            },
            {
                "person_id": "person-b",
                "full_name": "Grace",
                "linkedin_url": "https://www.linkedin.com/in/grace/",
                "company_names": ["Acme Ltd"],
            },
        ],
        "source_links": [],
    }
    companies_snapshot = {"companies": [], "source_links": []}

    plan = subject.build_linkedin_helper_backup_import_plan(
        content_bytes=b"archive",
        limit=20,
        offset=0,
        people_snapshot=people_snapshot,
        companies_snapshot=companies_snapshot,
        import_run_id="test-run",
    )

    assert plan["people_report"]["new"] == 1
    assert plan["people_report"]["ambiguous"] == 1
    assert len(plan["people"]) == 1
    assert plan["people"][0]["payload"]["full_name"] == "Ada"
    assert plan["people"][0]["employment_history"][0]["start_date"].isoformat() == (
        "2020-02-01"
    )


def test_execute_import_plan_persists_related_context(monkeypatch) -> None:
    person = _person_payload(source_record_id="lhd2-person:1", name="Ada")
    company = _company_payload()
    captured_person_payloads: list[dict[str, object]] = []

    monkeypatch.setattr(
        subject,
        "persist_linkedin_helper_company_snapshot",
        lambda payload, canonical_company_id=None: {
            "company_id": "company-1",
            "source_record_id": "source-company-1",
        },
    )

    def persist_person(payload, **kwargs):
        captured_person_payloads.append(payload)
        return {
            "person_id": "person-1",
            "source_record_id": "source-person-1",
            "employment_role_ids": ["role-1"],
            "person_skill_ids": ["skill-1"],
        }

    monkeypatch.setattr(
        subject,
        "persist_linkedin_helper_person_snapshot",
        persist_person,
    )
    plan = {
        "company_payloads": {"lhd2-organization:42": company},
        "company_decisions": {
            "lhd2-organization:42": {
                "classification": "new",
                "canonical_company_ids": [],
            }
        },
        "company_report": {
            "results": [
                {
                    "source_record_id": "lhd2-organization:42",
                    "classification": "new",
                }
            ]
        },
        "people": [
            {
                "payload": person,
                "canonical_person_id": None,
                "current_company_source_record_id": "lhd2-organization:42",
                "employment_history": [
                    {
                        "company_source_record_id": "lhd2-organization:42",
                        "role_title": "Engineer",
                        "start_date": None,
                        "end_date": None,
                        "is_current": True,
                    }
                ],
            }
        ],
    }

    result = subject.execute_linkedin_helper_backup_import_plan(plan)

    assert result["people_persisted"] == 1
    assert result["companies_persisted"] == 1
    assert result["roles_persisted"] == 1
    assert result["skills_persisted"] == 1
    assert captured_person_payloads[0]["skills"] == ["Python"]
    assert captured_person_payloads[0]["record_kind"] == "candidate"
    assert captured_person_payloads[0]["employment_roles"][0]["company_id"] == (
        "company-1"
    )


def test_build_import_plan_from_mapped_payloads_uses_supplied_rows() -> None:
    person = _person_payload(source_record_id="lhd2-person:1", name="Ada")
    company = _company_payload()

    plan = subject.build_linkedin_helper_import_plan_from_mapped_payloads(
        people=[person],
        all_companies=[company],
        limit=20,
        offset=40,
        people_snapshot={"people": [], "source_links": []},
        companies_snapshot={"companies": [], "source_links": []},
    )

    assert plan["offset"] == 40
    assert plan["people_report"]["new"] == 1
    assert plan["company_report"]["new"] == 1
    assert len(plan["people"]) == 1


def test_build_import_plan_respects_configurable_company_limit() -> None:
    person = _person_payload(source_record_id="lhd2-person:1", name="Ada")
    company = _company_payload()

    try:
        subject.build_linkedin_helper_import_plan_from_mapped_payloads(
            people=[person],
            all_companies=[company],
            limit=20,
            offset=0,
            people_snapshot={"people": [], "source_links": []},
            companies_snapshot={"companies": [], "source_links": []},
            max_related_companies=0,
        )
    except ValueError as exc:
        assert str(exc) == "max_related_companies must be greater than zero."
    else:
        raise AssertionError("Expected invalid company limit to be rejected.")
