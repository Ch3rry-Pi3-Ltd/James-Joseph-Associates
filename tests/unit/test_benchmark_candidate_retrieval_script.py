"""Tests for stage-separated candidate retrieval benchmarking."""

from scripts import benchmark_candidate_retrieval as subject


def test_benchmark_query_runs_each_retrieval_stage_without_storing_brief(
    monkeypatch,
) -> None:
    calls: list[tuple[str, bool | None, bool | None]] = []

    monkeypatch.setattr(
        subject,
        "search_candidates_by_resume_text",
        lambda **kwargs: [
            {
                "candidate_id": "cand-text",
                "match_score": 0.8,
                "match_excerpt": "private resume evidence",
            }
        ],
    )

    def fake_hybrid(**kwargs):
        calls.append(
            (
                "hybrid",
                kwargs.get("include_text"),
                kwargs.get("include_semantic"),
            )
        )
        return [{"candidate_id": "cand-hybrid", "match_score": 0.9}]

    monkeypatch.setattr(subject, "search_candidates_hybrid", fake_hybrid)
    monkeypatch.setattr(
        subject,
        "retrieve_candidates_with_graph_context",
        lambda **kwargs: [{"candidate_id": "cand-graph", "match_score": 0.95}],
    )

    query = "Private senior data engineer role brief"
    result = subject._benchmark_query(query=query, limit=5)

    assert set(result["stages"]) == {
        "full_text",
        "semantic",
        "hybrid",
        "graph_assisted",
    }
    assert calls == [
        ("hybrid", False, True),
        ("hybrid", True, True),
    ]
    assert query not in str(result)
    assert "private resume evidence" not in str(result)
    assert all(
        stage["result_fingerprint"] for stage in result["stages"].values()
    )
