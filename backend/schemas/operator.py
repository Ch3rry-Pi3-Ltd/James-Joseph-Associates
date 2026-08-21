"""
Read-only operator API schemas for recruiter-style MCP/API clients.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from backend.core.llm_safety import (
    MAX_LLM_IDENTIFIER_CHARACTERS,
    MAX_LLM_INPUT_CHARACTERS,
)


class OperatorSearchCandidatesRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role_brief: str = Field(min_length=1, max_length=MAX_LLM_INPUT_CHARACTERS)
    search_limit: int = Field(default=10, ge=1, le=50)
    candidate_pool_limit: int = Field(default=25, ge=1, le=100)
    shortlist_limit: int = Field(default=5, ge=1, le=10)
    include_shortlist: bool = True


class OperatorSearchCandidatesResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role_brief: str
    retrieval_query: str
    detected_target_company: str | None = None
    candidate_pool_size: int = Field(ge=0)
    search_limit: int = Field(ge=1)
    candidate_pool_limit: int = Field(ge=1)
    shortlist_limit: int = Field(ge=1)
    retrieval_metadata: dict[str, Any] = Field(default_factory=dict)
    search_results: list[dict[str, Any]] = Field(default_factory=list)
    shortlist_results: list[dict[str, Any]] = Field(default_factory=list)


class OperatorCandidateProfileResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    candidate_id: str
    person_id: str
    full_name: str | None = None
    current_title: str | None = None
    current_company_name: str | None = None
    candidate_status: str | None = None
    resume_updated_at: datetime | str | None = None
    skills: list[dict[str, Any]] = Field(default_factory=list)
    contacts: list[dict[str, Any]] = Field(default_factory=list)
    interactions: list[dict[str, Any]] = Field(default_factory=list)
    jobs: list[dict[str, Any]] = Field(default_factory=list)
    opportunities: list[dict[str, Any]] = Field(default_factory=list)


class OperatorCandidateResumeReferenceResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    candidate_id: str
    document_id: str
    file_name: str
    content_type: str
    download_url: str
    source_system: str | None = None
    source_uri: str | None = None


class OperatorCompanyContextRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    company_name: str = Field(min_length=1, max_length=MAX_LLM_IDENTIFIER_CHARACTERS)
    candidate_limit: int = Field(default=10, ge=1, le=50)
    contact_limit: int = Field(default=10, ge=1, le=50)
    interaction_limit: int = Field(default=10, ge=1, le=50)
    job_limit: int = Field(default=10, ge=1, le=50)
    opportunity_limit: int = Field(default=10, ge=1, le=50)


class OperatorCompanyContextResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    company_name: str
    candidates: list[dict[str, Any]] = Field(default_factory=list)
    contacts: list[dict[str, Any]] = Field(default_factory=list)
    interactions: list[dict[str, Any]] = Field(default_factory=list)
    jobs: list[dict[str, Any]] = Field(default_factory=list)
    opportunities: list[dict[str, Any]] = Field(default_factory=list)


class OperatorCompanyDirectoryResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    count: int = Field(ge=0)
    companies: list[str] = Field(default_factory=list)
    company_records: list[dict[str, Any]] = Field(default_factory=list)


class OperatorCompanyLeadDiscoveryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    candidate_id: str = Field(min_length=1, max_length=MAX_LLM_IDENTIFIER_CHARACTERS)
    company_name: str = Field(min_length=1, max_length=MAX_LLM_IDENTIFIER_CHARACTERS)
    limit: int = Field(default=10, ge=1, le=50)


class OperatorQuestionAnswerRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question: str = Field(min_length=1, max_length=MAX_LLM_INPUT_CHARACTERS)
    search_limit: int = Field(default=10, ge=1, le=50)
    candidate_pool_limit: int = Field(default=25, ge=1, le=100)
    shortlist_limit: int = Field(default=5, ge=1, le=10)
    company_context_limit: int = Field(default=5, ge=1, le=20)
    user_id: str | None = Field(
        default=None,
        max_length=MAX_LLM_IDENTIFIER_CHARACTERS,
    )
    conversation_id: str | None = Field(
        default=None,
        max_length=MAX_LLM_IDENTIFIER_CHARACTERS,
    )


class OperatorQuestionAnswerResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question: str
    route_intent: str
    retrieval_plan: dict[str, Any]
    session_memory_turns_used: int = Field(ge=0)
    answer: str
    evidence_bullets: list[str] = Field(default_factory=list)
    candidates: list[dict[str, Any]] = Field(default_factory=list)
    contacts: list[dict[str, Any]] = Field(default_factory=list)
    jobs: list[dict[str, Any]] = Field(default_factory=list)
    opportunities: list[dict[str, Any]] = Field(default_factory=list)
    interactions: list[dict[str, Any]] = Field(default_factory=list)
    follow_up_questions: list[str] = Field(default_factory=list)


class OperatorMemoryClearRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: str = Field(min_length=1, max_length=MAX_LLM_IDENTIFIER_CHARACTERS)
    conversation_id: str | None = Field(
        default=None,
        max_length=MAX_LLM_IDENTIFIER_CHARACTERS,
    )


class OperatorMemoryClearResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cleared: bool
    user_id: str
    conversation_id: str | None = None
