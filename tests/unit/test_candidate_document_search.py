from datetime import datetime, timezone
from decimal import Decimal

import pytest

from backend.services import candidate_document_search


def _row(*, candidate_id: str, score: str, name: str = "Example Candidate"):
    return {
        "candidate_id": candidate_id,
        "person_id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
        "full_name": name,
        "current_title": "Securities Finance Analyst",
        "candidate_status": "active",
        "current_company_name": "Example Ltd",
        "resume_updated_at": datetime(2026, 10, 1, tzinfo=timezone.utc),
        "sort_resume_updated_at": datetime(2026, 10, 1, tzinfo=timezone.utc),
        "document_id": candidate_id,
        "document_title": "Example-CV.pdf",
        "document_source_uri": "dropbox:///Example-CV.pdf",
        "match_score": Decimal(score),
        "match_excerpt": "Worked in <mark>securities lending</mark>.",
    }


def test_search_candidate_documents_returns_coverage_and_keyset_cursor(monkeypatch):
    rows = [
        _row(candidate_id="11111111-1111-1111-1111-111111111111", score="0.9"),
        _row(candidate_id="22222222-2222-2222-2222-222222222222", score="0.8"),
        _row(candidate_id="33333333-3333-3333-3333-333333333333", score="0.7"),
    ]
    monkeypatch.setattr(
        candidate_document_search,
        "search_current_resume_documents",
        lambda **_: {
            "coverage": {
                "total_candidates": 14,
                "eligible_document_count": 12,
                "searchable_document_count": 11,
                "excluded_missing_text_count": 1,
                "candidates_without_current_resume_count": 2,
                "matched_document_count": 3,
                "matched_candidate_count": 2,
            },
            "results": rows,
        },
    )
    monkeypatch.setattr(
        candidate_document_search,
        "get_candidate_source_details",
        lambda candidate_ids: {
            candidate_id: [
                {
                    "source_system": "dropbox",
                    "latest_record_received_at": datetime(
                        2026, 9, 1, tzinfo=timezone.utc
                    ),
                }
            ]
            for candidate_id in candidate_ids
        },
    )

    result = candidate_document_search.search_candidate_documents(
        query="securities lending",
        page_size=2,
    )

    assert result["returned_result_count"] == 2
    assert result["has_more"] is True
    assert result["coverage"]["coverage_status"] == "complete_with_exclusions"
    assert result["coverage"]["is_exhaustive"] is False
    assert result["coverage"]["searched_document_count"] == 11
    assert result["coverage"]["matched_candidate_count"] == 2
    assert result["results"][0]["source_systems"] == ["dropbox"]
    assert result["results"][0]["download_url"].endswith("/current-resume")

    decoded = candidate_document_search.decode_candidate_document_search_cursor(
        result["next_cursor"]
    )
    assert decoded["after_score"] == Decimal("0.8")
    assert decoded["after_candidate_id"] == rows[1]["candidate_id"]
    assert decoded["after_document_id"] == rows[1]["document_id"]


def test_decode_candidate_document_search_cursor_rejects_invalid_value():
    with pytest.raises(
        candidate_document_search.CandidateDocumentSearchCursorError
    ):
        candidate_document_search.decode_candidate_document_search_cursor("not-a-cursor")


def test_csv_export_streams_all_matches_and_prevents_formula_execution(monkeypatch):
    row = _row(
        candidate_id="11111111-1111-1111-1111-111111111111",
        score="0.9",
        name="=HYPERLINK(\"unsafe\")",
    )
    monkeypatch.setattr(
        candidate_document_search,
        "iter_current_resume_document_matches",
        lambda **_: iter([[row]]),
    )
    monkeypatch.setattr(
        candidate_document_search,
        "get_candidate_source_details",
        lambda _: {},
    )

    exported = "".join(
        candidate_document_search.stream_candidate_document_search_csv(query="SFTR")
    )

    assert "candidate_id,candidate_name" in exported
    assert "'=HYPERLINK" in exported
    assert "<mark>" not in exported
    assert "securities lending" in exported
