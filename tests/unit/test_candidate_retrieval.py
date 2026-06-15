from backend.services.candidate_retrieval import fuse_candidate_rankings


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
