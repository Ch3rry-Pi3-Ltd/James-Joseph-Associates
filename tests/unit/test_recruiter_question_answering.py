from __future__ import annotations

import pytest

from backend.services import recruiter_question_answering
from backend.services.recruiter_question_answering import (
    RecruiterAnswerSelection,
    RecruiterQuestionAnsweringError,
    answer_recruiter_question,
)


class _FakeChain:
    def __init__(self, result: object) -> None:
        self._result = result

    def invoke(self, _: dict[str, object]) -> object:
        return self._result


class _FakeStructuredModel:
    def __init__(self, result: object) -> None:
        self._result = result

    def __call__(self, _: object) -> object:
        return self._result


class _FakeChatModel:
    def __init__(self, result: object) -> None:
        self._result = result

    def with_structured_output(self, _: object) -> _FakeStructuredModel:
        return _FakeStructuredModel(self._result)


def test_answer_recruiter_question_rejects_blank_input() -> None:
    with pytest.raises(RecruiterQuestionAnsweringError) as exc_info:
        answer_recruiter_question(question="   ")

    assert exc_info.value.stage == "validation"


def test_answer_recruiter_question_routes_role_brief_and_returns_grounded_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        recruiter_question_answering.mcp_read_adapter,
        "list_company_directory",
        lambda **kwargs: {"count": 0, "companies": []},
    )
    monkeypatch.setattr(
        recruiter_question_answering.mcp_read_adapter,
        "search_candidates_for_role",
        lambda **kwargs: {
            "search_results": [{"candidate_id": "cand-1", "full_name": "Alice"}],
            "shortlist_results": [{"candidate_id": "cand-1", "fit_score": 94}],
        },
    )
    monkeypatch.setattr(
        recruiter_question_answering,
        "build_langchain_chat_model",
        lambda **kwargs: _FakeChatModel(
            RecruiterAnswerSelection(
                answer="Alice is the strongest fit.",
                evidence_bullets=["Best match on Rust and trading systems."],
                cited_candidate_ids=["cand-1"],
                follow_up_questions=["Open the CV and verify recent production experience."],
            )
        ),
    )

    result = answer_recruiter_question(
        question="Which candidates best fit this Rust trading role?",
    )

    assert result["route_intent"] == "role_search"
    assert result["answer"] == "Alice is the strongest fit."
    assert result["candidates"] == [{"candidate_id": "cand-1", "fit_score": 94}]


def test_answer_recruiter_question_merges_company_context_when_company_detected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        recruiter_question_answering.mcp_read_adapter,
        "list_company_directory",
        lambda **kwargs: {"count": 2, "companies": ["Goldman Sachs", "Acme"]},
    )
    monkeypatch.setattr(
        recruiter_question_answering.mcp_read_adapter,
        "search_candidates_for_role",
        lambda **kwargs: {
            "search_results": [{"candidate_id": "cand-1", "full_name": "Alice"}],
            "shortlist_results": [{"candidate_id": "cand-1", "fit_score": 90}],
        },
    )
    monkeypatch.setattr(
        recruiter_question_answering.mcp_read_adapter,
        "search_company_context",
        lambda **kwargs: {
            "company_name": "Goldman Sachs",
            "candidates": [],
            "contacts": [{"contact_id": "contact-1", "full_name": "Bob"}],
            "interactions": [{"interaction_id": "int-1"}],
            "jobs": [{"job_id": "job-1"}],
            "opportunities": [{"opportunity_id": "opp-1"}],
        },
    )
    monkeypatch.setattr(
        recruiter_question_answering,
        "build_langchain_chat_model",
        lambda **kwargs: _FakeChatModel(
            RecruiterAnswerSelection(
                answer="We have one known contact and one prior interaction at Goldman Sachs.",
                evidence_bullets=["Known contact Bob.", "Prior interaction int-1."],
                cited_candidate_ids=["cand-1"],
                cited_contact_ids=["contact-1"],
                cited_interaction_ids=["int-1"],
                cited_job_ids=["job-1"],
                cited_opportunity_ids=["opp-1"],
            )
        ),
    )

    result = answer_recruiter_question(
        question="Who do we know at Goldman Sachs for this Rust role?",
    )

    assert result["route_intent"] == "role_search_with_company"
    assert result["contacts"] == [{"contact_id": "contact-1", "full_name": "Bob"}]
    assert result["interactions"] == [{"interaction_id": "int-1"}]
    assert result["jobs"] == [{"job_id": "job-1"}]
    assert result["opportunities"] == [{"opportunity_id": "opp-1"}]


def test_answer_recruiter_question_returns_fallback_when_no_evidence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        recruiter_question_answering.mcp_read_adapter,
        "list_company_directory",
        lambda **kwargs: {"count": 0, "companies": []},
    )
    monkeypatch.setattr(
        recruiter_question_answering.mcp_read_adapter,
        "search_candidates_for_role",
        lambda **kwargs: {
            "search_results": [],
            "shortlist_results": [],
        },
    )

    result = answer_recruiter_question(question="Find candidates for this role")

    assert result["answer"].startswith("No grounded evidence was found")
    assert result["candidates"] == []


def test_answer_recruiter_question_wraps_llm_failures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        recruiter_question_answering.mcp_read_adapter,
        "list_company_directory",
        lambda **kwargs: {"count": 0, "companies": []},
    )
    monkeypatch.setattr(
        recruiter_question_answering.mcp_read_adapter,
        "search_candidates_for_role",
        lambda **kwargs: {
            "search_results": [{"candidate_id": "cand-1"}],
            "shortlist_results": [],
        },
    )

    def _raise(**kwargs: object) -> None:
        raise RuntimeError("LLM offline")

    monkeypatch.setattr(
        recruiter_question_answering,
        "build_langchain_chat_model",
        _raise,
    )

    with pytest.raises(RecruiterQuestionAnsweringError) as exc_info:
        answer_recruiter_question(question="Find candidates for this role")

    assert exc_info.value.stage == "llm_answer"


def test_answer_recruiter_question_uses_and_appends_session_memory(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    appended_turns: list[dict[str, object]] = []

    monkeypatch.setattr(
        recruiter_question_answering.mcp_read_adapter,
        "list_company_directory",
        lambda **kwargs: {"count": 0, "companies": []},
    )
    monkeypatch.setattr(
        recruiter_question_answering.mcp_read_adapter,
        "search_candidates_for_role",
        lambda **kwargs: {
            "search_results": [{"candidate_id": "cand-1", "full_name": "Alice"}],
            "shortlist_results": [{"candidate_id": "cand-1", "fit_score": 94}],
        },
    )
    monkeypatch.setattr(
        recruiter_question_answering,
        "get_recent_operator_memory",
        lambda **kwargs: [{"question": "Old Q", "answer": "Old A", "metadata": {}}],
    )
    monkeypatch.setattr(
        recruiter_question_answering,
        "append_operator_memory_turn",
        lambda **kwargs: appended_turns.append(kwargs),
    )
    monkeypatch.setattr(
        recruiter_question_answering,
        "build_langchain_chat_model",
        lambda **kwargs: _FakeChatModel(
            RecruiterAnswerSelection(
                answer="Alice is still the strongest fit.",
                evidence_bullets=["Best match on Rust and trading systems."],
                cited_candidate_ids=["cand-1"],
            )
        ),
    )

    result = answer_recruiter_question(
        question="Which candidates best fit this Rust trading role?",
        user_id="user-1",
        conversation_id="thread-1",
    )

    assert result["session_memory_turns_used"] == 1
    assert appended_turns[0]["user_id"] == "user-1"
    assert appended_turns[0]["conversation_id"] == "thread-1"
