"""
Grounded recruiter-question answering over the read-only MCP adapter surface.
"""

from __future__ import annotations

import json
import re
from typing import Any, Literal

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, ConfigDict, Field

from backend.llm.models import DEFAULT_REASONING_MODEL_PROFILE
from backend.llm.providers import build_langchain_chat_model
from backend.services import mcp_read_adapter
from backend.services.mcp_read_adapter import McpReadAdapterError

RouteIntent = Literal["role_search", "company_context", "role_search_with_company"]

_ROLE_SEARCH_TERMS = (
    "fit",
    "fits",
    "shortlist",
    "job description",
    "role brief",
    "role",
    "candidate for",
    "best candidate",
)
_COMPANY_CONTEXT_TERMS = (
    "who do we know at",
    "spoken to",
    "interaction",
    "contacts",
    "hiring manager",
    "jobs at",
    "opportunities at",
    "company",
)


class RecruiterQuestionAnsweringError(RuntimeError):
    """
    Raised when grounded recruiter Q&A fails.
    """

    def __init__(
        self,
        message: str,
        *,
        stage: str,
        details: list[dict[str, Any]] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.stage = stage
        self.details = details or []


class RecruiterAnswerSelection(BaseModel):
    """
    Structured recruiter-facing grounded answer.
    """

    model_config = ConfigDict(extra="forbid")

    answer: str = Field(min_length=1)
    evidence_bullets: list[str] = Field(default_factory=list)
    cited_candidate_ids: list[str] = Field(default_factory=list)
    cited_contact_ids: list[str] = Field(default_factory=list)
    cited_job_ids: list[str] = Field(default_factory=list)
    cited_opportunity_ids: list[str] = Field(default_factory=list)
    cited_interaction_ids: list[str] = Field(default_factory=list)
    follow_up_questions: list[str] = Field(default_factory=list)


def answer_recruiter_question(
    *,
    question: str,
    search_limit: int = 10,
    candidate_pool_limit: int = 25,
    shortlist_limit: int = 5,
    company_context_limit: int = 5,
) -> dict[str, Any]:
    """
    Return one grounded recruiter-facing answer over bounded canonical evidence.
    """

    normalized_question = question.strip()
    if normalized_question == "":
        raise RecruiterQuestionAnsweringError(
            "Question must not be blank.",
            stage="validation",
            details=[{"field": "question"}],
        )

    retrieval_plan = _build_retrieval_plan(normalized_question)

    role_search_result: dict[str, Any] | None = None
    company_context_result: dict[str, Any] | None = None

    try:
        if retrieval_plan["run_role_search"]:
            role_search_result = mcp_read_adapter.search_candidates_for_role(
                role_brief=normalized_question,
                search_limit=search_limit,
                candidate_pool_limit=candidate_pool_limit,
                shortlist_limit=shortlist_limit,
                include_shortlist=True,
            )
        if retrieval_plan["company_name"] is not None:
            company_context_result = mcp_read_adapter.search_company_context(
                company_name=retrieval_plan["company_name"],
                candidate_limit=company_context_limit,
                contact_limit=company_context_limit,
                interaction_limit=company_context_limit,
                job_limit=company_context_limit,
                opportunity_limit=company_context_limit,
            )
    except McpReadAdapterError as exc:
        raise RecruiterQuestionAnsweringError(
            "Recruiter question retrieval failed.",
            stage="retrieval",
            details=[
                {"tool": exc.tool},
                *exc.details,
            ],
        ) from exc

    if not _has_any_evidence(
        role_search_result=role_search_result,
        company_context_result=company_context_result,
    ):
        return {
            "question": normalized_question,
            "route_intent": retrieval_plan["route_intent"],
            "retrieval_plan": retrieval_plan,
            "answer": (
                "No grounded evidence was found for that question in the current "
                "candidate and company context."
            ),
            "evidence_bullets": [],
            "candidates": [],
            "contacts": [],
            "jobs": [],
            "opportunities": [],
            "interactions": [],
            "follow_up_questions": [],
        }

    answer_selection = _generate_grounded_answer(
        question=normalized_question,
        retrieval_plan=retrieval_plan,
        role_search_result=role_search_result,
        company_context_result=company_context_result,
    )

    candidates = _collect_candidates(
        role_search_result=role_search_result,
        cited_candidate_ids=answer_selection.cited_candidate_ids,
    )
    contacts = _collect_items_by_id(
        items=(company_context_result or {}).get("contacts") or [],
        cited_ids=answer_selection.cited_contact_ids,
        key="contact_id",
    )
    jobs = _collect_items_by_id(
        items=(company_context_result or {}).get("jobs") or [],
        cited_ids=answer_selection.cited_job_ids,
        key="job_id",
    )
    opportunities = _collect_items_by_id(
        items=(company_context_result or {}).get("opportunities") or [],
        cited_ids=answer_selection.cited_opportunity_ids,
        key="opportunity_id",
    )
    interactions = _collect_items_by_id(
        items=(company_context_result or {}).get("interactions") or [],
        cited_ids=answer_selection.cited_interaction_ids,
        key="interaction_id",
    )

    return {
        "question": normalized_question,
        "route_intent": retrieval_plan["route_intent"],
        "retrieval_plan": retrieval_plan,
        "answer": answer_selection.answer,
        "evidence_bullets": list(answer_selection.evidence_bullets),
        "candidates": candidates,
        "contacts": contacts,
        "jobs": jobs,
        "opportunities": opportunities,
        "interactions": interactions,
        "follow_up_questions": list(answer_selection.follow_up_questions),
    }


def _build_retrieval_plan(question: str) -> dict[str, Any]:
    normalized_question = question.lower()
    detected_company_name = _detect_company_name(question)

    wants_role_search = any(term in normalized_question for term in _ROLE_SEARCH_TERMS)
    wants_company_context = (
        detected_company_name is not None
        and any(term in normalized_question for term in _COMPANY_CONTEXT_TERMS)
    )

    if wants_role_search and detected_company_name is not None:
        route_intent: RouteIntent = "role_search_with_company"
    elif wants_company_context:
        route_intent = "company_context"
    else:
        route_intent = "role_search"

    return {
        "route_intent": route_intent,
        "company_name": detected_company_name,
        "run_role_search": route_intent in ("role_search", "role_search_with_company"),
    }


def _detect_company_name(question: str) -> str | None:
    directory = mcp_read_adapter.list_company_directory(limit=20000)
    companies = directory["companies"]
    normalized_question = question.lower()

    matched_companies = [
        company
        for company in companies
        if company.lower() in normalized_question
    ]
    if matched_companies:
        return max(matched_companies, key=len)

    trailing_match = re.search(r"\bat\s+([A-Za-z0-9& .,'/-]{3,})", question)
    if trailing_match is None:
        return None

    guessed_company = trailing_match.group(1).strip(" .?")
    return guessed_company or None


def _has_any_evidence(
    *,
    role_search_result: dict[str, Any] | None,
    company_context_result: dict[str, Any] | None,
) -> bool:
    if role_search_result is not None:
        if role_search_result.get("search_results") or role_search_result.get(
            "shortlist_results"
        ):
            return True

    if company_context_result is not None:
        for field_name in (
            "candidates",
            "contacts",
            "interactions",
            "jobs",
            "opportunities",
        ):
            if company_context_result.get(field_name):
                return True

    return False


def _generate_grounded_answer(
    *,
    question: str,
    retrieval_plan: dict[str, Any],
    role_search_result: dict[str, Any] | None,
    company_context_result: dict[str, Any] | None,
) -> RecruiterAnswerSelection:
    system_prompt = (
        "You are a recruiter operations assistant. "
        "Answer the question using only the grounded evidence supplied to you. "
        "Do not invent companies, contacts, candidates, jobs, opportunities, or "
        "interactions that are not present in the payload. "
        "Be concise, concrete, and recruiter-usable. "
        "If the evidence is incomplete, say so plainly."
    )

    user_prompt = (
        f"Recruiter question:\n{question}\n\n"
        f"Retrieval plan:\n{json.dumps(retrieval_plan, indent=2, ensure_ascii=False)}\n\n"
        "Grounded role-search evidence:\n"
        f"{json.dumps(role_search_result, indent=2, ensure_ascii=False)}\n\n"
        "Grounded company-context evidence:\n"
        f"{json.dumps(company_context_result, indent=2, ensure_ascii=False)}\n\n"
        "Write a short direct answer, then evidence bullets. "
        "Only cite IDs that appear in the supplied evidence."
    )

    prompt = ChatPromptTemplate.from_messages(
        [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt),
        ]
    )

    try:
        chat_model = build_langchain_chat_model(
            profile=DEFAULT_REASONING_MODEL_PROFILE,
        )
        structured_model = chat_model.with_structured_output(
            RecruiterAnswerSelection
        )
        chain = prompt | structured_model
        raw_result = chain.invoke({})
    except Exception as exc:  # pragma: no cover - exercised via service tests
        raise RecruiterQuestionAnsweringError(
            "Recruiter answer generation failed during LLM synthesis.",
            stage="llm_answer",
            details=[{"error_type": exc.__class__.__name__, "message": str(exc)}],
        ) from exc

    if isinstance(raw_result, RecruiterAnswerSelection):
        return raw_result

    if isinstance(raw_result, dict):
        return RecruiterAnswerSelection(**raw_result)

    raise RecruiterQuestionAnsweringError(
        "Recruiter answer returned an unexpected response shape.",
        stage="llm_answer",
        details=[{"result_type": raw_result.__class__.__name__}],
    )


def _collect_candidates(
    *,
    role_search_result: dict[str, Any] | None,
    cited_candidate_ids: list[str],
) -> list[dict[str, Any]]:
    if role_search_result is None:
        return []

    preferred_candidates = (
        role_search_result.get("shortlist_results")
        or role_search_result.get("search_results")
        or []
    )
    return _collect_items_by_id(
        items=preferred_candidates,
        cited_ids=cited_candidate_ids,
        key="candidate_id",
    )


def _collect_items_by_id(
    *,
    items: list[dict[str, Any]],
    cited_ids: list[str],
    key: str,
) -> list[dict[str, Any]]:
    if not items:
        return []

    items_by_id = {
        str(item.get(key)): item
        for item in items
        if item.get(key) is not None
    }
    if cited_ids:
        collected = [
            items_by_id[item_id]
            for item_id in cited_ids
            if item_id in items_by_id
        ]
        if collected:
            return collected

    return items[:5]


__all__ = [
    "RecruiterAnswerSelection",
    "RecruiterQuestionAnsweringError",
    "answer_recruiter_question",
]
