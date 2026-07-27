"""Tests for read-only database usage metrics."""

from contextlib import contextmanager

from backend.db import database_usage as subject


class _Cursor:
    def __enter__(self):
        return self

    def __exit__(self, *args):
        return None

    def execute(self, statement):
        assert "pg_database_size" in statement

    def fetchone(self):
        return {"size_bytes": 2_500_000_000}


class _Connection:
    def cursor(self):
        return _Cursor()


def test_get_database_size_bytes_returns_allocated_size(monkeypatch) -> None:
    @contextmanager
    def connection():
        yield _Connection()

    monkeypatch.setattr(subject, "postgres_connection", connection)

    assert subject.get_database_size_bytes() == 2_500_000_000
