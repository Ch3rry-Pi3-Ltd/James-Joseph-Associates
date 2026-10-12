from concurrent.futures import ThreadPoolExecutor
from contextvars import copy_context
from unittest.mock import MagicMock

import pytest

from backend.core import read_budget as subject
from backend.db import connection


def test_nested_budget_never_extends_deadline_and_resets(monkeypatch):
    now = [100.0]
    monkeypatch.setattr(subject, "monotonic", lambda: now[0])
    with subject.read_budget(5):
        now[0] = 103
        with subject.read_budget(20):
            assert subject.remaining_read_seconds() == 2
            with ThreadPoolExecutor() as pool:
                assert pool.submit(copy_context().run, subject.remaining_read_seconds).result() == 2
        now[0] = 106
        with pytest.raises(TimeoutError):
            subject.remaining_read_seconds()
    assert subject.remaining_read_seconds() is None


def test_database_budget_sets_server_timeout_and_cancels_connection(monkeypatch):
    db = MagicMock()
    timer = MagicMock()
    monkeypatch.setattr(connection, "get_postgres_connection", lambda: db)
    monkeypatch.setattr(connection, "Timer", timer)
    with subject.read_budget(2):
        with connection.postgres_connection():
            callback = timer.call_args.args[1]
            callback()
            db.cancel_safe.assert_called_once_with(timeout=1)
    timeout_ms = int(db.execute.call_args.args[1][0])
    assert 0 < timeout_ms <= 2000
    timer.return_value.cancel.assert_called_once()
    db.close.assert_called_once()


def test_expired_budget_does_not_open_another_connection(monkeypatch):
    now = [100.0]
    monkeypatch.setattr(subject, "monotonic", lambda: now[0])
    connect = MagicMock()
    monkeypatch.setattr(connection, "get_postgres_connection", connect)
    with subject.read_budget(1):
        now[0] = 102.0
        with pytest.raises(TimeoutError):
            with connection.postgres_connection():
                pass
    connect.assert_not_called()
