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
- canonical merge/upsert becomes unsafe

These tests therefore lock down the extraction contract before a real provider
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

import json
from typing import Any

import pytest

import backend.services.resume_extraction as resume_extraction
from backend.llm.models import ModelProfile, ModelProvider, ModelPurpose
from backend.services.resume_extraction import (
    ResumeExtractionError,
    ResumeStructuredExtraction,
    _normalise_resume_structured_extraction,
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

        bundle["extracted_resume_text"] = None

    In plain language:

    - make one realistic upstream bundle
    - let individual tests mutate it as needed
    """

    # This fixture is intentionally broader than the minimum required by any
    # single test.
    #
    # That is deliberate. The production extraction service sits on top of a
    # fairly rich upstream bundle returned by
    # `extract_latest_jobadder_resume_text_for_candidate(...)`. Keeping this
    # fake bundle realistic makes the tests more trustworthy because they are
    # not accidentally proving behaviour against an unrealistically tiny input.
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
            "status": {
                "statusId": 11783,
                "name": "Active",
                "active": True,
                "default": True,
            },
            "skillTags": ["machine learning", "NLP", "Python"],
            "createdAt": "2025-07-10T16:01:10Z",
            "updatedAt": "2026-04-20T10:02:24Z",
        },
        # Keep both the raw note item and the cleaned note item because the
        # upstream ingest layer now exposes both:
        # - raw text for audit/debug
        # - cleaned text for prompt use
        #
        # The extraction service should consume the cleaned note path when it
        # prepares prompt input.
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
            "note_count": 1,
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
        # Keep both the raw extracted text and the cleaned text because the
        # extraction input builder is expected to prefer the cleaned value and
        # fall back to the raw value only if needed.
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

    Example
    -------
    A test can call:

        profile = _build_test_model_profile()

    and then pass that profile into the extraction service when it wants
    deterministic, explicit model metadata in the final returned payload.

    In plain language:

    - make one stable fake model profile
    - reuse it across tests
    """

    # Use a dedicated test profile rather than the module default so the tests
    # remain stable even if the production default model choice later changes.
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
    into a smaller prompt-ready extraction input.

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

    # Start with the routing/source identifiers first.
    #
    # These are the anchoring fields that help later layers understand which
    # source system and source record the prompt input came from.
    assert result["source_system"] == "jobadder"
    assert result["source_candidate_id"] == 16496678
    assert result["jobadder_account"] == 2236

    # The candidate context snapshot should be smaller than the full JobAdder
    # candidate payload. The point of this assertion is to prove that the input
    # builder selected the useful fields rather than blindly forwarding the
    # whole upstream object.
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

    # Resume context is also intentionally compact. The model needs enough
    # document metadata to reason about the source, but it does not need raw
    # transport clutter such as bytes or endpoint internals at this stage.
    assert result["latest_resume"] == {
        "attachment_id": 21091489,
        "file_name": "Roger Campbell - CV 2025.pdf",
        "mime_type": "application/pdf",
        "created_at": "2026-04-20T10:00:00Z",
        "page_count": 2,
        "character_count": 52,
        "extractor": "pypdf",
    }

    # The key behavioural assertion here is that the builder preferred the
    # cleaned resume text, not the noisier raw extracted text.
    assert result["cleaned_resume_text"] == (
        "Roger Campbell\nSenior Data Scientist\nPython\nSQL"
    )

    # Likewise, the prompt input should contain the cleaned note form rather
    # than the larger raw note payload.
    assert result["cleaned_candidate_notes"] == [
        {
            "note_id": "79d7b82f-3d11-4e2a-86bd-d68efdc09e0a",
            "type": "Email Reply",
            "created_at": "2026-04-06T08:51:06Z",
            "updated_at": "2026-04-06T08:51:06Z",
            "cleaned_text": "Hi Roger,\n\nThanks again for today.",
        }
    ]


def test_build_resume_extraction_input_from_jobadder_bundle_raises_when_resume_text_is_missing() -> None:
    """
    Verify that the input builder fails clearly when the prepared upstream bundle
    does not contain usable resume text.

    Notes
    -----
    - This is a contract failure, not a provider failure.
    - By this stage, the upstream resume-text pipeline is supposed to have
      already produced usable text.
    - If it has not, the extraction layer should stop immediately and say so.

    Example
    -------
    We simulate a broken upstream bundle by setting:

        bundle["extracted_resume_text"] = None

    The helper should then raise `ResumeExtractionError` at the
    `input_validation` stage.

    In plain language:

    - pretend the upstream bundle lost its extracted resume text
    - confirm the extraction layer rejects that input cleanly
    """

    bundle = _build_fake_resume_text_bundle()

    # Corrupt only the specific field this test cares about while keeping the
    # rest of the upstream bundle realistic.
    #
    # That makes the failure mode precise. If the helper raises here, it should
    # be because usable resume text is missing, not because the whole bundle was
    # turned into an unrealistic stub.
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

    Example
    -------
    Starting from a valid prompt-ready extraction input, the helper should
    return:

    - one `system_prompt`
    - one `user_prompt`

    where the user prompt contains real candidate-specific source material such
    as the candidate name and cleaned resume text.

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

    # At this layer we do not yet care about provider behaviour. We only care
    # that the prompt builder produced the two prompt parts that the later
    # LangChain chain expects.
    assert "system_prompt" in prompt_bundle
    assert "user_prompt" in prompt_bundle

    assert "careful recruitment data-extraction assistant" in prompt_bundle["system_prompt"]
    assert "Do not invent employers, titles, dates, qualifications, or contact details." in prompt_bundle["system_prompt"]
    assert "Source priority matters." in prompt_bundle["system_prompt"]
    assert "Do not add a skill, tool, platform, employer, project, or certification solely because it appears in recruiter notes" in prompt_bundle["system_prompt"]
    assert "`certifications` must be a list of plain strings only, not objects or nested records." in prompt_bundle["system_prompt"]
    assert "Remove display separators like `|`" in prompt_bundle["system_prompt"]
    assert "`ambiguity_notes` must be a list of short strings only, not one long paragraph and not nested objects." in prompt_bundle["system_prompt"]
    assert "Do not use university locations, old job locations, or remote/hybrid labels as a proxy for current location." in prompt_bundle["system_prompt"]
    assert 'Example: `MSc Data Science` should become `qualification = "MSc"` and `subject = "Data Science"`.' in prompt_bundle["system_prompt"]
    assert "Worked example for source priority and field boundaries:" in prompt_bundle["system_prompt"]
    assert "Worked example for location and education field shape:" in prompt_bundle["system_prompt"]
    assert "Worked example for preserving major projects under a role:" in prompt_bundle["system_prompt"]
    assert '"Production optimisation ML initiatives"' in prompt_bundle["system_prompt"]
    assert "If the source provides a clear project name, use that exact project name" in prompt_bundle["system_prompt"]
    assert '`responsibilities`: ["Led ML delivery across six major initiatives"]' in prompt_bundle["system_prompt"]
    assert '`deliverables`: ["Regression and time-series forecasting models", "Productionised ML deployment workflows"]' in prompt_bundle["system_prompt"]
    assert '`business_outcomes`: ["Delivered multi-million-dollar efficiency gains"]' in prompt_bundle["system_prompt"]
    assert "Include 1-3 concrete items in `responsibilities`, `deliverables`, or `business_outcomes`" in prompt_bundle["system_prompt"]
    assert "Worked example for exact project naming:" in prompt_bundle["system_prompt"]
    assert 'Use `name = "Leet-Cheat"` rather than `Leet-Cheat educational platform`' in prompt_bundle["system_prompt"]
    assert 'Do not include `Make.com` or `Supabase` in `skills` or `tools_and_platforms`' in prompt_bundle["system_prompt"]
    assert "`projects` should contain only clearly supported major projects or initiatives." in prompt_bundle["system_prompt"]
    assert "Do not copy broad resume-wide skill lists into every project." in prompt_bundle["system_prompt"]

    assert "Important source-handling reminder" in prompt_bundle["user_prompt"]
    assert "leave it out of the final structured fields entirely" in prompt_bundle["user_prompt"]
    assert "Keep schema shape simple: certifications are plain strings, and ambiguity notes are short strings." in prompt_bundle["user_prompt"]
    assert "Study locations, historic role locations, and remote/hybrid labels are not enough by themselves." in prompt_bundle["user_prompt"]
    assert '`qualification = "MSc"`, `subject = "Data Science"`.' in prompt_bundle["user_prompt"]
    assert "Make `evidence_notes` concrete and source-specific where possible" in prompt_bundle["user_prompt"]
    assert "Candidate context" in prompt_bundle["user_prompt"]
    assert "Cleaned candidate notes" in prompt_bundle["user_prompt"]
    assert "Cleaned resume text" in prompt_bundle["user_prompt"]
    assert "Roger Campbell" in prompt_bundle["user_prompt"]
    assert "Senior Data Scientist" in prompt_bundle["user_prompt"]


def test_extract_structured_candidate_profile_from_resume_bundle_returns_validated_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    Verify that the core extraction orchestrator returns one combined result
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
        # The real service builds a LangChain runnable and then calls:
        #
        #     extraction_chain.invoke({})
        #
        # So the fake object only needs to implement the same small surface:
        # an `invoke(...)` method that returns schema-shaped data.
        def invoke(self, payload: dict[str, Any]) -> dict[str, Any]:
            captured_invoke_payloads.append(payload)
            return {
                "current_employer": "Pirum",
                "current_title": "Senior Data Scientist",
                "professional_summary": (
                    "Senior applied machine learning candidate with Python and NLP experience."
                ),
                "location": "London",
                "emails": ["the_rfc@hotmail.co.uk"],
                "phones": ["07934 890 708"],
                "skills": ["Machine Learning", "NLP"],
                "tools_and_platforms": ["Python", "SQL", "LangChain"],
                "certifications": ["AWS Certified Cloud Practitioner"],
                "linkedin_url": None,
                "portfolio_references": ["MLOps & LLMOps"],
                "education": [
                    {
                        "institution": "University of Warwick",
                        "qualification": "MSc",
                        "subject": "Statistics",
                        "completion_date": "2018",
                    }
                ],
                "employment_history": [
                    {
                        "employer": "Pirum",
                        "title": "Senior Data Scientist",
                        "start_date": "2023",
                        "end_date": None,
                        "is_current": True,
                        "summary": "Built applied machine learning systems.",
                    }
                ],
                "projects": [
                    {
                        "name": "Market surveillance ML workflow",
                        "employer": "Pirum",
                        "role": "Senior Data Scientist",
                        "start_date": "2023",
                        "end_date": None,
                        "is_current": True,
                        "summary": "Built an applied machine learning workflow for trading operations.",
                        "responsibilities": ["Led delivery of the workflow."],
                        "deliverables": ["Market surveillance ML workflow."],
                        "business_outcomes": ["Improved operational decision support."],
                        "tools_and_platforms": ["Python", "SQL"],
                        "domains": ["Trading", "Machine Learning"],
                    }
                ],
                "evidence_notes": [
                    "Resume headline identifies the candidate as a Senior Data Scientist."
                ],
                "ambiguity_notes": [],
            }

    def fake_build_chain(
        *,
        chat_model: Any,
        system_prompt: str,
        user_prompt: str,
        use_native_structured_output: bool,
    ) -> FakeChain:
        # These assertions prove that the orchestration layer fed real prompt
        # content into the chain builder before any "model call" happened.
        assert chat_model == "fake-chat-model"
        assert "careful recruitment data-extraction assistant" in system_prompt
        assert "Roger Campbell" in user_prompt
        assert use_native_structured_output is True
        return FakeChain()

    # Replace the real chain builder with a fake success path so this test can
    # focus on the service's orchestration logic rather than real provider
    # behaviour.
    #
    # In other words, we want to prove:
    # - the service built the prompts
    # - the service invoked the chain
    # - the service validated the returned output
    #
    # without also depending on live model transport.
    monkeypatch.setattr(
        resume_extraction,
        "_build_langchain_resume_extraction_chain",
        fake_build_chain,
    )

    result = extract_structured_candidate_profile_from_resume_bundle(
        resume_text_bundle=bundle,
        chat_model="fake-chat-model",
        model_profile=model_profile,
    )

    # The extraction chain currently receives an empty runtime payload because
    # all of the real candidate-specific content has already been embedded into
    # the constructed prompts.
    #
    # This assertion is subtle but important. It proves the service is using the
    # chain in the expected "prompt already contains the data" style rather than
    # expecting additional input variables at invoke time.
    assert captured_invoke_payloads == [{}]

    assert result["source_system"] == "jobadder"
    assert result["source_candidate_id"] == 16496678
    assert result["jobadder_account"] == 2236

    # The returned model profile should be serialised plain data rather than a
    # dataclass instance. That keeps the result loggable, assertable, and later
    # route-friendly.
    assert result["model_profile"] == {
        "provider": ModelProvider.OPENAI,
        "model_name": "gpt-5.4-mini",
        "purpose": ModelPurpose.EXTRACTION,
        "temperature": 0.0,
        "max_output_tokens": 1600,
    }

    assert result["extraction_input"]["candidate_context"]["first_name"] == "Roger"
    assert result["structured_extraction"]["current_employer"] == "Pirum"
    assert result["structured_extraction"]["current_title"] == "Senior Data Scientist"
    assert result["structured_extraction"]["emails"] == ["the_rfc@hotmail.co.uk"]
    assert result["structured_extraction"]["skills"] == [
        "Machine Learning",
        "NLP",
    ]
    assert result["structured_extraction"]["tools_and_platforms"] == [
        "Python",
        "SQL",
        "LangChain",
    ]
    assert result["structured_extraction"]["certifications"] == [
        "AWS Certified Cloud Practitioner"
    ]
    assert result["structured_extraction"]["projects"] == [
        {
            "name": "Market surveillance ML workflow",
            "employer": "Pirum",
            "role": "Senior Data Scientist",
            "start_date": "2023",
            "end_date": None,
            "is_current": True,
            "summary": "Built an applied machine learning workflow for trading operations.",
            "responsibilities": ["Led delivery of the workflow."],
            "deliverables": ["Market surveillance ML workflow."],
            "business_outcomes": ["Improved operational decision support."],
            "tools_and_platforms": ["Python", "SQL"],
            "domains": ["Trading", "Machine Learning"],
        }
    ]


def test_extract_structured_candidate_profile_from_resume_bundle_raises_when_model_call_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    Verify that the core extraction orchestrator translates model-call failures
    into `ResumeExtractionError` with the correct stage label.

    Notes
    -----
    - This is the right behaviour because the rest of the backend should not
      need to care about the raw provider exception type.
    - It only needs to know that the extraction stage failed during model
      invocation.

    Example
    -------
    We replace the extraction chain with a fake object whose `invoke(...)`
    method raises:

        RuntimeError("Provider exploded")

    The service should translate that into `ResumeExtractionError` with:

    - `stage == "llm_invoke"`

    In plain language:

    - pretend the model call explodes
    - confirm the extraction service surfaces one clean local error
    """

    bundle = _build_fake_resume_text_bundle()
    model_profile = _build_test_model_profile()

    class FakeFailingChain:
        # Simulate a provider or transport failure after the chain has already
        # been built successfully.
        def invoke(self, payload: dict[str, Any]) -> dict[str, Any]:
            raise RuntimeError("Provider exploded")

    # Replace the real LangChain chain builder with a fake one so this test can
    # force a controlled failure exactly at model-invocation time.
    #
    # The production code would normally do this:
    # - build a real prompt
    # - build a real structured-output chain
    # - call `invoke(...)` on that chain
    #
    # But this test is not trying to verify LangChain wiring or provider
    # transport behaviour. It is only trying to verify the service's error
    # translation logic:
    #
    #     lower-level invoke failure
    #         -> ResumeExtractionError(stage="llm_invoke")
    #
    # So we patch the internal chain-builder function to always return our fake
    # failing chain, regardless of the prompt/model arguments it receives.
    monkeypatch.setattr(
        resume_extraction,
        "_build_langchain_resume_extraction_chain",
        lambda **kwargs: FakeFailingChain(),
    )

    # The extraction service should catch the fake chain's lower-level runtime
    # failure and re-raise it as the module's own orchestration error type.
    #
    # `pytest.raises(...)` both:
    # - asserts that the expected exception type was raised
    # - captures the exception object so the test can inspect its message,
    #   stage label, and structured details afterwards
    with pytest.raises(ResumeExtractionError) as exc_info:
        extract_structured_candidate_profile_from_resume_bundle(
            resume_text_bundle=bundle,
            chat_model="fake-chat-model",
            model_profile=model_profile,
        )

    error = exc_info.value

    assert str(error) == "The resume extraction model call failed."
    assert error.stage == "llm_invoke"
    assert error.details == [
        {"source_system": "jobadder"},
        {"source_candidate_id": 16496678},
        {"provider": ModelProvider.OPENAI},
        {"model_name": "gpt-5.4-mini"},
    ]


def test_extract_structured_candidate_profile_from_resume_bundle_retries_openrouter_with_json_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    Verify that the extraction orchestrator retries with the JSON-text fallback
    path when the OpenRouter/native-structured-output route rejects
    `json_schema`.

    Notes
    -----
    - This is the key compatibility test for cheaper OpenRouter-style models.
    - The first chain simulates a provider route that fails specifically
      because native `json_schema` output is unsupported.
    - The second chain simulates a plain chat response containing JSON text,
      which the service should parse and validate locally.
    """

    bundle = _build_fake_resume_text_bundle()
    model_profile = ModelProfile(
        provider=ModelProvider.OPENROUTER,
        model_name="nvidia/nemotron-3-nano-30b-a3b:nitro",
        purpose=ModelPurpose.EXTRACTION,
        temperature=0.0,
        max_output_tokens=1600,
    )
    build_modes: list[bool] = []

    class FakeNativeFailingChain:
        def invoke(self, payload: dict[str, Any]) -> dict[str, Any]:
            raise RuntimeError(
                "json_schema response format is not supported for model"
            )

    class FakeJsonFallbackChain:
        def invoke(self, payload: dict[str, Any]) -> Any:
            class FakeMessage:
                content = json.dumps(
                    {
                        "current_employer": "Pirum",
                        "current_title": "Senior Data Scientist",
                        "professional_summary": "Structured fallback path succeeded.",
                        "location": "London",
                        "emails": ["the_rfc@hotmail.co.uk"],
                        "phones": ["07934 890 708"],
                        "skills": ["Machine Learning"],
                        "tools_and_platforms": ["Python"],
                        "certifications": [],
                        "linkedin_url": None,
                        "portfolio_references": [],
                        "education": [],
                        "employment_history": [],
                        "projects": [],
                        "evidence_notes": ["Fallback JSON was parsed successfully."],
                        "ambiguity_notes": [],
                    }
                )

            return FakeMessage()

    def fake_build_chain(
        *,
        chat_model: Any,
        system_prompt: str,
        user_prompt: str,
        use_native_structured_output: bool,
    ) -> Any:
        build_modes.append(use_native_structured_output)
        if use_native_structured_output:
            return FakeNativeFailingChain()
        return FakeJsonFallbackChain()

    monkeypatch.setattr(
        resume_extraction,
        "_build_langchain_resume_extraction_chain",
        fake_build_chain,
    )

    result = extract_structured_candidate_profile_from_resume_bundle(
        resume_text_bundle=bundle,
        chat_model="fake-chat-model",
        model_profile=model_profile,
    )

    assert build_modes == [True, False]
    assert result["structured_extraction"]["current_employer"] == "Pirum"
    assert result["structured_extraction"]["tools_and_platforms"] == ["Python"]


def test_extract_structured_candidate_profile_from_resume_bundle_raises_when_output_schema_is_invalid(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    Verify that the core extraction orchestrator rejects model output that does
    not match the expected structured schema.

    Notes
    -----
    - This is one of the most important guardrails in the file.
    - A model may return something that "looks roughly right" to a human but is
      still not safe for downstream logic.
    - The extraction layer should therefore validate the output strictly before
      returning success.

    Example
    -------
    We simulate a model chain returning a value with the wrong type for
    `emails`.

    In plain language:

    - pretend the model returned malformed structured data
    - confirm the extraction service fails at schema validation
    """

    bundle = _build_fake_resume_text_bundle()

    class FakeInvalidChain:
        # This fake chain returns something that is close enough to look
        # believable at a glance, but still wrong at the contract level:
        # `emails` should be `list[str]`, not one string.
        #
        # That is exactly the kind of failure this test is trying to guard
        # against.
        def invoke(self, payload: dict[str, Any]) -> dict[str, Any]:
            return {
                "current_employer": "Pirum",
                "current_title": "Senior Data Scientist",
                "professional_summary": "Looks okay at first glance.",
                "location": "London",
                "emails": "the_rfc@hotmail.co.uk",
                "phones": ["07934 890 708"],
                "skills": ["Python"],
                "tools_and_platforms": [],
                "certifications": [],
                "linkedin_url": None,
                "portfolio_references": [],
                "education": [],
                "employment_history": [],
                "projects": [],
                "evidence_notes": [],
                "ambiguity_notes": [],
            }

    # Patch the chain builder again, but this time return a chain whose output
    # is "almost plausible" while still being schema-invalid.
    #
    # That distinction matters. We are not testing total nonsense here. We are
    # testing the more realistic failure mode where a model returns something a
    # human might casually accept, but which is still unsafe for downstream code
    # because it breaks the declared schema contract.
    monkeypatch.setattr(
        resume_extraction,
        "_build_langchain_resume_extraction_chain",
        lambda **kwargs: FakeInvalidChain(),
    )

    # The service should reject that malformed structured output and raise its
    # own local validation-stage error rather than silently returning bad data.
    with pytest.raises(ResumeExtractionError) as exc_info:
        extract_structured_candidate_profile_from_resume_bundle(
            resume_text_bundle=bundle,
            chat_model="fake-chat-model",
        )

    error = exc_info.value

    assert str(error) == (
        "The resume extraction model output did not match the expected schema."
    )
    assert error.stage == "llm_output_validation"
    assert error.details[0] == {"source_system": "jobadder"}
    assert error.details[1] == {"source_candidate_id": 16496678}
    # We do not pin the entire nested validation payload exactly because
    # Pydantic may vary some error formatting across versions. The important
    # thing is that validation errors were captured and surfaced.
    assert error.details[2]["validation_errors"]


def test_parse_json_object_from_model_text_accepts_fenced_json() -> None:
    """
    Verify that the JSON-text fallback parser accepts simple fenced JSON.

    Notes
    -----
    - Some models still wrap valid JSON in markdown fences even after being
      told not to.
    - The fallback parser should tolerate that narrow formatting error rather
      than failing unnecessarily.
    """

    parsed = resume_extraction._parse_json_object_from_model_text(
        '```json\n{"current_title": "Senior Data Scientist"}\n```'
    )

    assert parsed == {"current_title": "Senior Data Scientist"}


def test_extract_jobadder_candidate_resume_profile_fetches_upstream_bundle_and_delegates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    Verify that the top-level JobAdder convenience entrypoint does exactly the
    two things it is supposed to do:

    1. fetch the prepared JobAdder resume-text bundle
    2. delegate to the generic structured extraction helper

    Notes
    -----
    - This test keeps the public entrypoint honest.
    - The whole point of this helper is convenience, not duplicate business
      logic.
    - So we explicitly check that it delegates rather than rebuilding the same
      work itself.

    Example
    -------
    We replace:

    - the upstream JobAdder resume-text helper
    - the downstream generic extraction helper

    with small fake functions, then confirm the public JobAdder entrypoint:

    - fetched the upstream bundle once
    - passed that exact bundle into the generic extractor
    - forwarded the chat model and model profile unchanged

    In plain language:

    - fake the upstream JobAdder bundle helper
    - fake the downstream extraction helper
    - confirm the public entrypoint passes the right values through
    """

    fake_bundle = _build_fake_resume_text_bundle()
    model_profile = _build_test_model_profile()
    captured_calls: dict[str, Any] = {}

    def fake_extract_latest_jobadder_resume_text_for_candidate(
        *,
        jobadder_account: int,
        candidate_id: int,
    ) -> dict[str, Any]:
        # Record the public entrypoint's upstream call so we can confirm it
        # fetched the prepared resume-text bundle with the expected identifiers.
        captured_calls["jobadder_account"] = jobadder_account
        captured_calls["candidate_id"] = candidate_id
        return fake_bundle

    def fake_extract_structured_candidate_profile_from_resume_bundle(
        *,
        resume_text_bundle: dict[str, Any],
        chat_model: Any,
        model_profile: ModelProfile,
    ) -> dict[str, Any]:
        # Record the downstream delegation call so we can prove the public
        # entrypoint forwarded the exact upstream bundle rather than rebuilding
        # or mutating it.
        captured_calls["resume_text_bundle"] = resume_text_bundle
        captured_calls["chat_model"] = chat_model
        captured_calls["model_profile"] = model_profile
        return {
            "source_system": "jobadder",
            "source_candidate_id": 16496678,
            "structured_extraction": {
                "current_employer": "Pirum",
                "current_title": "Senior Data Scientist",
            },
        }

    # Patch the upstream JobAdder helper so the public convenience entrypoint
    # receives a known prepared bundle without hitting the real ingest flow.
    monkeypatch.setattr(
        resume_extraction,
        "extract_latest_jobadder_resume_text_for_candidate",
        fake_extract_latest_jobadder_resume_text_for_candidate,
    )

    # Patch the downstream generic extraction helper as well. This keeps the
    # test focused on delegation rather than extraction quality:
    # - fetch upstream bundle once
    # - pass that exact bundle through unchanged
    # - forward the chat model and model profile unchanged
    monkeypatch.setattr(
        resume_extraction,
        "extract_structured_candidate_profile_from_resume_bundle",
        fake_extract_structured_candidate_profile_from_resume_bundle,
    )

    result = extract_jobadder_candidate_resume_profile(
        jobadder_account=2236,
        candidate_id=16496678,
        chat_model="fake-chat-model",
        model_profile=model_profile,
    )

    # This one assertion is the heart of the test:
    # - fetch upstream bundle once
    # - pass that exact bundle into the generic extractor
    # - do not duplicate the extraction orchestration here
    assert captured_calls == {
        "jobadder_account": 2236,
        "candidate_id": 16496678,
        "resume_text_bundle": fake_bundle,
        "chat_model": "fake-chat-model",
        "model_profile": model_profile,
    }

    assert result == {
        "source_system": "jobadder",
        "source_candidate_id": 16496678,
        "structured_extraction": {
            "current_employer": "Pirum",
            "current_title": "Senior Data Scientist",
        },
    }


def test_resume_structured_extraction_schema_accepts_valid_nested_payload() -> None:
    """
    Verify that the main extraction schema accepts a valid nested payload with
    employment-history and education entries.

    Notes
    -----
    - This is a direct schema test rather than a service-orchestration test.
    - It is worth having because the schema is the contract the rest of the
      backend will trust.
    - If this contract changes accidentally later, this test should fail.

    Example
    -------
    We validate one nested payload containing:

    - top-level identity fields
    - one education entry
    - one employment-history entry

    and confirm the schema accepts it as a valid
    `ResumeStructuredExtraction`.

    In plain language:

    - feed the main schema one valid nested payload
    - confirm the schema accepts it and normalizes it correctly
    """

    payload = {
        "current_employer": "Pirum",
        "current_title": "Senior Data Scientist",
        "professional_summary": "Senior applied machine learning candidate.",
        "location": "London",
        "emails": ["the_rfc@hotmail.co.uk"],
        "phones": ["07934 890 708"],
        "skills": ["Python", "Machine Learning"],
        "tools_and_platforms": ["LangChain", "Azure ML"],
        "certifications": ["AWS Certified Cloud Practitioner"],
        "linkedin_url": None,
        "portfolio_references": ["MLOps & LLMOps"],
        "education": [
            {
                "institution": "University of Warwick",
                "qualification": "MSc",
                "subject": "Statistics",
                "completion_date": "2018",
            }
        ],
        "employment_history": [
            {
                "employer": "Pirum",
                "title": "Senior Data Scientist",
                "start_date": "2023",
                "end_date": None,
                "is_current": True,
                "summary": "Built applied machine learning systems.",
            }
        ],
        "projects": [
            {
                "name": "Market surveillance ML workflow",
                "employer": "Pirum",
                "role": "Senior Data Scientist",
                "start_date": "2023",
                "end_date": None,
                "is_current": True,
                "summary": "Built an applied machine learning workflow for trading operations.",
                "responsibilities": ["Led delivery of the workflow."],
                "deliverables": ["Market surveillance ML workflow."],
                "business_outcomes": ["Improved operational decision support."],
                "tools_and_platforms": ["Python", "SQL"],
                "domains": ["Trading", "Machine Learning"],
            }
        ],
        "evidence_notes": ["Resume headline supports current title."],
        "ambiguity_notes": [],
    }

    # This is the final contract test in the file.
    #
    # Everything else in the extraction service is ultimately working toward
    # this moment: can the output be accepted by the schema the rest of the
    # backend intends to trust?
    result = ResumeStructuredExtraction.model_validate(payload)

    assert result.current_employer == "Pirum"
    assert result.current_title == "Senior Data Scientist"
    assert result.education[0].institution == "University of Warwick"
    assert result.employment_history[0].employer == "Pirum"
    assert result.projects[0].name == "Market surveillance ML workflow"
    assert result.skills == ["Python", "Machine Learning"]
    assert result.tools_and_platforms == ["LangChain", "Azure ML"]
    assert result.certifications == ["AWS Certified Cloud Practitioner"]


def test_normalise_resume_structured_extraction_rehomes_tools_and_drops_soft_skills() -> None:
    """
    Verify that the post-validation cleanup keeps `skills` focused on core
    domains while moving obvious technologies into `tools_and_platforms`.

    Notes
    -----
    - This is intentionally a narrow deterministic cleanup test.
    - It does not try to "fix" the model broadly.
    - It only proves the local rule we want:
        - generic soft skills should not stay in `skills`
        - obvious technologies should live in `tools_and_platforms`
    """

    extraction = ResumeStructuredExtraction.model_validate(
        {
            "current_employer": "Pirum",
            "current_title": "Senior Data Scientist",
            "professional_summary": "Senior applied machine learning candidate.",
            "location": "London",
            "emails": ["the_rfc@hotmail.co.uk"],
            "phones": ["07934 890 708"],
            "skills": [
                "Machine Learning",
                "Python",
                "Leadership",
                "SQL",
                "Statistical Inference",
                "GitHub Actions",
            ],
            "tools_and_platforms": ["LangChain"],
            "certifications": [],
            "linkedin_url": None,
            "portfolio_references": [],
            "education": [],
            "employment_history": [],
            "projects": [],
            "evidence_notes": [],
            "ambiguity_notes": [],
        }
    )

    result = _normalise_resume_structured_extraction(extraction)

    assert result.skills == [
        "Machine Learning",
        "Statistical Inference",
    ]
    assert result.tools_and_platforms == [
        "LangChain",
        "Python",
        "SQL",
        "GitHub Actions",
    ]
