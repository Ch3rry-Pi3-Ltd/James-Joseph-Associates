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

    assert result == "data engineer python sql cloud platform etl datasets"


def test_derive_text_retrieval_query_prioritizes_skill_terms_over_label_noise() -> None:
    query = (
        "Job Description FINANCIAL SYSTEMS ANALYST Grade 3 Reporting to Head of BMI "
        "Location London IBM Planning Analytics TM1 TurboIntegrator SQL finance systems"
    )

    result = derive_text_retrieval_query(query)

    assert result == (
        "financial analyst ibm planning analytics tm1 turbointegrator sql finance"
    )


def test_build_text_retrieval_query_variants_returns_progressive_backoff() -> None:
    query = (
        "Senior data engineer with strong Python, SQL, cloud platform, and ETL "
        "experience. Ideally someone who has worked with large datasets."
    )

    result = build_text_retrieval_query_variants(query)

    assert result == [
        "data engineer python sql cloud platform etl datasets",
        "data engineer python sql cloud platform",
        "data engineer python sql",
        "data engineer python",
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
    assert captured["text_query"] == "data engineer python"
    assert captured["semantic_query"] == (
        "Senior data engineer with strong Python, SQL, cloud platform, and ETL experience."
    )


def test_search_candidates_hybrid_stops_text_backoff_once_it_finds_matches(
    monkeypatch,
) -> None:
    attempted_queries: list[str] = []

    def fake_text_search(*, query: str, limit: int) -> list[dict[str, object]]:
        attempted_queries.append(query)
        if query == "data engineer python sql cloud platform etl":
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
        "data engineer python sql cloud platform etl",
    ]


def test_search_candidates_hybrid_returns_text_results_when_semantic_fails(
    monkeypatch,
) -> None:
    text_result = {
        "candidate_id": "cand-1",
        "person_id": "person-1",
        "document_id": "doc-1",
        "match_score": 0.9,
        "match_excerpt": "python sql data engineering",
    }
    monkeypatch.setattr(
        candidate_retrieval,
        "search_candidates_by_resume_text",
        lambda **kwargs: [text_result],
    )

    def fail_semantic_search(**kwargs):
        raise TimeoutError("embedding provider timed out")

    monkeypatch.setattr(
        candidate_retrieval,
        "search_candidates_by_semantic_blocks",
        fail_semantic_search,
    )

    result = search_candidates_hybrid(
        query="Senior data engineer with Python and SQL",
        limit=5,
    )

    assert [row["candidate_id"] for row in result] == ["cand-1"]
    assert result[0]["retrieval_sources"] == ["text"]


def test_semantic_circuit_opens_after_repeated_failures(monkeypatch) -> None:
    monkeypatch.setattr(candidate_retrieval, "_semantic_consecutive_failures", 0)
    monkeypatch.setattr(candidate_retrieval, "_semantic_circuit_open_until", 0.0)
    attempts = 0

    monkeypatch.setattr(
        candidate_retrieval,
        "search_candidates_by_resume_text",
        lambda **kwargs: [
            {
                "candidate_id": "cand-1",
                "person_id": "person-1",
                "match_score": 0.8,
            }
        ],
    )

    def fail_semantic(**kwargs):
        nonlocal attempts
        attempts += 1
        raise TimeoutError("provider timeout")

    monkeypatch.setattr(
        candidate_retrieval,
        "search_candidates_by_semantic_blocks",
        fail_semantic,
    )

    diagnostics: list[dict[str, object]] = []
    for _ in range(3):
        current: dict[str, object] = {}
        search_candidates_hybrid(
            query="senior data engineer",
            limit=5,
            diagnostics=current,
        )
        diagnostics.append(current)

    assert attempts == 2
    assert diagnostics[0]["semantic_fallback_used"] is True
    assert diagnostics[1]["semantic_fallback_used"] is True
    assert diagnostics[2]["semantic_circuit_open"] is True
