"""Tests for secure, expiring candidate shortlist shares."""

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest

from backend.db import candidate_shortlist_shares as shares_db
from backend.services import candidate_shortlist_shares as shares_service
from backend.services.candidate_shortlist_shares import (
    CandidateShortlistShareError,
)


def _share_row(**overrides: object) -> dict[str, object]:
    now = datetime.now(timezone.utc)
    row: dict[str, object] = {
        "id": "4fc6ad2a-1fae-4fbb-b8f6-6de16b56e2ea",
        "match_run_id": "61b18a15-0ca1-42c6-80c2-4800b002c17b",
        "created_by_user_id": "user_123",
        "created_by_email": "reviewer@example.com",
        "role_title": "Senior Data Engineer",
        "job_description": "Senior Python data engineer",
        "shortlisted_candidates": [{"candidate_id": "candidate-1"}],
        "expires_at": now + timedelta(days=14),
        "revoked_at": None,
        "created_at": now,
        "updated_at": now,
    }
    row.update(overrides)
    return row


def test_create_share_normalizes_identity_and_sets_expiry(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_upsert(**kwargs: object) -> dict[str, object]:
        captured.update(kwargs)
        return _share_row()

    monkeypatch.setattr(
        shares_service,
        "upsert_candidate_shortlist_share",
        fake_upsert,
    )

    result = shares_service.create_candidate_shortlist_share(
        match_run_id="61b18a15-0ca1-42c6-80c2-4800b002c17b",
        created_by_user_id=" user_123 ",
        created_by_email=" Reviewer@Example.com ",
        role_title=" Senior Data Engineer ",
        job_description=" Senior Python data engineer ",
        shortlisted_candidates=[{"candidate_id": "candidate-1"}],
        expires_in_days=14,
    )

    assert captured["created_by_user_id"] == "user_123"
    assert captured["created_by_email"] == "reviewer@example.com"
    assert captured["role_title"] == "Senior Data Engineer"
    assert captured["job_description"] == "Senior Python data engineer"
    expires_at = captured["expires_at"]
    assert isinstance(expires_at, datetime)
    assert timedelta(days=13, hours=23) < (
        expires_at - datetime.now(timezone.utc)
    ) <= timedelta(days=14)
    assert result["can_revoke"] is True


def test_load_share_rejects_expired_and_revoked_links(monkeypatch) -> None:
    monkeypatch.setattr(
        shares_service,
        "get_candidate_shortlist_share",
        lambda _share_id: _share_row(
            expires_at=datetime.now(timezone.utc) - timedelta(seconds=1)
        ),
    )
    with pytest.raises(CandidateShortlistShareError) as expired:
        shares_service.load_candidate_shortlist_share(
            share_id="share-1",
            requesting_user_id="user_123",
        )
    assert expired.value.code == "shortlist_share_expired"
    assert expired.value.status_code == 410

    monkeypatch.setattr(
        shares_service,
        "get_candidate_shortlist_share",
        lambda _share_id: _share_row(revoked_at=datetime.now(timezone.utc)),
    )
    with pytest.raises(CandidateShortlistShareError) as revoked:
        shares_service.load_candidate_shortlist_share(
            share_id="share-1",
            requesting_user_id="user_123",
        )
    assert revoked.value.code == "shortlist_share_revoked"
    assert revoked.value.status_code == 410


def test_revoke_share_requires_creator(monkeypatch) -> None:
    monkeypatch.setattr(
        shares_service,
        "get_candidate_shortlist_share",
        lambda _share_id: _share_row(),
    )

    with pytest.raises(CandidateShortlistShareError) as forbidden:
        shares_service.revoke_shortlist_share(
            share_id="share-1",
            requesting_user_id="different-user",
        )

    assert forbidden.value.code == "shortlist_share_forbidden"
    assert forbidden.value.status_code == 403


def test_upsert_share_commits_json_snapshot(monkeypatch) -> None:
    returned_row = _share_row()
    cursor = MagicMock()
    cursor.fetchone.return_value = returned_row
    connection = MagicMock()
    connection.cursor.return_value.__enter__.return_value = cursor
    context = MagicMock()
    context.return_value.__enter__.return_value = connection
    monkeypatch.setattr(shares_db, "postgres_connection", context)

    result = shares_db.upsert_candidate_shortlist_share(
        match_run_id="61b18a15-0ca1-42c6-80c2-4800b002c17b",
        created_by_user_id="user_123",
        created_by_email="reviewer@example.com",
        role_title="Senior Data Engineer",
        job_description="Senior Python data engineer",
        shortlisted_candidates=[{"candidate_id": "candidate-1"}],
        expires_at=datetime.now(timezone.utc) + timedelta(days=14),
    )

    assert result == returned_row
    query = cursor.execute.call_args.args[0]
    parameters = cursor.execute.call_args.args[1]
    assert "ON CONFLICT (match_run_id, created_by_user_id)" in query
    assert parameters["created_by_user_id"] == "user_123"
    connection.commit.assert_called_once_with()
