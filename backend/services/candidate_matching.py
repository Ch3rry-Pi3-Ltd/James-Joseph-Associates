"""
Candidate shortlist helpers for role-brief matching.

This module turns the existing canonical resume search into a recruiter-facing
shortlist workflow:

- retrieve candidate resumes from Supabase
- send the retrieved pool plus the job description to the LLM
- return the top shortlisted candidates with reasons
"""

from __future__ import annotations

import json
from datetime import date, datetime
from typing import Any
from uuid import UUID, uuid4

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, ConfigDict, Field

from backend.core.llm_safety import (
    MAX_LLM_INPUT_CHARACTERS,
    UNTRUSTED_CONTENT_POLICY,
)
from backend.core.observability import observe_stage, observe_workflow
from backend.evaluation.quality_checks import validate_claim_evidence
from backend.llm.models import DEFAULT_REASONING_MODEL_PROFILE
from backend.llm.providers import build_langchain_chat_model
from backend.llm.telemetry import invoke_with_model_telemetry
from backend.services.candidate_profiles import (
    build_candidate_profile,
    discover_company_context,
)
from backend.services.candidate_retrieval import search_candidates_hybrid
from backend.services.candidate_source_metadata import (
    attach_candidate_source_metadata,
)


_PROFILE_SUMMARY_CHARACTER_LIMIT = 1200
_PROFILE_HEADLINE_CHARACTER_LIMIT = 400
_PROFILE_SKILL_LIMIT = 24
_SHORTLIST_WORKFLOW_VERSION = "1.0"
_SHORTLIST_PROMPT_VERSION = "candidate-shortlist-v1.0"
_REASONING_MODEL_PROFILE_VERSION = "default-reasoning-v1"


