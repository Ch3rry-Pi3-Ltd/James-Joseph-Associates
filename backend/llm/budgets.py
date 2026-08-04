"""Versioned operating-budget inventory for every active model workflow."""

from __future__ import annotations

from dataclasses import dataclass


GPT_4_1_MINI_CONTEXT_TOKENS = 1_047_576
GPT_4_1_MINI_MAX_OUTPUT_TOKENS = 32_768
GPT_4_1_MINI_INPUT_USD_PER_MILLION = 0.40
GPT_4_1_MINI_CACHED_INPUT_USD_PER_MILLION = 0.10
GPT_4_1_MINI_OUTPUT_USD_PER_MILLION = 1.60
TEXT_EMBEDDING_3_LARGE_INPUT_USD_PER_MILLION = 0.13


@dataclass(frozen=True, slots=True)
class ModelWorkflowBudget:
    workflow: str
    model: str
    provider_context_tokens: int | None
    local_input_budget: str
    max_output_tokens: int | None
    timeout_seconds: float | None
    truncation_policy: str
    cost_alert_usd: float
    known_gap: str | None = None


MODEL_WORKFLOW_BUDGETS = (
    ModelWorkflowBudget(
        workflow="candidate_shortlist_reranking",
        model="gpt-4.1-mini",
        provider_context_tokens=GPT_4_1_MINI_CONTEXT_TOKENS,
        local_input_budget=(
            "50,000-character role brief; 100-candidate hard retrieval ceiling "
            "(25 default)"
        ),
        max_output_tokens=1_200,
        timeout_seconds=60.0,
        truncation_policy=(
            "Reject an oversized role brief; bound profile summaries, headlines, "
            "skills and candidate count before prompt assembly."
        ),
        cost_alert_usd=0.03,
        known_gap="No final token count is enforced on the assembled candidate payload.",
    ),
    ModelWorkflowBudget(
        workflow="recruiter_qa_synthesis",
        model="gpt-4.1-mini",
        provider_context_tokens=GPT_4_1_MINI_CONTEXT_TOKENS,
        local_input_budget=(
            "50,000-character question; 25-candidate pool, five-item company "
            "context and four memory turns by default"
        ),
        max_output_tokens=1_200,
        timeout_seconds=60.0,
        truncation_policy=(
            "Reject an oversized question; bound retrieval collections and session memory."
        ),
        cost_alert_usd=0.03,
        known_gap="No final token count is enforced on the assembled evidence payload.",
    ),
    *(
        ModelWorkflowBudget(
            workflow=f"resume_extraction_{source}",
            model="gpt-4.1-mini",
            provider_context_tokens=GPT_4_1_MINI_CONTEXT_TOKENS,
            local_input_budget=(
                "18,000-character CV first-pass ceiling plus cleaned source notes"
            ),
            max_output_tokens=4_000,
            timeout_seconds=60.0,
            truncation_policy=(
                "Truncate CV text for the first pass; preserve notes by current policy; "
                "retry length failures with a 4,000-token output ceiling."
            ),
            cost_alert_usd=0.02,
            known_gap="Source notes have no total character ceiling by explicit policy.",
        )
        for source in ("jobadder", "dropbox", "outlook", "recruiterflow")
    ),
    ModelWorkflowBudget(
        workflow="candidate_query_embedding",
        model="text-embedding-3-large",
        provider_context_tokens=None,
        local_input_budget="One validated search query per request.",
        max_output_tokens=None,
        timeout_seconds=None,
        truncation_policy="Reject blank input; upstream route/schema ceilings apply.",
        cost_alert_usd=0.005,
        known_gap="The embedding client does not yet set an explicit request timeout.",
    ),
    ModelWorkflowBudget(
        workflow="document_chunk_embedding_batch",
        model="text-embedding-3-large",
        provider_context_tokens=None,
        local_input_budget=(
            "25 chunks per default batch; document chunks are 1,200 characters "
            "with 150-character overlap"
        ),
        max_output_tokens=None,
        timeout_seconds=None,
        truncation_policy="Split documents deterministically before batching embeddings.",
        cost_alert_usd=0.005,
        known_gap="The embedding client does not yet set an explicit request timeout.",
    ),
    ModelWorkflowBudget(
        workflow="candidate_semantic_block_embedding_batch",
        model="text-embedding-3-large",
        provider_context_tokens=None,
        local_input_budget="25 structured candidate blocks per default provider batch.",
        max_output_tokens=None,
        timeout_seconds=None,
        truncation_policy=(
            "Build bounded profile, skills, and experience blocks before batching."
        ),
        cost_alert_usd=0.005,
        known_gap="The embedding client does not yet set an explicit request timeout.",
    ),
)


def get_model_workflow_budget(workflow: str) -> ModelWorkflowBudget:
    """Return one named budget or raise a clear error for an unregistered workflow."""

    for budget in MODEL_WORKFLOW_BUDGETS:
        if budget.workflow == workflow:
            return budget
    raise KeyError(f"Unknown model workflow budget: {workflow}")


__all__ = [
    "GPT_4_1_MINI_CONTEXT_TOKENS",
    "GPT_4_1_MINI_MAX_OUTPUT_TOKENS",
    "MODEL_WORKFLOW_BUDGETS",
    "ModelWorkflowBudget",
    "get_model_workflow_budget",
]
