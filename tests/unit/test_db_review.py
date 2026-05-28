"""
Unit tests for the review overview database helper.
"""

from unittest.mock import MagicMock, patch

from backend.db.review import get_review_overview


def test_get_review_overview_returns_counts_and_recent_rows() -> None:
    """
    Verify that the helper returns the expected combined overview payload.
    """

    mock_cursor = MagicMock()
    mock_cursor.fetchone.side_effect = [
        {
            "people": 4,
            "candidates": 3,
            "jobs": 2,
            "applications": 5,
            "documents": 6,
            "source_records": 7,
        },
    ]
    mock_cursor.fetchall.side_effect = [
        [
            {
                "candidate_id": "cand-1",
                "full_name": "Sarah Jones",
            }
        ],
        [
            {
                "job_id": "job-1",
                "title": "tw398 - KDB Developer",
            }
        ],
        [
            {
                "application_id": "app-1",
                "candidate_name": "Sarah Jones",
            }
        ],
        [
            {
                "document_id": "doc-1",
                "title": "Senior KDB Developer.pdf",
            }
        ],
        [
            {
                "source_record_uuid": "src-1",
                "source_system": "outlook",
            }
        ],
        [
            {
                "reconciliation_decision_id": "rec-1",
                "decision_status": "needs_review",
            }
        ],
        [
            {
                "document_type": "candidate_attachment",
                "document_count": 12,
            }
        ],
        [
            {
                "source_system": "recruiterflow",
                "source_record_count": 422,
            }
        ],
        [
            {
                "decision_status": "needs_review",
                "reconciliation_count": 3,
            }
        ],
    ]

    mock_connection = MagicMock()
    mock_connection.cursor.return_value.__enter__.return_value = mock_cursor

    with patch("backend.db.review.postgres_connection") as mock_postgres_connection:
        mock_postgres_connection.return_value.__enter__.return_value = (
            mock_connection
        )

        result = get_review_overview(limit=5)

    assert result == {
        "counts": {
            "people": 4,
            "candidates": 3,
            "jobs": 2,
            "applications": 5,
            "documents": 6,
            "source_records": 7,
        },
        "recent_candidates": [
            {
                "candidate_id": "cand-1",
                "full_name": "Sarah Jones",
            }
        ],
        "recent_jobs": [
            {
                "job_id": "job-1",
                "title": "tw398 - KDB Developer",
            }
        ],
        "recent_applications": [
            {
                "application_id": "app-1",
                "candidate_name": "Sarah Jones",
            }
        ],
        "recent_documents": [
            {
                "document_id": "doc-1",
                "title": "Senior KDB Developer.pdf",
            }
        ],
        "recent_source_records": [
            {
                "source_record_uuid": "src-1",
                "source_system": "outlook",
            }
        ],
        "recent_reconciliation_decisions": [
            {
                "reconciliation_decision_id": "rec-1",
                "decision_status": "needs_review",
            }
        ],
        "document_type_counts": [
            {
                "document_type": "candidate_attachment",
                "document_count": 12,
            }
        ],
        "source_system_counts": [
            {
                "source_system": "recruiterflow",
                "source_record_count": 422,
            }
        ],
        "reconciliation_status_counts": [
            {
                "decision_status": "needs_review",
                "reconciliation_count": 3,
            }
        ],
    }


def test_get_review_overview_passes_limit_to_recent_queries() -> None:
    """
    Verify that the helper passes the supplied limit into the recent-row queries.
    """

    mock_cursor = MagicMock()
    mock_cursor.fetchall.side_effect = [[], [], [], [], [], [], [], [], []]
    mock_cursor.fetchone.side_effect = [{"people": 0}]

    mock_connection = MagicMock()
    mock_connection.cursor.return_value.__enter__.return_value = mock_cursor

    with patch("backend.db.review.postgres_connection") as mock_postgres_connection:
        mock_postgres_connection.return_value.__enter__.return_value = (
            mock_connection
        )

        get_review_overview(limit=7)

    execute_calls = mock_cursor.execute.call_args_list

    assert len(execute_calls) == 10
    assert execute_calls[1].args[1] == {"limit": 7}
    assert execute_calls[2].args[1] == {"limit": 7}
    assert execute_calls[3].args[1] == {"limit": 7}
    assert execute_calls[4].args[1] == {"limit": 7}
    assert execute_calls[5].args[1] == {"limit": 7}
    assert execute_calls[6].args[1] == {"limit": 7}
    assert execute_calls[7].args[1] == {"limit": 7}
    assert execute_calls[8].args[1] == {"limit": 7}
    assert execute_calls[9].args[1] == {"limit": 7}
