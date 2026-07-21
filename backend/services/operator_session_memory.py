"""
Short-lived per-user session memory for recruiter-facing Q&A.
"""

from __future__ import annotations

from collections import deque
from datetime import UTC, datetime, timedelta
from threading import Lock
from typing import Any

from backend.settings import get_settings

_DEFAULT_CONVERSATION_ID = "__default__"
_MEMORY_STORE: dict[tuple[str, str], deque[dict[str, Any]]] = {}
_MEMORY_EXPIRY: dict[tuple[str, str], datetime] = {}
_MEMORY_LOCK = Lock()


def get_recent_operator_memory(
    *,
    user_id: str,
    conversation_id: str | None = None,
) -> list[dict[str, Any]]:
    """
    Return recent retained memory turns for one user/session key.
    """

    normalized_user_id = _normalize_required_identifier(
        value=user_id,
        field_name="user_id",
    )
    key = _build_memory_key(
        user_id=normalized_user_id,
        conversation_id=conversation_id,
    )

    with _MEMORY_LOCK:
        _prune_expired_locked(now=_utcnow())
        turns = _MEMORY_STORE.get(key)
        if turns is None:
            return []
        return [dict(turn) for turn in turns]


def append_operator_memory_turn(
    *,
    user_id: str,
    question: str,
    answer: str,
    conversation_id: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    """
    Append one bounded memory turn for one user/session key.
    """

    normalized_user_id = _normalize_required_identifier(
        value=user_id,
        field_name="user_id",
    )
    normalized_question = _normalize_required_identifier(
        value=question,
        field_name="question",
    )
    normalized_answer = _normalize_required_identifier(
        value=answer,
        field_name="answer",
    )
    key = _build_memory_key(
        user_id=normalized_user_id,
        conversation_id=conversation_id,
    )

    settings = get_settings()
    max_turns = max(1, int(settings.operator_session_memory_max_turns))
    ttl_hours = max(1, int(settings.operator_session_memory_ttl_hours))
    now = _utcnow()
    expires_at = now + timedelta(hours=ttl_hours)

    turn = {
        "question": normalized_question,
        "answer": normalized_answer,
        "created_at": now.isoformat(),
        "metadata": dict(metadata or {}),
    }

    with _MEMORY_LOCK:
        _prune_expired_locked(now=now)
        turns = _MEMORY_STORE.setdefault(key, deque())
        turns.append(turn)
        while len(turns) > max_turns:
            turns.popleft()
        _MEMORY_EXPIRY[key] = expires_at


def clear_operator_memory(
    *,
    user_id: str,
    conversation_id: str | None = None,
) -> None:
    """
    Remove retained memory for one user/session key.
    """

    normalized_user_id = _normalize_required_identifier(
        value=user_id,
        field_name="user_id",
    )
    key = _build_memory_key(
        user_id=normalized_user_id,
        conversation_id=conversation_id,
    )

    with _MEMORY_LOCK:
        _MEMORY_STORE.pop(key, None)
        _MEMORY_EXPIRY.pop(key, None)


def reset_operator_memory_store() -> None:
    """
    Clear the in-memory store. Intended for tests.
    """

    with _MEMORY_LOCK:
        _MEMORY_STORE.clear()
        _MEMORY_EXPIRY.clear()


def _build_memory_key(
    *,
    user_id: str,
    conversation_id: str | None,
) -> tuple[str, str]:
    normalized_conversation_id = (
        conversation_id.strip()
        if isinstance(conversation_id, str) and conversation_id.strip() != ""
        else _DEFAULT_CONVERSATION_ID
    )
    return (user_id, normalized_conversation_id)


def _normalize_required_identifier(*, value: str, field_name: str) -> str:
    normalized_value = value.strip()
    if normalized_value == "":
        raise ValueError(f"{field_name} must not be blank.")
    return normalized_value


def _prune_expired_locked(*, now: datetime) -> None:
    expired_keys = [
        key
        for key, expires_at in _MEMORY_EXPIRY.items()
        if expires_at <= now
    ]
    for key in expired_keys:
        _MEMORY_EXPIRY.pop(key, None)
        _MEMORY_STORE.pop(key, None)


def _utcnow() -> datetime:
    return datetime.now(UTC)


__all__ = [
    "append_operator_memory_turn",
    "clear_operator_memory",
    "get_recent_operator_memory",
    "reset_operator_memory_store",
]
