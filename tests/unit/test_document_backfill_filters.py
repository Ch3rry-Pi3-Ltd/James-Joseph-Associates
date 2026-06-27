from unittest.mock import MagicMock, patch

from backend.db.document_chunk_backfill import list_documents_for_chunk_backfill
from backend.db.document_embedding_backfill import list_chunks_missing_embeddings


def test_list_documents_for_chunk_backfill_applies_source_record_prefix_filter() -> None:
    mock_cursor = MagicMock()
    mock_cursor.fetchall.return_value = []

    mock_connection = MagicMock()
    mock_connection.cursor.return_value.__enter__.return_value = mock_cursor

    with patch(
        "backend.db.document_chunk_backfill.postgres_connection"
    ) as mock_postgres_connection:
        mock_postgres_connection.return_value.__enter__.return_value = mock_connection

        list_documents_for_chunk_backfill(
            document_types=("resume",),
            linked_source_record_id_prefixes=("/+++ Outlook CV Export",),
            limit=25,
        )

    execute_sql, execute_params = mock_cursor.execute.call_args.args
    assert "source_record_id like any" in execute_sql
    assert execute_params["source_record_id_patterns"] == [
        "/+++ Outlook CV Export%"
    ]


def test_list_chunks_missing_embeddings_applies_source_record_prefix_filter() -> None:
    mock_cursor = MagicMock()
    mock_cursor.fetchall.return_value = []

    mock_connection = MagicMock()
    mock_connection.cursor.return_value.__enter__.return_value = mock_cursor

    with patch(
        "backend.db.document_embedding_backfill.postgres_connection"
    ) as mock_postgres_connection:
        mock_postgres_connection.return_value.__enter__.return_value = mock_connection

        list_chunks_missing_embeddings(
            document_types=("resume",),
            linked_source_record_id_prefixes=("/+++ Outlook CV Export",),
            limit=25,
        )

    execute_sql, execute_params = mock_cursor.execute.call_args.args
    assert "source_record_id like any" in execute_sql
    assert execute_params["source_record_id_patterns"] == [
        "/+++ Outlook CV Export%"
    ]
