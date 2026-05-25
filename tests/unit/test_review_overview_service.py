"""
Unit tests for the review overview service helper.
"""

from unittest.mock import patch

from backend.services.review_overview import build_review_overview


def test_build_review_overview_delegates_to_db_helper() -> None:
    """
    Verify that the service delegates directly to the DB helper.
    """

    expected = {
        "counts": {"jobs": 2},
        "recent_candidates": [],
        "recent_jobs": [],
        "recent_applications": [],
        "recent_documents": [],
        "recent_source_records": [],
    }

    with patch(
        "backend.services.review_overview.get_review_overview",
        return_value=expected,
    ) as mock_get_review_overview:
        result = build_review_overview(limit=4)

    assert result == expected
    mock_get_review_overview.assert_called_once_with(limit=4)
