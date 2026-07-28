from unittest.mock import MagicMock

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


def test_semantic_search_keeps_profile_only_candidates(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        semantic_blocks_db,
        "semantic_block_index_has_embeddings",
        lambda: True,
    )
    monkeypatch.setattr(
        semantic_blocks_db,
        "embed_texts",
        lambda _texts: [[0.1, 0.2]],
    )

    mock_cursor = MagicMock()
    mock_cursor.fetchall.return_value = [
        {
            "candidate_id": "candidate-1",
            "person_id": "person-1",
            "full_name": "Profile Only",
            "document_id": None,
            "document_title": None,
            "match_score": 0.91,
        }
    ]
    mock_connection = MagicMock()
    mock_connection.cursor.return_value.__enter__.return_value = mock_cursor
    mock_postgres_connection = MagicMock()
    mock_postgres_connection.return_value.__enter__.return_value = mock_connection
    monkeypatch.setattr(
        semantic_blocks_db,
        "postgres_connection",
        mock_postgres_connection,
    )

    result = search_candidates_by_semantic_blocks(
        query="rust low latency engineer",
        limit=10,
    )

    search_sql = mock_cursor.execute.call_args.args[0]
    assert "left join documents d" in search_sql
    assert result[0]["candidate_id"] == "candidate-1"
    assert result[0]["document_id"] is None
