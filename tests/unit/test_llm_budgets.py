"""Contract checks for the active model-workflow budget registry."""

from backend.llm.budgets import (
    GPT_4_1_MINI_MAX_OUTPUT_TOKENS,
    MODEL_WORKFLOW_BUDGETS,
    get_model_workflow_budget,
)


def test_every_active_model_workflow_has_one_unique_budget() -> None:
    expected = {
        "candidate_shortlist_reranking",
        "recruiter_qa_synthesis",
        "resume_extraction_jobadder",
        "resume_extraction_dropbox",
        "resume_extraction_outlook",
        "resume_extraction_recruiterflow",
        "candidate_query_embedding",
        "document_chunk_embedding_batch",
    }
    names = [budget.workflow for budget in MODEL_WORKFLOW_BUDGETS]

    assert set(names) == expected
    assert len(names) == len(set(names))


def test_chat_output_budgets_stay_inside_provider_limit() -> None:
    for budget in MODEL_WORKFLOW_BUDGETS:
        if budget.max_output_tokens is not None:
            assert 0 < budget.max_output_tokens <= GPT_4_1_MINI_MAX_OUTPUT_TOKENS
        assert budget.cost_alert_usd > 0


def test_budget_lookup_fails_for_unregistered_workflow() -> None:
    assert get_model_workflow_budget("candidate_shortlist_reranking").model == (
        "gpt-4.1-mini"
    )

    try:
        get_model_workflow_budget("unregistered")
    except KeyError as exc:
        assert "unregistered" in str(exc)
    else:
        raise AssertionError("Expected an unregistered workflow to fail closed.")
