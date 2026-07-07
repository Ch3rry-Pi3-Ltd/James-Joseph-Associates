from backend.db import candidate_semantic_blocks as semantic_blocks_db
from backend.db.candidate_semantic_blocks import (
    search_candidates_by_semantic_blocks,
)


def test_search_candidates_by_semantic_blocks_returns_empty_when_index_is_blank(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        semantic_blocks_db,
        "semantic_block_index_has_embeddings",
        lambda: False,
    )

    def fail_embed_texts(_texts: list[str]) -> list[list[float]]:
        raise AssertionError("Embedding client should not be called.")

    monkeypatch.setattr(
        semantic_blocks_db,
        "embed_texts",
        fail_embed_texts,
    )

    result = search_candidates_by_semantic_blocks(
        query="senior python data engineer",
        limit=10,
    )

    assert result == []
