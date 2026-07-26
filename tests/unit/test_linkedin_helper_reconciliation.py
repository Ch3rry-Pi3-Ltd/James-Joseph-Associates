"""Tests for read-only Linked Helper identity reconciliation."""

from backend.services.linkedin_helper_reconciliation import (
    build_canonical_company_identity_index,
    build_canonical_identity_index,
    reconcile_linkedin_helper_companies,
    reconcile_linkedin_helper_people,
)


def _canonical_index() -> dict[str, dict[str, set[str]]]:
    return build_canonical_identity_index(
        people=[
            {
                "person_id": "person-1",
                "full_name": "Ada Lovelace",
                "primary_email": "ada@example.com",
                "primary_phone": "+44 7700 900123",
                "linkedin_url": "https://www.linkedin.com/in/ada-lovelace/",
                "company_names": ["Analytical Engines Ltd"],
            },
            {
                "person_id": "person-2",
                "full_name": "Grace Hopper",
                "primary_email": "grace@example.com",
                "primary_phone": None,
                "linkedin_url": None,
                "company_names": ["US Navy"],
            },
        ],
        source_links=[
            {
                "source_record_id": "lhd2-person:existing",
                "person_id": "person-2",
            }
        ],
    )


def _payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "source_record_id": "lhd2-person:new",
        "source_payload": {"public_identifiers": []},
        "full_name": "New Person",
        "primary_email": None,
        "primary_phone": None,
        "linkedin_url": None,
        "company_name": "New Company",
    }
    payload.update(overrides)
    return payload


def test_reconciliation_prefers_existing_source_link() -> None:
    report = reconcile_linkedin_helper_people(
        payloads=[
            _payload(
                source_record_id="lhd2-person:existing",
                full_name="Grace Hopper",
            )
        ],
        canonical_index=_canonical_index(),
    )

    assert report["matched"] == 1
    assert report["results"][0]["canonical_person_ids"] == ["person-2"]
    assert report["results"][0]["match_method"] == "existing_source_link"


def test_reconciliation_matches_linkedin_and_unique_name_company() -> None:
    report = reconcile_linkedin_helper_people(
        payloads=[
            _payload(
                linkedin_url="https://uk.linkedin.com/in/ADA-LOVELACE/",
                full_name="Ada Lovelace",
                company_name="Analytical Engines Ltd",
            ),
            _payload(
                source_record_id="lhd2-person:grace",
                full_name="Grace Hopper",
                company_name="US Navy",
            ),
        ],
        canonical_index=_canonical_index(),
    )

    assert report["matched"] == 2
    assert report["results"][0]["match_method"] == "linkedin_profile"
    assert report["results"][1]["match_method"] == "name_and_company"


def test_reconciliation_marks_conflicting_deterministic_signals_ambiguous() -> None:
    report = reconcile_linkedin_helper_people(
        payloads=[
            _payload(
                full_name="Ada Lovelace",
                primary_email="grace@example.com",
                linkedin_url="https://www.linkedin.com/in/ada-lovelace/",
                company_name="Analytical Engines Ltd",
            )
        ],
        canonical_index=_canonical_index(),
    )

    assert report["ambiguous"] == 1
    assert report["results"][0]["reason"] == "conflicting_deterministic_signals"
    assert report["results"][0]["canonical_person_ids"] == ["person-1", "person-2"]


def test_reconciliation_keeps_name_only_matches_for_review() -> None:
    report = reconcile_linkedin_helper_people(
        payloads=[
            _payload(
                full_name="Ada Lovelace",
                company_name=None,
            )
        ],
        canonical_index=_canonical_index(),
    )

    assert report["ambiguous"] == 1
    assert report["results"][0]["reason"] == "name_only_review_candidate"


def test_reconciliation_distinguishes_new_and_unusable_rows() -> None:
    report = reconcile_linkedin_helper_people(
        payloads=[
            _payload(full_name="Katherine Johnson"),
            _payload(
                source_record_id=None,
                full_name=None,
                company_name=None,
            ),
        ],
        canonical_index=_canonical_index(),
    )

    assert report["new"] == 1
    assert report["skipped"] == 1
    assert report["results"][1]["reason"] == "missing_usable_identity"


def test_duplicate_source_name_company_is_not_used_as_deterministic_match() -> None:
    report = reconcile_linkedin_helper_people(
        payloads=[
            _payload(
                source_record_id="lhd2-person:ada-1",
                full_name="Ada Lovelace",
                company_name="Analytical Engines Ltd",
            ),
            _payload(
                source_record_id="lhd2-person:ada-2",
                full_name="Ada Lovelace",
                company_name="Analytical Engines Ltd",
            ),
        ],
        canonical_index=_canonical_index(),
    )

    assert report["ambiguous"] == 2
    assert all(
        result["reason"] == "name_only_review_candidate"
        for result in report["results"]
    )


