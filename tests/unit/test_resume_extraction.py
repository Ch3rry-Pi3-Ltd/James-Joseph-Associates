"""
Unit tests for resume-extraction helpers.

This module tests the first LLM-facing extraction layer in
`backend.services.resume_extraction`.

Why these tests matter
----------------------
By this point in the pipeline, the backend can already prepare:

- structured JobAdder candidate metadata
- cleaned JobAdder note text
- cleaned resume text

This module tests the next question:

    "Can the backend turn that prepared material into one validated,
    structured extraction result?"

That matters because this is the first place where the backend starts depending
on an LLM-shaped boundary.

If this layer is loose or brittle, the downstream effects are serious:

- prompt inputs become inconsistent
- model calls become harder to debug
- invalid outputs can leak into later enrichment logic
- canonical merge/upset becomes unsafe

These tests threrefore lock down the extraction contract before a real provider
call is wired through it.

Scope of these tests
--------------------
These tests intentionally do not:

- call the real OpenAI API
- call any real LangChain provider endpoint
- hit JobAdder live
- write to the database

Instead, they isolate the local orchestration behaviour by replacing:

- the upstream JobAdder resume-text bundle helper
- the LangChain extraction chain builder

with small fake functions and objects.

Example
-------
A typical test in this module proves that a prepared bundle such as:

    {
        "candidate": {...},
        "notes": {...},
        "extracted_resume_text": {...},
        ...
    }

is reduced into a bounded prompt-ready input and then turned into one validated
structured extraction object.

In plain language:

- prepare a realistic fake upstream bundle
- pass it into the extraction layer
- confirm the output shape is trustworthy
"""

from typing import Any

import pytest

import backend.services.resume_extraction as resume_extraction
from backend.llm.models import ModelProfile, ModelProvider, ModelPurpose
from backend.services.resume_extraction import (
    ResumeExtractionError,
    ResumeStructuredExtraction,
    build_resume_extraction_input_from_jobadder_bundle,
    build_resume_extraction_prompt,
    extract_jobadder_candidate_resume_profile,
    extract_structured_candidate_profile_from_resume_bundle,
)

def _build_fake_resume_text_bundle() -> dict[str, Any]:
    """
    Return a realistic prepared JobAdder resume-text bundle for reuse across
    tests.

    Notes
    -----
    - This helper deliberately mirrors the shape returned by
      `extract_latest_jobadder_resume_text_for_candidate(...)`.
    - Keeping one shared bundle factory makes the tests easier to read because
      each test can focus on the specific field it cares about instead of
      rebuilding the entire structure from scratch.

    Example
    -------
    A test can start from:

        bundle = _build_fake_resume_text_bundle()

    and then adjust only the one part relevant to that scenario, for example:

        bundle["extract_resume_text"] = None

    In plain language:

    - make one realistic upstream bundle
    - let individual tests mutate it as needed
    """

    return {
        "source_system": "jobadder",
        "jobadder_account": 2236,
        "jobadder_instance": "eu2",
        "api_url": "https://eu2api.jobadder.com/v2/",
        "source_candidate_id": 16496678,
        "candidate": {
            "candidateId": 16496678,
            "firstName": "Roger",
            "lastName": "Campbell",
            "email": "the_rfc@hotmail.co.uk",
            "mobile": "07934 890 708",
            "location": "London",
            "status": "Active",
            "skillTags": ["machine learning", "NLP", "Python"],
            "createdAt": "2025-07-10T16:01:10Z",
            "updatedAt": "2026-04-20T10:02:24Z",
        },
        "notes": {
            "items": [
                {
                    "noteId": "79d7b82f-3d11-4e2a-86bd-d68efdc09e0a",
                    "type": "Email Reply",
                    "text": "Hi Roger, raw note text",
                    "createdAt": "2026-04-06T08:51:06Z",
                    "updatedAt": "2026-04-06T08:51:06Z",
                }
            ],
            "cleaned_items": [
                {
                    "note_id": "79d7b82f-3d11-4e2a-86bd-d68efdc09e0a",
                    "type": "Email Reply",
                    "created_at": "2026-04-06T08:51:06Z",
                    "updated_at": "2026-04-06T08:51:06Z",
                    "text": "Hi Roger, raw note text",
                    "cleaned_text": "Hi Roger,\n\nThanks again for today.",
                }
            ],
            "node_count": 1,
            "total_count": 1,
            "links": {},
        },
        "latest_resume": {
            "attachmentId": 21091489,
            "type": "Resume",
            "category": "Resume",
            "fileName": "Roger Campbell - CV 2025.pdf",
            "fileType": "application/pdf",
            "createdAt": "2026-04-20T10:00:00Z",
        },
        "resume_source": {
            "provider": "jobadder_attachment",
            "external_id": 21091489,
        },
        "downloaded_resume": {
            "file_name": "Roger Campbell - CV 2025.pdf",
            "content_type": "application/pdf",
            "content_length": 123456,
            "endpoint_url": "https://eu2api.jobadder.com/v2/candidates/16496678/attachments/21091489",
        },
        "extracted_resume_text": {
            "text": "Roger CampbellÃ‚\nSenior Data Scientist\nPython\nSQL",
            "cleaned_text": "Roger Campbell\nSenior Data Scientist\nPython\nSQL",
            "page_count": 2,
            "extractor": "pypdf",
            "file_name": "Roger Campbell - CV 2025.pdf",
            "character_count": 52,
        },
        "ingest_shell": {
            "source_system": "jobadder",
            "source_candidate_id": 16496678,
            "candidate_notes": [
                {
                    "note_id": "79d7b82f-3d11-4e2a-86bd-d68efdc09e0a",
                    "type": "Email Reply",
                    "created_at": "2026-04-06T08:51:06Z",
                    "updated_at": "2026-04-06T08:51:06Z",
                    "text": "Hi Roger, raw note text",
                    "cleaned_text": "Hi Roger,\n\nThanks again for today.",
                }
            ],
        },
    }

