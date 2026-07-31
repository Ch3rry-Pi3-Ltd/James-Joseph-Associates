"""Tests for private recruiter role briefs and saved result snapshots."""

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from backend.db import candidate_saved_briefs as saved_briefs_db
from backend.services import candidate_saved_briefs as saved_briefs_service
from backend.services.candidate_saved_briefs import CandidateSavedBriefError


def _saved_brief_row(**overrides: object) -> dict[str, object]:
    now = datetime.now(timezone.utc)
    row: dict[str, object] = {
        "id": "658a5599-7027-4c8c-b4aa-b76f13566525",
        "created_by_user_id": "user_123",
        "created_by_email": "reviewer@example.com",
        "title": "Senior Data Engineer",
        "job_description": "Senior Python data engineer",
        "target_company_name": "Example Ltd",
        "retrieval_focus_terms": "python sql data engineer",
        "search_result_limit": 5,
        "retrieval_limit": 25,
        "shortlist_limit": 3,
        "last_match_run_id": None,
        "retrieved_candidate_count": 25,
        "search_results": [{"candidate_id": "candidate-1"}],
        "shortlisted_candidates": [{"candidate_id": "candidate-1"}],
        "created_at": now,
        "updated_at": now,
    }
    row.update(overrides)
    return row


def _write_payload() -> dict[str, object]:
    return {
        "title": " Senior Data Engineer ",
        "job_description": " Senior Python data engineer ",
        "target_company_name": " Example Ltd ",
        "retrieval_focus_terms": " python sql data engineer ",
        "search_result_limit": 5,
        "retrieval_limit": 25,
        "shortlist_limit": 3,
        "last_match_run_id": None,
        "retrieved_candidate_count": 25,
        "search_results": [{"candidate_id": "candidate-1"}],
        "shortlisted_candidates": [{"candidate_id": "candidate-1"}],
    }


def test_create_saved_brief_normalizes_operator_and_text(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_create(**kwargs: object) -> dict[str, object]:
        captured.update(kwargs)
        return _saved_brief_row()

    monkeypatch.setattr(
        saved_briefs_service,
        "create_candidate_saved_brief",
        fake_create,
    )

    result = saved_briefs_service.create_saved_brief(
        created_by_user_id=" user_123 ",
        created_by_email=" Reviewer@Example.com ",
        payload=_write_payload(),
    )

    assert captured["created_by_user_id"] == "user_123"
    assert captured["created_by_email"] == "reviewer@example.com"
    assert captured["title"] == "Senior Data Engineer"
    assert captured["target_company_name"] == "Example Ltd"
    assert result["saved_brief_id"] == "658a5599-7027-4c8c-b4aa-b76f13566525"
    assert "created_by_user_id" not in result


def test_list_saved_briefs_returns_compact_public_rows(monkeypatch) -> None:
    row = _saved_brief_row(
        job_description_preview="Senior Python data engineer",
        search_result_count=5,
        shortlist_count=3,
    )
    monkeypatch.setattr(
        saved_briefs_service,
        "list_candidate_saved_briefs",
        lambda **_kwargs: [row],
    )

    result = saved_briefs_service.list_saved_briefs(
        created_by_user_id="user_123",
        limit=50,
    )

    assert result["count"] == 1
    assert result["saved_briefs"][0]["search_result_count"] == 5
    assert "job_description" not in result["saved_briefs"][0]


def test_load_saved_brief_hides_cross_owner_missing_rows(monkeypatch) -> None:
    monkeypatch.setattr(
        saved_briefs_service,
        "get_candidate_saved_brief",
        lambda **_kwargs: None,
    )

    with pytest.raises(CandidateSavedBriefError) as missing:
        saved_briefs_service.load_saved_brief(
            saved_brief_id="658a5599-7027-4c8c-b4aa-b76f13566525",
            created_by_user_id="different-user",
        )

    assert missing.value.code == "saved_brief_not_found"
    assert missing.value.status_code == 404


def test_delete_saved_brief_requires_owned_row(monkeypatch) -> None:
    monkeypatch.setattr(
        saved_briefs_service,
        "delete_candidate_saved_brief",
        lambda **_kwargs: False,
    )

    with pytest.raises(CandidateSavedBriefError) as missing:
        saved_briefs_service.remove_saved_brief(
            saved_brief_id="658a5599-7027-4c8c-b4aa-b76f13566525",
            created_by_user_id="different-user",
        )

    assert missing.value.code == "saved_brief_not_found"


def test_database_update_scopes_write_to_authenticated_owner(monkeypatch) -> None:
    cursor = MagicMock()
    cursor.fetchone.return_value = _saved_brief_row()
    connection = MagicMock()
    connection.cursor.return_value.__enter__.return_value = cursor
    context = MagicMock()
    context.return_value.__enter__.return_value = connection
    monkeypatch.setattr(saved_briefs_db, "postgres_connection", context)

    saved_briefs_db.update_candidate_saved_brief(
        saved_brief_id="658a5599-7027-4c8c-b4aa-b76f13566525",
        created_by_user_id="user_123",
        created_by_email="reviewer@example.com",
        **{
            key: value
            for key, value in _write_payload().items()
            if key != "title"
        },
        title="Senior Data Engineer",
    )

    query = cursor.execute.call_args.args[0]
    parameters = cursor.execute.call_args.args[1]
    assert "AND created_by_user_id = %(created_by_user_id)s" in query
    assert parameters["created_by_user_id"] == "user_123"
    connection.commit.assert_called_once_with()