def test_full_backup_person_identity_count_overrides_bounded_sample() -> None:
    report = reconcile_linkedin_helper_people(
        payloads=[
            _payload(
                full_name="Ada Lovelace",
                company_name="Analytical Engines Ltd",
                source_payload={
                    "public_identifiers": [],
                    "source_name_company_count": 2,
                },
            )
        ],
        canonical_index=_canonical_index(),
    )

    assert report["matched"] == 0
    assert report["ambiguous"] == 1
    assert report["results"][0]["reason"] == "name_only_review_candidate"


def _canonical_company_index() -> dict[str, dict[str, set[str]]]:
    return build_canonical_company_identity_index(
        companies=[
            {
                "company_id": "company-1",
                "name": "Analytical Engines Ltd",
                "domain": "example.com",
                "website_url": "https://www.example.com/about",
                "linkedin_url": (
                    "https://www.linkedin.com/company/analytical-engines/"
                ),
            },
            {
                "company_id": "company-2",
                "name": "US Navy",
                "domain": "navy.example",
                "website_url": None,
                "linkedin_url": None,
            },
        ],
        source_links=[
            {
                "source_record_id": "lhd2-organization:existing",
                "company_id": "company-2",
            }
        ],
    )


def _company_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "source_record_id": "lhd2-organization:new",
        "source_payload": {
            "public_identifiers": [],
            "company_identifiers": [],
        },
        "name": "New Company",
        "domain": None,
        "website_url": None,
        "linkedin_url": None,
    }
    payload.update(overrides)
    return payload


def test_company_reconciliation_prefers_existing_source_link() -> None:
    report = reconcile_linkedin_helper_companies(
        payloads=[
            _company_payload(
                source_record_id="lhd2-organization:existing",
                name="US Navy",
            )
        ],
        canonical_index=_canonical_company_index(),
    )

    assert report["matched"] == 1
    assert report["results"][0]["canonical_company_ids"] == ["company-2"]
    assert report["results"][0]["match_method"] == "existing_source_link"


def test_company_reconciliation_matches_linkedin_domain_and_unique_name() -> None:
    report = reconcile_linkedin_helper_companies(
        payloads=[
            _company_payload(
                name="Analytical Engines Ltd",
                linkedin_url=(
                    "https://uk.linkedin.com/company/ANALYTICAL-ENGINES/"
                ),
            ),
            _company_payload(
                source_record_id="lhd2-organization:domain",
                name="Different Trading Name",
                website_url="https://www.navy.example/contact",
            ),
            _company_payload(
                source_record_id="lhd2-organization:name",
                name="US Navy",
            ),
        ],
        canonical_index=_canonical_company_index(),
    )

    assert report["matched"] == 3
    assert report["results"][0]["match_method"] == "linkedin_company"
    assert report["results"][1]["match_method"] == "domain"
    assert report["results"][2]["match_method"] == "name"


def test_company_reconciliation_marks_conflicting_signals_ambiguous() -> None:
    report = reconcile_linkedin_helper_companies(
        payloads=[
            _company_payload(
                name="Analytical Engines Ltd",
                linkedin_url=(
                    "https://www.linkedin.com/company/analytical-engines/"
                ),
                domain="navy.example",
            )
        ],
        canonical_index=_canonical_company_index(),
    )

    assert report["ambiguous"] == 1
    assert report["results"][0]["reason"] == "conflicting_deterministic_signals"
    assert report["results"][0]["canonical_company_ids"] == [
        "company-1",
        "company-2",
    ]


def test_duplicate_source_company_name_is_review_only() -> None:
    report = reconcile_linkedin_helper_companies(
        payloads=[
            _company_payload(
                source_record_id="lhd2-organization:navy-1",
                name="US Navy",
            ),
            _company_payload(
                source_record_id="lhd2-organization:navy-2",
                name="US Navy",
            ),
        ],
        canonical_index=_canonical_company_index(),
    )

    assert report["ambiguous"] == 2
    assert all(
        result["reason"] == "name_only_review_candidate"
        for result in report["results"]
    )


def test_full_backup_company_name_count_overrides_bounded_sample() -> None:
    report = reconcile_linkedin_helper_companies(
        payloads=[
            _company_payload(
                name="Analytical Engines Ltd",
                source_payload={
                    "public_identifiers": [],
                    "company_identifiers": [],
                    "source_name_count": 2,
                },
            )
        ],
        canonical_index=_canonical_company_index(),
    )

    assert report["matched"] == 0
    assert report["ambiguous"] == 1
    assert report["results"][0]["reason"] == "name_only_review_candidate"


def test_company_reconciliation_distinguishes_new_and_unusable_rows() -> None:
    report = reconcile_linkedin_helper_companies(
        payloads=[
            _company_payload(name="NewCo"),
            _company_payload(source_record_id=None, name=None),
        ],
        canonical_index=_canonical_company_index(),
    )

    assert report["new"] == 1
    assert report["skipped"] == 1