def _build_test_model_profile() -> ModelProfile:
    """
    Return a deterministic extraction model profile for tests.

    Notes
    -----
    - Using an explicit test profile keeps assertions stable.
    - It also avoids accidental coupling to future changes in the default model
      profile if the production model choice later changes.
    """

    return ModelProfile(
        provider=ModelProvider.OPENAI,
        model_name="gpt-5.4-mini",
        purpose=ModelPurpose.EXTRACTION,
        temperature=0.0,
        max_output_tokens=1600,
    )

def test_build_resume_extraction_input_from_jobadder_bundle_returns_bounded_prompt_input() -> None:
    """
    Verify that the input builder converts the larger upstream resume bundle
    into smaller prompt-ready extraction input.

    Notes
    -----
    - This is one of the most important local behaviours in the file.
    - The extraction layer should not dump the entire upstream bundle straight
      into the prompt.
    - Instead, it should:
        - keep the useful candidate context
        - keep useful resume metadata
        - prefer cleaned resume text
        - include cleaned candidate notes
        - keep the result bounded and readable

    Example
    -------
    Starting from a realistic prepared JobAdder bundle, the helper should return
    a dictionary with keys such as:

    - `candidate_context`
    - `latest_resume`
    - `cleaned_resume_text`
    - `cleaned_candidate_notes`

    In plain language:

    - take the big upstream bundle
    - reduce it to the prompt material that actually matters
    """

    bundle = _build_fake_resume_text_bundle()

    result = build_resume_extraction_input_from_jobadder_bundle(
        resume_text_bundle=bundle,
        max_resume_characters=500,
        max_note_count=3,
        max_note_characters=500,
    )

    assert result["source_system"] == "jobadder"
    assert result["source_candidate_id"] == 16496678
    assert result["jobadder_account"] == 2236

    assert result["candidate_context"] == {
        "candidate_id": 16496678,
        "first_name": "Roger",
        "last_name": "Campbell",
        "email": "the_rfc@hotmail.co.uk",
        "mobile": "07934 890 708",
        "location": "London",
        "status": "Active",
        "skill_tags": ["machine learning", "NLP", "Python"],
        "created_at": "2025-07-10T16:01:10Z",
        "updated_at": "2026-04-20T10:02:24Z",
    }

    assert result["latest_resume"] == {
        "attachment_id": 21091489,
        "file_name": "Roger Campbell - CV 2025.pdf",
        "mime_type": "application/pdf",
        "created_at": "2026-04-20T10:00:00Z",
        "page_count": 2,
        "character_count": 52,
        "extractor": "pypdf",
    }

    assert result["cleaned_resume_text"] == (
        "Roger Campbell\nSenior Data Scientist\nPython\nSQL"
    )

    assert result["cleaned_candidate_notes"] == [
        {
            "note_id": "79d7b82f-3d11-4e2a-86bd-d68efdc09e0a",
            "type": "Email Reply",
            "created_at": "2026-04-06T08:51:06Z",
            "updated_at": "2026-04-06T08:51:06Z",
            "cleaned_text": "Hi Roger,\n\nThanks again for today.",
        }
    ]

