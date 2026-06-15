from backend.services.candidate_semantic_blocks import (
    build_candidate_semantic_blocks,
    normalize_semantic_block_text,
)


def test_normalize_semantic_block_text_compacts_whitespace() -> None:
    result = normalize_semantic_block_text("  Senior   data\n engineer \t Python  ")
    assert result == "Senior data engineer Python"


def test_build_candidate_semantic_blocks_returns_profile_skills_and_summary() -> None:
    blocks = build_candidate_semantic_blocks(
        candidate={
            "full_name": "Sarah Jones",
            "current_title": "Senior Data Engineer",
            "current_company_name": "Acme",
            "location": "London",
            "headline": "Python and platform specialist",
            "candidate_status": "active",
            "availability_status": "open",
            "notice_period": "1 month",
            "resume_updated_at": "2026-06-01T12:00:00+00:00",
            "summary": "Built cloud ETL pipelines and analytics platforms.",
            "document_title": "Sarah-Jones-CV.pdf",
            "document_source_uri": "dropbox:///Sarah-Jones-CV.pdf",
        },
        skills=[
            {
                "skill_name": "Python",
                "canonical_name": "python",
                "evidence_text": "Python and Airflow pipelines",
            },
            {
                "skill_name": "SQL",
                "canonical_name": "sql",
                "evidence_text": "Warehouse optimisation",
            },
        ],
    )

    assert [block.block_type for block in blocks] == ["profile", "skills", "summary"]
    assert "Sarah Jones" in blocks[0].block_text
    assert "python; sql" in blocks[1].block_text.lower()
    assert "Built cloud ETL pipelines" in blocks[2].block_text
