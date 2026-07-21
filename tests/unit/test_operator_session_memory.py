from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from backend.services import operator_session_memory
from backend.services.operator_session_memory import (
    append_operator_memory_turn,
    clear_operator_memory,
    get_recent_operator_memory,
    reset_operator_memory_store,
)
from backend.settings import get_settings


@pytest.fixture(autouse=True)
def _reset_store() -> None:
    get_settings.cache_clear()
    reset_operator_memory_store()
    yield
    reset_operator_memory_store()
    get_settings.cache_clear()


def test_operator_session_memory_retains_recent_turns_per_user(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPERATOR_SESSION_MEMORY_MAX_TURNS", "2")
    get_settings.cache_clear()

    append_operator_memory_turn(
        user_id="user-1",
        question="Q1",
        answer="A1",
    )
    append_operator_memory_turn(
        user_id="user-1",
        question="Q2",
        answer="A2",
    )
    append_operator_memory_turn(
        user_id="user-1",
        question="Q3",
        answer="A3",
    )

    memory = get_recent_operator_memory(user_id="user-1")

    assert [turn["question"] for turn in memory] == ["Q2", "Q3"]


def test_operator_session_memory_is_scoped_by_conversation_id() -> None:
    append_operator_memory_turn(
        user_id="user-1",
        conversation_id="thread-a",
        question="Q1",
        answer="A1",
    )
    append_operator_memory_turn(
        user_id="user-1",
        conversation_id="thread-b",
        question="Q2",
        answer="A2",
    )

    assert get_recent_operator_memory(
        user_id="user-1",
        conversation_id="thread-a",
    ) == [
        {
            "question": "Q1",
            "answer": "A1",
            "created_at": get_recent_operator_memory(
                user_id="user-1",
                conversation_id="thread-a",
            )[0]["created_at"],
            "metadata": {},
        }
    ]
    assert get_recent_operator_memory(
        user_id="user-1",
        conversation_id="thread-b",
    )[0]["question"] == "Q2"


def test_operator_session_memory_expires_after_ttl(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPERATOR_SESSION_MEMORY_TTL_HOURS", "1")
    get_settings.cache_clear()

    base_time = datetime(2026, 7, 21, 12, 0, tzinfo=UTC)
    monkeypatch.setattr(
        operator_session_memory,
        "_utcnow",
        lambda: base_time,
    )
    append_operator_memory_turn(
        user_id="user-1",
        question="Q1",
        answer="A1",
    )

    monkeypatch.setattr(
        operator_session_memory,
        "_utcnow",
        lambda: base_time + timedelta(hours=2),
    )

    assert get_recent_operator_memory(user_id="user-1") == []


def test_operator_session_memory_can_be_cleared() -> None:
    append_operator_memory_turn(
        user_id="user-1",
        question="Q1",
        answer="A1",
    )

    clear_operator_memory(user_id="user-1")

    assert get_recent_operator_memory(user_id="user-1") == []