def test_build_resume_extraction_input_from_jobadder_bundle_raises_when_text_is_missing() -> None:
    """
    Verify that the input builder fails clearly when the prepared upstream bundle
    does not contain usable resume text.

    Notes
    -----
    - This is a contract failure, not a provider failure.
    - By this stage, the upstream resume-text pipeline is suppose to have
      already produced usable text.
    - If it has not, the extraction layer should stop immediately and say so.

    In plain language:

    - pretend the upstream bundle lost its extracted resume text
    - confirm the extraction layer rejects that input cleanly
    """

    bundle = _build_fake_resume_text_bundle()
    bundle["extracted_resume_text"] = None

    with pytest.raises(ResumeExtractionError) as exc_info:
        build_resume_extraction_input_from_jobadder_bundle(
            resume_text_bundle=bundle,
        )

    error = exc_info.value

    assert str(error) == "The prepared resume bundle is missing extracted resume text."
    assert error.stage == "input_validation"
    assert error.details == [{"candidate_id": 16496678}]

def test_build_resume_extraction_prompt_returns_system_and_user_prompt() -> None:
    """
    Verify that the prompt builder returns both prompt layers needed for the
    structured extraction call.

    Notes
    -----
    - The system prompt should contain the extraction rules.
    - The user prompt should contain the actual candidate-specific source
      material.
    - This split is important because LangChain chat prompts distinguish
      instruction context from task input.

    In plain language:

    - build the prompt-ready input first
    - confirm the prompt builder turns it into both required prompt strings
    """

    bundle = _build_fake_resume_text_bundle()
    extraction_input = build_resume_extraction_input_from_jobadder_bundle(
        resume_text_bundle=bundle,
    )

    prompt_bundle = build_resume_extraction_prompt(
        extraction_input=extraction_input,
    )

    assert "system_prompt" in prompt_bundle
    assert "user_prompt" in prompt_bundle

    assert "careful recruitment data-extraction assistant" in prompt_bundle["system_prompt"]
    assert "Do not invent employers, titles, dates, qualifications, or contact details." in prompt_bundle["system_prompt"]


    assert "Candidate context" in prompt_bundle["user_prompt"]
    assert "Cleaned candidate notes" in prompt_bundle["user_prompt"]
    assert "Cleaned resume text" in prompt_bundle["user_prompt"]
    assert "Roger Campbell" in prompt_bundle["user_prompt"]
    assert "Senior Data Scientist" in prompt_bundle["user_prompt"]

def test_extract_structured_candidate_profile_from_resume_bundle_returns_validated_result(
    monkeypath: pytest.MonkeyPatch,
) -> None:
    """
    Verify that the core extraction orchestator returns one combined result
    when the model chain succeeds.

    Notes
    -----
    - This test replaces the LangChain extraction chain with a fake object.
    - That keeps the test focused on this module's orchestration logic rather
      than on provider behaviour.
    - The important thing here is not just "did it call something?" but:
        - did it build the extraction input?
        - did it build the prompts?
        - did it invoke the chain?
        - did it validate and return the output in the expected final shape?

    Example
    -------
    We simulate a successful model chain returning a dictionary that matches the
    `ResumeStructuredExtraction` schema.

    In plain language:

    - fake the model call
    - confirm the extraction service returns one trustworthy combined result
    """

    bundle = _build_fake_resume_text_bundle()
    model_profile = _build_test_model_profile()
    captured_invoke_payloads: list[dict[str, Any]] = []

    class FakeChain:
        def invoke(self, payload: dict[str, Any]) -> dict[str, Any]:
            captured_invoke_payloads.append(payload)
            return {
                
            }