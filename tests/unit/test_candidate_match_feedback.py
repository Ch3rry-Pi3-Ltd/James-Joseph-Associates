from unittest.mock import MagicMock

from backend.db import candidate_match_feedback as feedback_db
from backend.services import candidate_match_feedback as feedback_service


def test_save_candidate_match_feedback_normalizes_review_snapshot(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_upsert(**kwargs: object) -> dict[str, object]:
        captured.update(kwargs)
        return {"id": "feedback-1"}

    monkeypatch.setattr(
        feedback_service,
        "upsert_candidate_match_feedback",
        fake_upsert,
    )

    result = feedback_service.save_candidate_match_feedback(
        match_run_id="run-1",
        candidate_id="candidate-1",
        document_id=None,
        reviewer_user_id=" user-1 ",
        reviewer_email=" Reviewer@Example.com ",
        feedback_value="good_match",
        feedback_reason="  Strong technical fit.  ",
        job_description="  Senior Python engineer  ",
        shortlist_rank=1,
        fit_score=93,
        retrieval_score=0.91,
        graph_context_score=0.2,
        ranking_input_score=0.8,
        source_category=" cross_source ",
    )

    assert result == {"id": "feedback-1"}
    assert captured["reviewer_user_id"] == "user-1"
    assert captured["reviewer_email"] == "reviewer@example.com"
    assert captured["feedback_reason"] == "Strong technical fit."
    assert captured["job_description"] == "Senior Python engineer"
    assert captured["source_category"] == "cross_source"
    assert captured["job_description_hash"] == (
        "c5e6efc73bf7b3fa45093631e8416eb15061993dfb1"
        "0e7d9ec889534f3eccc29"
    )


def test_upsert_candidate_match_feedback_commits_and_returns_row(
    monkeypatch,
) -> None:
    returned_row = {
        "id": "feedback-1",
        "match_run_id": "run-1",
        "candidate_id": "candidate-1",
    }
    cursor = MagicMock()
    cursor.fetchone.return_value = returned_row
    connection = MagicMock()
    connection.cursor.return_value.__enter__.return_value = cursor
    context = MagicMock()
    context.return_value.__enter__.return_value = connection
    monkeypatch.setattr(feedback_db, "postgres_connection", context)

    result = feedback_db.upsert_candidate_match_feedback(
        match_run_id="run-1",
        candidate_id="candidate-1",
        document_id=None,
        reviewer_user_id="user-1",
        reviewer_email=None,
        feedback_value="not_suitable",
        feedback_reason=None,
        job_description_hash="hash",
        job_description="Role brief",
        shortlist_rank=2,
        fit_score=70,
        retrieval_score=0.6,
        graph_context_score=None,
        ranking_input_score=None,
        source_category="cv_backed",
    )

    assert result == returned_row
    query = cursor.execute.call_args.args[0]
    parameters = cursor.execute.call_args.args[1]
    assert "ON CONFLICT (match_run_id, candidate_id, reviewer_user_id)" in query
    assert parameters["feedback_value"] == "not_suitable"
    connection.commit.assert_called_once_with()