class CandidateMatchingError(RuntimeError):
    """
    Raised when candidate shortlisting fails after retrieval.
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


class CandidateEvidenceClaim(BaseModel):
    """One generated statement tied to retrievable evidence references."""

    model_config = ConfigDict(extra="forbid")

    claim: str = Field(min_length=1)
    evidence_refs: list[str] = Field(min_length=1)


class CandidateShortlistAssessment(BaseModel):
    """
    One candidate selected by the LLM shortlist step.
    """

    model_config = ConfigDict(extra="forbid")

    candidate_id: str = Field(min_length=1)
    fit_score: int = Field(ge=0, le=100)
    fit_summary: CandidateEvidenceClaim
    strengths: list[CandidateEvidenceClaim] = Field(default_factory=list)
    gaps: list[CandidateEvidenceClaim] = Field(default_factory=list)


class CandidateShortlistSelection(BaseModel):
    """
    Structured shortlist returned by the LLM.
    """

    model_config = ConfigDict(extra="forbid")

    shortlisted_candidates: list[CandidateShortlistAssessment] = Field(
        default_factory=list,
    )


def build_candidate_job_description_shortlist(
    *,
    job_description: str,
    retrieval_limit: int = 25,
    shortlist_limit: int = 3,
) -> dict[str, Any]:
    """
    Return a recruiter-facing shortlist for one free-text job description.
    """

    match_run_id = str(uuid4())
    with observe_workflow(
        workflow="candidate_shortlist",
        workflow_version=_SHORTLIST_WORKFLOW_VERSION,
        run_id=match_run_id,
    ):
        return _build_candidate_job_description_shortlist(
            job_description=job_description,
            retrieval_limit=retrieval_limit,
            shortlist_limit=shortlist_limit,
            match_run_id=match_run_id,
        )


def _build_candidate_job_description_shortlist(
    *,
    job_description: str,
    retrieval_limit: int,
    shortlist_limit: int,
    match_run_id: str,
) -> dict[str, Any]:
    """Execute the observed shortlist stages for one established run ID."""

    with observe_stage("input_validation", "validation") as validation_stage:
        normalized_job_description = job_description.strip()
        if normalized_job_description == "":
            raise CandidateMatchingError(
                "Job description must not be blank.",
                stage="validation",
                details=[{"field": "job_description"}],
            )
        if len(normalized_job_description) > MAX_LLM_INPUT_CHARACTERS:
            raise CandidateMatchingError(
                "Job description is too long.",
                stage="validation",
                details=[
                    {
                        "field": "job_description",
                        "max_length": MAX_LLM_INPUT_CHARACTERS,
                    }
                ],
            )

        bounded_retrieval_limit = max(1, min(int(retrieval_limit), 100))
        bounded_shortlist_limit = max(1, min(int(shortlist_limit), 10))
        validation_stage.set_metrics(
            input_items=1,
            validation_rule_count=4,
            retrieval_limit=bounded_retrieval_limit,
            shortlist_limit=bounded_shortlist_limit,
        )

    with observe_stage(
        "hybrid_graph_retrieval",
        "retrieval",
        metrics={
            "retrieval_mode": "hybrid_graph",
            "retrieval_limit": bounded_retrieval_limit,
        },
    ) as retrieval_stage:
        retrieved_candidates = retrieve_candidates_with_graph_context(
            query=normalized_job_description,
            limit=bounded_retrieval_limit,
        )
        retrieval_stage.set_metrics(candidate_count=len(retrieved_candidates))
    if not retrieved_candidates:
        with observe_stage(
            "response_assembly",
            "response",
            metrics={"candidate_count": 0, "output_items": 0},
        ):
            return {
                "match_run_id": match_run_id,
                "job_description": normalized_job_description,
                "retrieval_limit": bounded_retrieval_limit,
                "shortlist_limit": bounded_shortlist_limit,
                "retrieved_candidate_count": 0,
                "shortlisted_candidates": [],
            }

    shortlist_assessments = _rank_retrieved_candidates_for_job_description(
        job_description=normalized_job_description,
        retrieved_candidates=retrieved_candidates,
        shortlist_limit=bounded_shortlist_limit,
        run_id=match_run_id,
    )

    candidates_by_id = {
        str(candidate["candidate_id"]): candidate for candidate in retrieved_candidates
    }
    shortlisted_candidates: list[dict[str, Any]] = []
    seen_candidate_ids: set[str] = set()

    for assessment in shortlist_assessments:
        candidate_id = assessment.candidate_id.strip()
        if candidate_id == "" or candidate_id in seen_candidate_ids:
            continue
        matched_candidate = candidates_by_id.get(candidate_id)
        if matched_candidate is None:
            continue

        shortlisted_candidates.append(
            {
                "candidate_id": candidate_id,
                "person_id": _json_safe_value(matched_candidate["person_id"]),
                "full_name": _json_safe_value(matched_candidate.get("full_name")),
                "current_title": _json_safe_value(
                    matched_candidate.get("current_title")
                ),
                "candidate_status": _json_safe_value(
                    matched_candidate.get("candidate_status")
                ),
                "current_company_name": _json_safe_value(
                    matched_candidate.get("current_company_name")
                ),
                "resume_updated_at": _json_safe_value(
                    matched_candidate.get("resume_updated_at")
                ),
                "document_id": _json_safe_value(matched_candidate.get("document_id")),
                "document_title": _json_safe_value(
                    matched_candidate.get("document_title")
                ),
                "document_source_uri": _json_safe_value(
                    matched_candidate.get("document_source_uri")
                ),
                "retrieval_score": float(matched_candidate.get("match_score") or 0.0),
                "retrieval_sources": list(
                    _json_safe_value(matched_candidate.get("retrieval_sources") or [])
                ),
                "text_rank": _json_safe_value(matched_candidate.get("text_rank")),
                "semantic_rank": _json_safe_value(
                    matched_candidate.get("semantic_rank")
                ),
                "text_score": float(matched_candidate.get("text_score") or 0.0)
                if matched_candidate.get("text_score") is not None
                else None,
                "semantic_score": float(matched_candidate.get("semantic_score") or 0.0)
                if matched_candidate.get("semantic_score") is not None
                else None,
                "semantic_block_type": _json_safe_value(
                    matched_candidate.get("semantic_block_type")
                ),
                "semantic_block_label": _json_safe_value(
                    matched_candidate.get("semantic_block_label")
                ),
                "source_systems": list(
                    _json_safe_value(matched_candidate.get("source_systems") or [])
                ),
                "source_details": list(
                    _json_safe_value(matched_candidate.get("source_details") or [])
                ),
                "source_category": _json_safe_value(
                    matched_candidate.get("source_category") or "unknown"
                ),
                "graph_context_score": _json_safe_value(
                    matched_candidate.get("graph_context_score")
                ),
                "ranking_input_score": _json_safe_value(
                    matched_candidate.get("ranking_input_score")
                ),
                "fit_score": assessment.fit_score,
                "fit_summary": assessment.fit_summary.claim,
                "strengths": [claim.claim for claim in assessment.strengths],
                "gaps": [claim.claim for claim in assessment.gaps],
                "claim_evidence": {
                    "fit_summary": assessment.fit_summary.model_dump(),
                    "strengths": [claim.model_dump() for claim in assessment.strengths],
                    "gaps": [claim.model_dump() for claim in assessment.gaps],
                },
                "match_excerpt": _json_safe_value(
                    matched_candidate.get("match_excerpt")
                ),
                "graph_evidence": _json_safe_value(
                    matched_candidate.get("graph_evidence")
                ),
            }
        )
        seen_candidate_ids.add(candidate_id)

        if len(shortlisted_candidates) >= bounded_shortlist_limit:
            break

    with observe_stage(
        "response_assembly",
        "response",
        metrics={
            "candidate_count": len(retrieved_candidates),
            "output_items": len(shortlisted_candidates),
        },
    ):
        return {
            "match_run_id": match_run_id,
            "job_description": normalized_job_description,
            "retrieval_limit": bounded_retrieval_limit,
            "shortlist_limit": bounded_shortlist_limit,
            "retrieved_candidate_count": len(retrieved_candidates),
            "shortlisted_candidates": shortlisted_candidates,
        }


def retrieve_candidates_with_graph_context(
    *,
    query: str,
    limit: int = 25,
) -> list[dict[str, Any]]:
    """Return the deterministic pre-LLM graph-assisted retrieval stage."""

    retrieved_candidates = search_candidates_hybrid(
        query=query,
        limit=limit,
        include_text=True,
        include_semantic=True,
    )
    if not retrieved_candidates:
        return []

    # Provenance is one batched read for the whole retrieval pool. Graph
    # profile assembly reuses it instead of issuing another source lookup per
    # candidate and then repeating the batch after ranking.
    retrieved_candidates = attach_candidate_source_metadata(retrieved_candidates)
    retrieved_candidates = _attach_graph_evidence_to_candidates(
        retrieved_candidates,
        per_candidate_limit=3,
    )
    return _score_candidates_with_graph_context(retrieved_candidates)


def _rank_retrieved_candidates_for_job_description(
    *,
    job_description: str,
    retrieved_candidates: list[dict[str, Any]],
    shortlist_limit: int,
    run_id: str | None = None,
) -> list[CandidateShortlistAssessment]:
    """
    Ask the reasoning model to choose the strongest candidates from retrieval.
    """

    system_prompt = (
        "You are a recruitment assistant. "
        "You will receive a free-text job description and a retrieved pool of "
        "candidate resume matches. Choose only the strongest candidates for the role. "
        "Base your decision on the provided candidate data only. "
        "Do not invent missing experience. "
        "Prefer concrete evidence over generic recruiter language. "
        "Structured profile evidence and CV evidence are both valid evidence. "
        "Do not penalize a candidate merely because no CV document is attached; "
        "assess profile-only candidates on the supplied headline, summary, role, "
        "company, skills, and retrieval evidence. "
        f"{UNTRUSTED_CONTENT_POLICY} "
        "Return no more than the requested shortlist limit."
    )

    candidate_payload = [
        {
            "candidate_id": _json_safe_value(candidate["candidate_id"]),
            "full_name": _json_safe_value(candidate.get("full_name")),
            "current_title": _json_safe_value(candidate.get("current_title")),
            "candidate_status": _json_safe_value(candidate.get("candidate_status")),
            "current_company_name": _json_safe_value(
                candidate.get("current_company_name")
            ),
            "resume_updated_at": _json_safe_value(candidate.get("resume_updated_at")),
            "document_title": _json_safe_value(candidate.get("document_title")),
            "retrieval_score": _json_safe_value(candidate.get("match_score")),
            "retrieval_sources": _json_safe_value(
                candidate.get("retrieval_sources") or []
            ),
            "text_rank": _json_safe_value(candidate.get("text_rank")),
            "semantic_rank": _json_safe_value(candidate.get("semantic_rank")),
            "text_score": _json_safe_value(candidate.get("text_score")),
            "semantic_score": _json_safe_value(candidate.get("semantic_score")),
            "semantic_block_type": _json_safe_value(
                candidate.get("semantic_block_type")
            ),
            "semantic_block_label": _json_safe_value(
                candidate.get("semantic_block_label")
            ),
            "graph_context_score": _json_safe_value(
                candidate.get("graph_context_score")
            ),
            "ranking_input_score": _json_safe_value(
                candidate.get("ranking_input_score")
            ),
            "match_excerpt": _json_safe_value(candidate.get("match_excerpt")),
            "evidence_catalog": _build_candidate_evidence_catalog(candidate),
        }
        for candidate in retrieved_candidates
    ]

    user_prompt = (
        "<untrusted_job_description>\n"
        f"{job_description}\n"
        "</untrusted_job_description>\n\n"
        f"Return the top {shortlist_limit} candidates only.\n\n"
        "<untrusted_retrieved_candidates>\n"
        f"{json.dumps(candidate_payload, indent=2, ensure_ascii=False)}\n"
        "</untrusted_retrieved_candidates>\n\n"
        "For each shortlisted candidate:\n"
        "- use the exact candidate_id from the supplied list\n"
        "- assign a fit_score from 0 to 100\n"
        "- write one brief fit_summary claim grounded in the evidence_catalog\n"
        "- list concrete strengths as short evidence-backed claims\n"
        "- list gaps only when they are missing or unclear in the evidence\n"
        "- attach one or more exact evidence_refs from that candidate's evidence_catalog to every fit_summary, strength, and gap claim\n"
        "- avoid generic filler such as 'strong background' unless you name the actual area\n"
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
            CandidateShortlistSelection
        )
        chain = prompt | structured_model
        raw_result, _ = invoke_with_model_telemetry(
            chain,
            {},
            workflow="candidate_shortlist_reranking",
            provider=DEFAULT_REASONING_MODEL_PROFILE.provider.value,
            model=DEFAULT_REASONING_MODEL_PROFILE.model_name,
            run_id=run_id,
            prompt_version=_SHORTLIST_PROMPT_VERSION,
            model_profile_version=_REASONING_MODEL_PROFILE_VERSION,
        )
    except Exception as exc:  # pragma: no cover - exercised via service tests
        raise CandidateMatchingError(
            "Candidate shortlisting failed during LLM ranking.",
            stage="llm_ranking",
            details=[{"error_type": exc.__class__.__name__, "message": str(exc)}],
        ) from exc

    if isinstance(raw_result, CandidateShortlistSelection):
        assessments = raw_result.shortlisted_candidates
    elif isinstance(raw_result, dict):
        assessments = CandidateShortlistSelection(**raw_result).shortlisted_candidates
    else:
        raise CandidateMatchingError(
            "Candidate shortlisting returned an unexpected response shape.",
            stage="llm_ranking",
            details=[{"result_type": raw_result.__class__.__name__}],
        )

    with observe_stage(
        "grounding_validation",
        "validation",
        metrics={
            "input_items": len(assessments),
            "validation_rule_count": 3,
        },
    ) as validation_stage:
        _validate_assessment_grounding(
            assessments=assessments,
            retrieved_candidates=retrieved_candidates,
        )
        validation_stage.set_metrics(output_items=len(assessments))
    return assessments


def _build_candidate_evidence_catalog(
    candidate: dict[str, Any],
) -> list[dict[str, Any]]:
    """Return bounded, referenceable ranking evidence without contact routes."""

    candidate_id = str(candidate["candidate_id"])
    catalog: list[dict[str, Any]] = []

    def add(reference: str, label: str, value: Any) -> None:
        safe_value = _json_safe_value(value)
        if safe_value in (None, "", [], {}):
            return
        catalog.append(
            {
                "evidence_ref": reference,
                "label": label,
                "value": safe_value,
            }
        )

    add(
        f"candidate:{candidate_id}:retrieval",
        "Retrieved match evidence",
        candidate.get("match_excerpt"),
    )
    add(
        f"candidate:{candidate_id}:current_title",
        "Current title",
        candidate.get("current_title"),
    )
    add(
        f"candidate:{candidate_id}:current_company",
        "Current company",
        candidate.get("current_company_name"),
    )
    add(
        f"candidate:{candidate_id}:provenance",
        "Evidence provenance",
        {
            "source_category": candidate.get("source_category"),
            "source_systems": candidate.get("source_systems") or [],
        },
    )

    document_id = candidate.get("document_id")
    if document_id:
        add(
            f"document:{document_id}",
            "Current CV document",
            {
                "title": candidate.get("document_title"),
                "resume_updated_at": candidate.get("resume_updated_at"),
            },
        )

    graph_evidence = candidate.get("graph_evidence") or {}
    profile_evidence = graph_evidence.get("profile_evidence") or {}
    for field_name in (
        "headline",
        "summary",
        "location",
        "skill_names",
        "recent_employment",
    ):
        add(
            f"candidate:{candidate_id}:profile:{field_name}",
            f"Profile {field_name.replace('_', ' ')}",
            profile_evidence.get(field_name),
        )

    entity_specs = (
        (
            "contacts",
            "contact",
            "contact_id",
            ("full_name", "role_title", "seniority", "is_hiring_manager"),
        ),
        (
            "interactions",
            "interaction",
            "interaction_id",
            ("interaction_type", "occurred_at", "subject", "summary"),
        ),
        ("jobs", "job", "job_id", ("title", "status", "location", "employment_type")),
        (
            "opportunities",
            "opportunity",
            "opportunity_id",
            ("title", "stage", "smart_summary", "last_contact_at"),
        ),
    )
    for collection_name, entity_name, id_field, safe_fields in entity_specs:
        for item in graph_evidence.get(collection_name) or []:
            entity_id = item.get(id_field)
            if not entity_id:
                continue
            add(
                f"{entity_name}:{entity_id}",
                f"Linked {entity_name}",
                {field: item.get(field) for field in safe_fields},
            )

    return catalog


def _validate_assessment_grounding(
    *,
    assessments: list[CandidateShortlistAssessment],
    retrieved_candidates: list[dict[str, Any]],
) -> None:
    catalogs_by_candidate = {
        str(candidate["candidate_id"]): _build_candidate_evidence_catalog(candidate)
        for candidate in retrieved_candidates
    }

    failures: list[dict[str, Any]] = []
    for assessment in assessments:
        catalog = catalogs_by_candidate.get(assessment.candidate_id)
        if catalog is None:
            failures.append(
                {
                    "candidate_id": assessment.candidate_id,
                    "finding_codes": ["unknown_candidate_id"],
                }
            )
            continue

        findings = validate_claim_evidence(
            claim_groups={
                "fit_summary": [assessment.fit_summary.model_dump()],
                "strengths": [claim.model_dump() for claim in assessment.strengths],
                "gaps": [claim.model_dump() for claim in assessment.gaps],
            },
            allowed_evidence_refs={str(item["evidence_ref"]) for item in catalog},
        )
        if findings:
            failures.append(
                {
                    "candidate_id": assessment.candidate_id,
                    "finding_codes": sorted({finding.code for finding in findings}),
                }
            )

    if failures:
        raise CandidateMatchingError(
            "Candidate shortlisting returned claims without retrievable evidence.",
            stage="grounding_validation",
            details=failures,
        )


def _json_safe_value(value: Any) -> Any:
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(key): _json_safe_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe_value(item) for item in value]
    return value


def _attach_graph_evidence_to_candidates(
    candidates: list[dict[str, Any]],
    *,
    per_candidate_limit: int = 3,
) -> list[dict[str, Any]]:
    """
    Enrich retrieved candidates with bounded graph-style evidence.

    This first slice is intentionally pragmatic rather than fully recursive:

    - candidate profile + linked skill names
    - current-company context
    - top contacts, interactions, jobs, and opportunities for that company
    """

    enriched_candidates: list[dict[str, Any]] = []
    bounded_limit = max(1, min(int(per_candidate_limit), 10))
    company_context_cache: dict[str, dict[str, Any]] = {}

    for candidate in candidates:
        candidate_copy = dict(candidate)
        candidate_copy["graph_evidence"] = _build_candidate_graph_evidence(
            candidate_copy,
            per_candidate_limit=bounded_limit,
            company_context_cache=company_context_cache,
        )
        enriched_candidates.append(candidate_copy)

    return enriched_candidates


def _score_candidates_with_graph_context(
    candidates: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """
    Apply a bounded graph-context score and reorder shortlist input candidates.

    This is intentionally conservative. Semantic/text retrieval remains the
    primary signal; graph context provides a small deterministic lift where the
    corpus already contains richer linked evidence.
    """

    scored_candidates: list[dict[str, Any]] = []

    for candidate in candidates:
        candidate_copy = dict(candidate)
        graph_context_score = _compute_graph_context_score(
            candidate_copy.get("graph_evidence")
        )
        retrieval_score = float(candidate_copy.get("match_score") or 0.0)
        ranking_input_score = round(
            (retrieval_score * 0.85) + (graph_context_score * 0.15),
            6,
        )
        candidate_copy["graph_context_score"] = graph_context_score
        candidate_copy["ranking_input_score"] = ranking_input_score
        scored_candidates.append(candidate_copy)

    return sorted(
        scored_candidates,
        key=lambda candidate: (
            float(candidate.get("ranking_input_score") or 0.0),
            float(candidate.get("match_score") or 0.0),
            float(candidate.get("graph_context_score") or 0.0),
        ),
        reverse=True,
    )


def _build_candidate_graph_evidence(
    candidate: dict[str, Any],
    *,
    per_candidate_limit: int = 3,
    company_context_cache: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """
    Build one bounded evidence bundle for a retrieved candidate.
    """

    candidate_id = str(candidate["candidate_id"])
    profile = build_candidate_profile(
        candidate_id,
        include_source_metadata=False,
    )
    if profile is None:
        return {
            "candidate_id": candidate_id,
            "current_company_name": candidate.get("current_company_name"),
            "skill_names": [],
            "evidence_kind": _candidate_evidence_kind(candidate),
            "has_resume_document": bool(candidate.get("document_id")),
            "profile_evidence": {},
            "recent_employment": [],
            "contacts_count": 0,
            "interactions_count": 0,
            "jobs_count": 0,
            "opportunities_count": 0,
            "contacts": [],
            "interactions": [],
            "jobs": [],
            "opportunities": [],
        }

    profile_candidate = profile["candidate"]
    skill_names = _extract_skill_names(profile.get("skills") or [])[
        :_PROFILE_SKILL_LIMIT
    ]
    recent_employment = list(profile.get("recent_employment") or [])[:5]
    current_company_name = (
        candidate.get("current_company_name")
        or profile_candidate.get("current_company_name")
        or ""
    ).strip()

    evidence = {
        "candidate_id": candidate_id,
        "current_company_name": current_company_name or None,
        "skill_names": skill_names,
        "evidence_kind": _candidate_evidence_kind(candidate),
        "has_resume_document": bool(candidate.get("document_id")),
        "recent_employment": recent_employment,
        "profile_evidence": {
            "current_title": _bounded_optional_text(
                candidate.get("current_title")
                or profile_candidate.get("current_title"),
                limit=_PROFILE_HEADLINE_CHARACTER_LIMIT,
            ),
            "headline": _bounded_optional_text(
                profile_candidate.get("headline"),
                limit=_PROFILE_HEADLINE_CHARACTER_LIMIT,
            ),
            "summary": _bounded_optional_text(
                profile_candidate.get("summary"),
                limit=_PROFILE_SUMMARY_CHARACTER_LIMIT,
            ),
            "location": _bounded_optional_text(
                profile_candidate.get("location"),
                limit=_PROFILE_HEADLINE_CHARACTER_LIMIT,
            ),
            "current_company_name": current_company_name or None,
            "skill_names": skill_names,
            "recent_employment": recent_employment,
        },
        "contacts_count": 0,
        "interactions_count": 0,
        "jobs_count": 0,
        "opportunities_count": 0,
        "contacts": [],
        "interactions": [],
        "jobs": [],
        "opportunities": [],
    }

    if current_company_name == "":
        return evidence

    cache_key = current_company_name.casefold()
    company_context = (
        company_context_cache.get(cache_key)
        if company_context_cache is not None
        else None
    )
    if company_context is None:
        company_context = discover_company_context(
            company_name=current_company_name,
            limit=per_candidate_limit,
            include_candidates=False,
            include_opportunities=True,
        )
        if company_context_cache is not None:
            company_context_cache[cache_key] = company_context

    contacts = list(company_context["contacts"])
    interactions = list(company_context["interactions"])
    jobs = list(company_context["jobs"])
    opportunities = list(company_context["opportunities"])

    evidence["contacts_count"] = len(contacts)
    evidence["interactions_count"] = len(interactions)
    evidence["jobs_count"] = len(jobs)
    evidence["opportunities_count"] = len(opportunities)
    evidence["contacts"] = contacts
    evidence["interactions"] = interactions
    evidence["jobs"] = jobs
    evidence["opportunities"] = opportunities
    return evidence


def _compute_graph_context_score(graph_evidence: dict[str, Any] | None) -> float:
    """
    Return a conservative 0..1 score from bounded linked evidence counts.
    """

    if not graph_evidence:
        return 0.0

    contacts_count = min(int(graph_evidence.get("contacts_count") or 0), 3)
    interactions_count = min(int(graph_evidence.get("interactions_count") or 0), 3)
    jobs_count = min(int(graph_evidence.get("jobs_count") or 0), 2)
    opportunities_count = min(
        int(graph_evidence.get("opportunities_count") or 0),
        2,
    )
    skill_names_count = min(len(graph_evidence.get("skill_names") or []), 4)

    raw_score = (
        (contacts_count * 0.15)
        + (interactions_count * 0.2)
        + (jobs_count * 0.15)
        + (opportunities_count * 0.15)
        + (skill_names_count * 0.05)
    )
    max_score = (3 * 0.15) + (3 * 0.2) + (2 * 0.15) + (2 * 0.15) + (4 * 0.05)
    return round(min(raw_score / max_score, 1.0), 6)


def _extract_skill_names(skills: list[dict[str, Any]]) -> list[str]:
    skill_names: list[str] = []
    seen_skill_names: set[str] = set()

    for skill in skills:
        skill_name = str(
            skill.get("canonical_name") or skill.get("skill_name") or ""
        ).strip()
        if skill_name == "":
            continue
        normalized_skill_name = skill_name.lower()
        if normalized_skill_name in seen_skill_names:
            continue
        seen_skill_names.add(normalized_skill_name)
        skill_names.append(skill_name)

    return skill_names


def _candidate_evidence_kind(candidate: dict[str, Any]) -> str:
    if candidate.get("document_id"):
        return "resume_and_structured_profile"
    return "structured_profile_only"


def _bounded_optional_text(value: Any, *, limit: int) -> str | None:
    normalized_value = " ".join(str(value or "").split())
    if normalized_value == "":
        return None
    if len(normalized_value) <= limit:
        return normalized_value
    return normalized_value[:limit].rstrip() + "..."


__all__ = [
    "CandidateEvidenceClaim",
    "CandidateMatchingError",
    "CandidateShortlistAssessment",
    "CandidateShortlistSelection",
    "build_candidate_job_description_shortlist",
    "retrieve_candidates_with_graph_context",
]
