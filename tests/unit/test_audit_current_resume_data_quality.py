from scripts.audit_current_resume_data_quality import (
    build_current_resume_quality_report,
)


def _snapshot() -> dict:
    return {
        "core": {
            "total_candidates": 100,
            "candidates_with_current_link_count": 80,
            "candidates_with_multiple_current_documents_count": 0,
            "duplicate_current_link_group_count": 0,
            "non_resume_current_link_count": 0,
            "distinct_current_resume_document_count": 80,
            "missing_text_document_count": 0,
            "missing_search_vector_document_count": 0,
            "candidates_with_history_but_no_current_count": 0,
            "missing_person_mirror_link_count": 0,
            "current_document_missing_history_link_count": 0,
            "very_short_text_document_count": 0,
            "missing_source_locator_document_count": 0,
            "missing_document_provenance_count": 0,
        },
        "candidate_evidence": {
            "candidate_count": 80,
            "missing_current_title_count": 0,
            "missing_current_company_count": 0,
            "missing_structured_skills_count": 8,
            "missing_employment_history_count": 4,
            "missing_semantic_embeddings_count": 2,
            "future_resume_date_count": 0,
            "resume_age_under_6_months_count": 20,
            "resume_age_6_to_12_months_count": 20,
            "resume_age_1_to_2_years_count": 20,
            "resume_age_2_to_5_years_count": 20,
            "resume_age_over_5_years_count": 0,
        },
        "text_lengths": {"median_characters": 4200},
        "provenance_by_source_system": [
            {"source_system": "dropbox", "document_count": 60}
        ],
        "duplicate_signals": {"duplicate_content_hash_group_count": 0},
        "locator_recovery": {"unresolved_locator_count": 0},
    }


def test_quality_report_calculates_aggregate_coverage_without_sensitive_content() -> None:
    report = build_current_resume_quality_report(_snapshot())

    assert report["status"] == "monitor"
    assert report["rates"] == {
        "candidate_current_resume_coverage_percent": 80.0,
        "current_resume_text_coverage_percent": 100.0,
        "current_resume_provenance_coverage_percent": 100.0,
        "download_locator_coverage_percent": 100.0,
        "current_title_coverage_percent": 100.0,
        "current_company_coverage_percent": 100.0,
        "structured_skills_coverage_percent": 90.0,
        "employment_history_coverage_percent": 95.0,
        "semantic_embedding_coverage_percent": 97.5,
        "resume_updated_within_2_years_percent": 75.0,
    }
    assert report["sensitive_content_returned"] is False
    assert report["writes_performed"] == 0


def test_quality_report_prioritises_invariant_failures_over_review_warnings() -> None:
    snapshot = _snapshot()
    snapshot["core"].update(
        {
            "candidates_with_multiple_current_documents_count": 2,
            "very_short_text_document_count": 3,
        }
    )
    snapshot["candidate_evidence"]["future_resume_date_count"] = 1

    report = build_current_resume_quality_report(snapshot)

    assert report["status"] == "needs_attention"
    assert report["findings"][0]["severity"] == "error"
    assert {
        "multiple_current_documents",
        "very_short_extracted_text",
        "future_resume_date",
    }.issubset({finding["code"] for finding in report["findings"]})
