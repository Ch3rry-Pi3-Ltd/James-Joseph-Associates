from backend.services.company_name_quality import assess_company_name_quality
from scripts.audit_company_name_quality import build_company_quality_report


def test_company_quality_flags_descriptions_and_extraction_fragments() -> None:
    generic = assess_company_name_quality(
        "A financial services company",
        linkedin_url="https://www.linkedin.com/company/2150990/",
    )
    fragment = assess_company_name_quality("A ID:Tech")

    assert generic["quality_flags"] == ["possible_generic_description"]
    assert generic["has_web_identity"] is True
    assert fragment["quality_flags"] == ["possible_extraction_fragment"]


def test_company_quality_report_is_non_destructive_and_bounded() -> None:
    report = build_company_quality_report(
        [
            {
                "company_id": "company-1",
                "name": "Confidential Company",
                "source_systems": ["dropbox"],
                "source_record_types": ["dropbox_resume_extraction"],
            },
            {"company_id": "company-2", "name": "Acme Ltd"},
        ],
        limit=1,
    )

    assert report["needs_review_count"] == 1
    assert report["returned_count"] == 1
    assert report["writes_performed"] == 0
    assert report["review_items"][0]["company_id"] == "company-1"
