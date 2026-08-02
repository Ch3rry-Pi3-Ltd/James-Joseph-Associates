"""Regression contract for embedding, chunking, and structured blocks."""

from inspect import signature

from backend.services.candidate_semantic_blocks import (
    build_candidate_semantic_blocks,
)
from backend.services.document_chunking import chunk_document_text
from backend.settings import Settings


def test_embedding_and_raw_chunk_defaults_are_explicit() -> None:
    assert Settings.model_fields["openai_embedding_model"].default == (
        "text-embedding-3-large"
    )
    assert Settings.model_fields["openai_embedding_dimensions"].default == 1536

    parameters = signature(chunk_document_text).parameters
    assert parameters["max_chars"].default == 1200
    assert parameters["overlap_chars"].default == 150


def test_structured_candidate_blocks_keep_recruitment_boundaries() -> None:
    blocks = build_candidate_semantic_blocks(
        candidate={
            "full_name": "Example Candidate",
            "current_title": "Data Engineer",
            "headline": "Python platform specialist",
            "summary": "Builds production data services.",
            "primary_email": "private@example.test",
            "primary_phone": "+447700900000",
            "resume_extracted_text": "Python SQL cloud delivery.",
        },
        skills=[
            {"canonical_name": f"skill-{index}"}
            for index in range(1, 11)
        ],
    )

    assert [block.block_type for block in blocks] == [
        "profile",
        "focus",
        "skills",
        "skills",
        "summary",
        "resume_context",
    ]
    serialized = " ".join(block.block_text for block in blocks)
    assert "private@example.test" not in serialized
    assert "+447700900000" not in serialized
