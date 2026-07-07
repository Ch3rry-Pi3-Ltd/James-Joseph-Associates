from backend.services import candidate_retrieval
from backend.services.candidate_retrieval import (
    build_text_retrieval_query_variants,
    derive_text_retrieval_query,
    fuse_candidate_rankings,
    search_candidates_hybrid,
)


def test_fuse_candidate_rankings_prefers_candidates_seen_in_both_sources() -> None:
    fused = fuse_candidate_rankings(
        text_results=[
            {
                "candidate_id": "cand-1",
                "person_id": "person-1",
                "document_id": "doc-1",
                "match_score": 0.9,
                "match_excerpt": "python sql",
            },
            {
                "candidate_id": "cand-2",
                "person_id": "person-2",
                "document_id": "doc-2",
                "match_score": 0.8,
                "match_excerpt": "java",
            },
        ],
        semantic_results=[
            {
                "candidate_id": "cand-2",
                "person_id": "person-2",
                "document_id": "doc-2",
                "match_score": 0.85,
                "match_excerpt": "platform data engineering",
            }
        ],
        limit=5,
    )

    assert [row["candidate_id"] for row in fused] == ["cand-2", "cand-1"]
    assert fused[0]["match_excerpt"] == "platform data engineering"
    assert fused[0]["match_score"] > fused[1]["match_score"]
    assert fused[0]["retrieval_sources"] == ["text", "semantic"]
    assert fused[0]["text_rank"] == 2
    assert fused[0]["semantic_rank"] == 1
    assert fused[0]["semantic_block_type"] is None


def test_derive_text_retrieval_query_compacts_role_brief_into_keywords() -> None:
    query = (
        "Senior data engineer with strong Python, SQL, cloud platform, and ETL "
        "experience. Ideally someone who has worked with large datasets."
    )

    result = derive_text_retrieval_query(query)

    assert result == "senior data engineer python sql cloud platform etl"


def test_build_text_retrieval_query_variants_returns_progressive_backoff() -> None:
    query = (
        "Senior data engineer with strong Python, SQL, cloud platform, and ETL "
        "experience. Ideally someone who has worked with large datasets."
    )

    result = build_text_retrieval_query_variants(query)

    assert result == [
        "senior data engineer python sql cloud platform etl",
        "senior data engineer python sql cloud",
        "senior data engineer python",
        "senior data engineer",
    ]


def test_search_candidates_hybrid_uses_compact_text_query_and_full_semantic_query(
    monkeypatch,
) -> None:
    captured: dict[str, object] = {}

    def fake_text_search(*, query: str, limit: int) -> list[dict[str, object]]:
        captured["text_query"] = query
        captured["text_limit"] = limit
        return []

    def fake_semantic_search(*, query: str, limit: int) -> list[dict[str, object]]:
        captured["semantic_query"] = query
        captured["semantic_limit"] = limit
        return []

    monkeypatch.setattr(
        candidate_retrieval,
        "search_candidates_by_resume_text",
        fake_text_search,
    )
    monkeypatch.setattr(
        candidate_retrieval,
        "search_candidates_by_semantic_blocks",
        fake_semantic_search,
    )

    result = search_candidates_hybrid(
        query=(
            "Senior data engineer with strong Python, SQL, cloud platform, "
            "and ETL experience."
        ),
        limit=10,
    )

    assert result == []
    assert captured["text_query"] == "senior data engineer"
    assert captured["semantic_query"] == (
        "Senior data engineer with strong Python, SQL, cloud platform, and ETL experience."
    )


def test_search_candidates_hybrid_stops_text_backoff_once_it_finds_matches(
    monkeypatch,
) -> None:
    attempted_queries: list[str] = []

    def fake_text_search(*, query: str, limit: int) -> list[dict[str, object]]:
        attempted_queries.append(query)
        if query == "senior data engineer python sql cloud":
            return [
                {
                    "candidate_id": "cand-1",
                    "person_id": "person-1",
                    "document_id": "doc-1",
                    "match_score": 0.9,
                    "match_excerpt": "python sql cloud",
                }
            ]
        return []

    monkeypatch.setattr(
        candidate_retrieval,
        "search_candidates_by_resume_text",
        fake_text_search,
    )
    monkeypatch.setattr(
        candidate_retrieval,
        "search_candidates_by_semantic_blocks",
        lambda **kwargs: [],
    )

    result = search_candidates_hybrid(
        query=(
            "Senior data engineer with strong Python, SQL, cloud platform, "
            "and ETL experience."
        ),
        limit=10,
        include_text=True,
        include_semantic=False,
    )

    assert [row["candidate_id"] for row in result] == ["cand-1"]
    assert attempted_queries == [
        "senior data engineer python sql cloud platform etl",
        "senior data engineer python sql cloud",
    ]
