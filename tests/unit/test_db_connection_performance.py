"""Unit coverage for database-operation timing logs."""

import logging
from unittest.mock import MagicMock

from backend.db import connection as subject


def test_postgres_connection_records_duration_and_closes(monkeypatch, caplog) -> None:
    """A managed database block should be timed and reliably closed."""

    connection = MagicMock()
    monkeypatch.setattr(subject, "get_postgres_connection", lambda: connection)

    with caplog.at_level(logging.INFO, logger="backend.db.connection"):
        with subject.postgres_connection() as yielded_connection:
            assert yielded_connection is connection

    connection.close.assert_called_once_with()
    assert "database_performance" in caplog.text
    assert "operation=postgres_connection" in caplog.text
    assert "duration_ms=" in caplog.text
