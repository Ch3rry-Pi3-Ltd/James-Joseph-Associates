"""
Resume extraction helpers.

This module is the first real LLM-backed extraction layer in the candidate
ingestion pipeline.

Why this module exists
----------------------
By this point in the backend, the upstream ingestion flow can already:

- connect to JobAdder
- refresh tokens when needed
- fetch candidate detail
- fetch candidate attachments
- fetch candidate notes
- identify the latest likely resume
- download the selected resume bytes
- extract plain text from the resume PDF
- clean the extracted resume text
- clean the JobAdder notes text

The next problem is different:

    "Can we take that prepared source material and turn it into one validated,
    structured candidate-enrichment output?"

That is what this module is for.

Why LangChain is reasonable here
--------------------------------
At this stage, LangChain starts to earn its keep because we now have a genuine
LLM boundary with a few real concerns:

- prompt construction
- structured output enforcement
- provider-backed invocation
- clearer separation between:
    - input shaping
    - prompt logic
    - model invocation
    - output validation

That said, this module still stays disciplined.

It does not:

- own the entire end-to-end workflow graph
- write canonical candidate records
- manage retries across every ingestion stage
- implement the final provider-routing strategy for the whole backend

This file is specifically about one thing:

    "Given a prepared resume-text bundle, can we ask a model for one reliable,
    structured candidate extraction?"

Scope of this first LangChain version
-------------------------------------
This module does:

- validate the prepared resume-text bundle
- build one prompt-ready extraction input
- create a LangChain prompt
- invoke a chat model with structured output
- validate the returned structure
- return a combined extraction result

It does not:

- create OpenAI credentials by itself
- decide final environment-variable naming
- choose the global provider strategy for the whole backend
- store results in the database
- compare candidates to jobs
- draft recruiter emails

That boundary is deliberate.

Example
-------
A later route, background task, or workflow step can call:

    result = extract_jobadder_candidate_resume_profile(
        jobadder_account=2236,
        candidate_id=16496678,
        chat_model=build_default_openai_resume_extraction_chat_model(),
    )

and receive a structure containing:

- the prompt-ready extraction input
- the model profile used
- the validated structured extraction output

For example, a later caller might inspect:

    result["structured_extraction"]["current_title"]
    result["structured_extraction"]["skills"]
    result["structured_extraction"]["employment_history"]

In plain language:

- take the prepared JobAdder + CV bundle
- build a careful extraction prompt
- ask the model for structured output
- validate that output before the rest of the backend trusts it

Interaction Map
---------------
The main interaction chain in this module is:

1. `extract_jobadder_candidate_resume_profile(...)`
   Top-level JobAdder convenience entrypoint. It fetches the prepared
   candidate + resume-text bundle, then passes that bundle into the
   structured extraction layer.

2. `extract_latest_jobadder_resume_text_for_candidate(...)`
   Upstream helper from `jobadder_ingest.py`. It returns candidate data,
   notes, resume metadata, extracted resume text, and cleaned resume text.

3. `extract_structured_candidate_profile_from_resume_bundle(...)`
   Core extraction orchestrator in this file. It builds the prompt-ready
   input, builds the prompts, invokes the model, validates the output, and
   returns the final structured result.

4. `build_resume_extraction_input_from_jobadder_bundle(...)`
   Reduces the larger upstream bundle into the smaller, bounded extraction
   input that the model actually needs.

5. `build_resume_extraction_prompt(...)`
   Builds the system prompt and user prompt from the prepared extraction
   input.

6. `_build_langchain_resume_extraction_chain(...)`
   Combines the LangChain prompt and the structured-output model into one
   runnable extraction chain.

7. model invocation
   Executes the chain and asks the model for one structured extraction
   object.

8. validation against `ResumeStructuredExtraction`
   Confirms the returned output matches the schema expected by the rest of
   the backend.

9. final structured result returned
   Returns one stable extraction payload containing metadata, prompt inputs,
   and validated structured output.

In plain language:

- get the prepared JobAdder + CV bundle
- reduce it to the important prompt-ready pieces
- build the extraction prompts
- call the structured model
- validate the output
- return something the rest of the backend can rely on
"""

from dataclasses import asdict
import json
from typing import Any

from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field, ValidationError

from backend.llm.models import ModelProfile, ModelProvider, ModelPurpose
from backend.services.jobadder_ingest import (
    extract_latest_jobadder_resume_text_for_candidate,
)

# Default model description for structured resume extraction.
#
# This remains a local typed description rather than a provider-specific config
# object. That keeps the rest of the backend able to talk about:
# - provider
# - model name
# - purpose
# - generation controls
#
# without forcing every downstream caller to know LangChain details.
DEFAULT_RESUME_EXTRACTION_MODEL_PROFILE = ModelProfile(
    provider=ModelProvider.OPENAI,
    model_name="gpt-5.4",
    purpose=ModelPurpose.EXTRACTION,
    temperature=0.0,
    max_output_tokens=2200,
)


class EmploymentHistoryItem(BaseModel):
    """
    One extracted employment-history item.

    Attributes
    ----------
    employer : str | None
        Employer name as supported by the source material.

    title : str | None
        Role title for this employment entry.

    start_date : str | None
        Human-readable start date as seen or inferred from the source material.

    end_date : str | None
        Human-readable end date as seen or inferred from the source material.

    is_current : bool | None
        Whether this role appears to be the current role.

    summary : str | None
        Short factual summary of responsibilities or context.

    Notes
    -----
    - Dates intentionally remain strings in this first version.
    - CV dates are often partial, vague, or inconsistently formatted.
    - Canonical date normalization should happen later, not inside the LLM
      extraction contract.

    Example
    -------
    A structured role entry might look like:

        EmploymentHistoryItem(
            employer="Pirum",
            title="Senior Data Scientist",
            start_date="2023",
            end_date=None,
            is_current=True,
            summary="Built applied machine learning systems for trading workflows.",
        )

    In plain language:

    - one job
    - one employer
    - one title
    - loose date strings for now
    """

    employer: str | None = Field(default=None)
    title: str | None = Field(default=None)
    start_date: str | None = Field(default=None)
    end_date: str | None = Field(default=None)
    is_current: bool | None = Field(default=None)
    summary: str | None = Field(default=None)


class EducationHistoryItem(BaseModel):
    """
    One extracted education-history item.

    Attributes
    ----------
    institution : str | None
        School, university, or training provider name.

    qualification : str | None
        Degree, diploma, certificate, or other qualification label.

    subject : str | None
        Subject or area of study.

    completion_date : str | None
        Human-readable completion date string.

    Notes
    -----
    - This remains an extraction-stage schema, not the final canonical storage
      model.

    Example
    -------
    A structured education entry might look like:

        EducationHistoryItem(
            institution="University of Warwick",
            qualification="MSc",
            subject="Statistics",
            completion_date="2018",
        )

    In plain language:

    - one education item
    - one institution
    - one qualification
    - one loose completion-date string
    """

    institution: str | None = Field(default=None)
    qualification: str | None = Field(default=None)
    subject: str | None = Field(default=None)
    completion_date: str | None = Field(default=None)


class ResumeStructuredExtraction(BaseModel):
    """
    Structured extraction output expected from the LLM.

    Attributes
    ----------
    current_employer : str | None
        Best current-employer value supported by the resume and notes.

    current_title : str | None
        Best current-title value supported by the resume and notes.

    professional_summary : str | None
        Short factual profile summary.

    location : str | None
        Candidate location when visible.

    emails : list[str]
        Email addresses found in the source material.

    phones : list[str]
        Phone numbers found in the source material.

    skills : list[str]
        Important technical, domain, or tooling skills.

    education : list[EducationHistoryItem]
        Extracted education history.

    employment_history : list[EmploymentHistoryItem]
        Extracted employment history.

    evidence_notes : list[str]
        Brief factual notes about source evidence that supports the extraction.

    ambiguity_notes : list[str]
        Brief factual notes describing uncertainty, contradiction, or missing
        context.

    Notes
    -----
    - This is intentionally narrower than a full canonical candidate model.
    - The immediate goal is a reliable extraction contract.

    Example
    -------
    A successful extraction object might look like:

        ResumeStructuredExtraction(
            current_employer="Pirum",
            current_title="Senior Data Scientist",
            professional_summary="Senior applied machine learning candidate with Python, NLP, and data-platform experience.",
            location="London",
            emails=["the_rfc@hotmail.co.uk"],
            phones=["07934 890 708"],
            skills=["Python", "Machine Learning", "NLP", "SQL"],
            education=[],
            employment_history=[],
            evidence_notes=[
                "Resume headline identifies the candidate as a Senior Data Scientist.",
                "Contact block contains one email address and one mobile number.",
            ],
            ambiguity_notes=[
                "Current employer was inferred from the most recent employment entry rather than stated explicitly.",
            ],
        )

    In plain language:

    - this is the shape the rest of the backend should trust
    - the model can be flexible internally
    - the output contract should not be flexible
    """

    current_employer: str | None = Field(default=None)
    current_title: str | None = Field(default=None)
    professional_summary: str | None = Field(default=None)
    location: str | None = Field(default=None)
    emails: list[str] = Field(default_factory=list)
    phones: list[str] = Field(default_factory=list)
    skills: list[str] = Field(default_factory=list)
    education: list[EducationHistoryItem] = Field(default_factory=list)
    employment_history: list[EmploymentHistoryItem] = Field(default_factory=list)
    evidence_notes: list[str] = Field(default_factory=list)
    ambiguity_notes: list[str] = Field(default_factory=list)


class ResumeExtractionError(RuntimeError):
    """
    Raised when the backend cannot build or validate a structured resume
    extraction.

    Attributes
    ----------
    message : str
        Safe human-readable explanation of what failed.

    stage : str
        Small machine-readable label describing the failed stage.

        Common values include:

        - `input_validation`
        - `prompt_build`
        - `llm_invoke`
        - `llm_output_validation`

    details : list[dict[str, Any]]
        Small structured metadata that helps explain the failure without
        carrying full CV text or large prompt payloads.

    Notes
    -----
    - This exception is for backend control flow.
    - It deliberately avoids storing the full source text on the object.

    Example
    -------
    A caller can inspect:

        error.stage
        error.details

    to distinguish between:

    - a broken prompt input
    - a failed model invocation
    - a schema mismatch in the model output

    In plain language:

    - one exception family for the extraction stage
    - small machine-readable stage labels
    - structured details for debugging and tests
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

    def __str__(self) -> str:
        """
        Return the main human-readable message only.

        Example
        -------
        Calling:

            str(error)

        returns just the main explanation, while the richer structured context
        remains on:

        - `error.stage`
        - `error.details`
        """

        return self.message


def build_default_openai_resume_extraction_chat_model(
    *,
    model_name: str = DEFAULT_RESUME_EXTRACTION_MODEL_PROFILE.model_name,
    temperature: float = DEFAULT_RESUME_EXTRACTION_MODEL_PROFILE.temperature,
    max_output_tokens: int = DEFAULT_RESUME_EXTRACTION_MODEL_PROFILE.max_output_tokens,
) -> ChatOpenAI:
    """
    Build the default LangChain chat model for resume extraction.

    Parameters
    ----------
    model_name : str
        OpenAI model name to use.

    temperature : float
        Sampling temperature.

    max_output_tokens : int
        Maximum output-token target passed to the underlying provider wrapper.

    Returns
    -------
    ChatOpenAI
        LangChain chat model configured for structured extraction work.

    Notes
    -----
    - This helper is intentionally simple.
    - It assumes provider credentials are supplied through the runtime
      environment.
    - A future dedicated provider module can replace or wrap this helper later
      if the backend needs:
        - multi-provider routing
        - custom retries
        - usage tracking
        - central model factories

    Example
    -------
    Build a default extraction model:

        chat_model = build_default_openai_resume_extraction_chat_model()

    Or override the model name explicitly:

        chat_model = build_default_openai_resume_extraction_chat_model(
            model_name="gpt-5.4-mini",
            temperature=0.0,
            max_output_tokens=1600,
        )

    That returned `chat_model` can then be passed directly into:

        extract_jobadder_candidate_resume_profile(
            jobadder_account=2236,
            candidate_id=16496678,
            chat_model=chat_model,
        )

    In plain language:

    - build a usable default chat model
    - keep provider-transport details out of the extraction orchestration
    """

    return ChatOpenAI(
        model=model_name,
        temperature=temperature,
        max_tokens=max_output_tokens,
    )


def extract_jobadder_candidate_resume_profile(
    *,
    jobadder_account: int,
    candidate_id: int,
    chat_model: Any,
    model_profile: ModelProfile = DEFAULT_RESUME_EXTRACTION_MODEL_PROFILE,
) -> dict[str, Any]:
    """
    Run the structured resume-extraction flow for one JobAdder candidate.

    Parameters
    ----------
    jobadder_account : int
        JobAdder account identifier used to find the stored OAuth connection.

    candidate_id : int
        JobAdder candidate identifier to ingest and extract from.

    chat_model : Any
        LangChain-compatible chat model.

        In practice this should be a model that supports
        `with_structured_output(...)`, such as `ChatOpenAI`.

    model_profile : ModelProfile
        Local model description used for metadata and later observability.

    Returns
    -------
    dict[str, Any]
        Combined extraction result containing:

        - source-system identifiers
        - model metadata
        - the prompt-ready extraction input
        - the prompt bundle
        - the validated structured extraction output

    Raises
    ------
    JobAdderIngestPreparationError
        If the upstream JobAdder ingest flow fails.

    ResumeExtractionError
        If prompt preparation, model invocation, or output validation fails.

    Example
    -------
    A typical call looks like:

        result = extract_jobadder_candidate_resume_profile(
            jobadder_account=2236,
            candidate_id=16496678,
            chat_model=build_default_openai_resume_extraction_chat_model(),
        )

    The result then contains keys such as:

        result["extraction_input"]
        result["prompt_bundle"]
        result["structured_extraction"]

    And the validated extraction output can then be read via fields such as:

        result["structured_extraction"]["current_employer"]
        result["structured_extraction"]["emails"]
        result["structured_extraction"]["skills"]

    In plain language:

    - fetch the prepared JobAdder + CV text bundle
    - pass it into the LLM extraction layer
    - validate the returned structure before returning it
    """

    resume_text_bundle = extract_latest_jobadder_resume_text_for_candidate(
        jobadder_account=jobadder_account,
        candidate_id=candidate_id,
    )

    return extract_structured_candidate_profile_from_resume_bundle(
        resume_text_bundle=resume_text_bundle,
        chat_model=chat_model,
        model_profile=model_profile,
    )


def extract_structured_candidate_profile_from_resume_bundle(
    *,
    resume_text_bundle: dict[str, Any],
    chat_model: Any,
    model_profile: ModelProfile = DEFAULT_RESUME_EXTRACTION_MODEL_PROFILE,
) -> dict[str, Any]:
    """
    Run structured extraction from an already-prepared resume-text bundle.

    Parameters
    ----------
    resume_text_bundle : dict[str, Any]
        Prepared bundle returned by the upstream JobAdder ingest + text
        extraction flow.

    chat_model : Any
        LangChain-compatible chat model.

    model_profile : ModelProfile
        Local model description for metadata and traceability.

    Returns
    -------
    dict[str, Any]
        Structured extraction result.

    Notes
    -----
    - This helper is deliberately separate from the JobAdder convenience
      wrapper.
    - That means later sources can reuse the same extraction layer if they can
      produce the same prepared text-bundle contract.

    Example
    -------
    A caller that already has a prepared bundle can do:

        result = extract_structured_candidate_profile_from_resume_bundle(
            resume_text_bundle=resume_bundle,
            chat_model=chat_model,
        )

    That is useful later when the source is not JobAdder but the prepared
    bundle shape is equivalent.

    A successful result then contains:

        {
            "source_system": "jobadder",
            "source_candidate_id": 16496678,
            "model_profile": {...},
            "extraction_input": {...},
            "prompt_bundle": {...},
            "structured_extraction": {...},
        }
    """

    extraction_input = build_resume_extraction_input_from_jobadder_bundle(
        resume_text_bundle=resume_text_bundle,
    )
    prompt_bundle = build_resume_extraction_prompt(
        extraction_input=extraction_input,
    )

    extraction_chain = _build_langchain_resume_extraction_chain(
        chat_model=chat_model,
        system_prompt=prompt_bundle["system_prompt"],
        user_prompt=prompt_bundle["user_prompt"],
    )

    # LangChain becomes useful here because it can hold together:
    # - prompt construction
    # - provider invocation
    # - structured output parsing
    #
    # in one chain-shaped object.
    #
    # Even so, we still validate the final result ourselves before returning it.
    #
    # That second validation step is not redundant ceremony. It protects the
    # service boundary from:
    # - provider/library behaviour differences
    # - malformed model output that is "almost right"
    # - future refactors where the chain may stop returning a fully validated
    #   Pydantic object directly
    try:
        raw_result = extraction_chain.invoke({})
    except Exception as exc:
        raise ResumeExtractionError(
            "The resume extraction model call failed.",
            stage="llm_invoke",
            details=[
                {"source_system": extraction_input["source_system"]},
                {"source_candidate_id": extraction_input["source_candidate_id"]},
                {"provider": model_profile.provider},
                {"model_name": model_profile.model_name},
            ],
        ) from exc

    # Some structured-output paths may already hand back an instantiated
    # `ResumeStructuredExtraction`.
    #
    # Others may hand back a plain dictionary-like object. Supporting both
    # keeps this orchestration layer robust to small library-level behaviour
    # differences without loosening the final schema contract.
    if isinstance(raw_result, ResumeStructuredExtraction):
        structured_extraction = raw_result
    else:
        try:
            structured_extraction = ResumeStructuredExtraction.model_validate(raw_result)
        except ValidationError as exc:
            raise ResumeExtractionError(
                "The resume extraction model output did not match the expected schema.",
                stage="llm_output_validation",
                details=[
                    {"source_system": extraction_input["source_system"]},
                    {"source_candidate_id": extraction_input["source_candidate_id"]},
                    {"validation_errors": exc.errors()},
                ],
            ) from exc

    return {
        "source_system": extraction_input["source_system"],
        "source_candidate_id": extraction_input["source_candidate_id"],
        "jobadder_account": extraction_input.get("jobadder_account"),
        "model_profile": _serialise_model_profile(model_profile),
        "extraction_input": extraction_input,
        "prompt_bundle": prompt_bundle,
        "structured_extraction": structured_extraction.model_dump(),
    }


def build_resume_extraction_input_from_jobadder_bundle(
    *,
    resume_text_bundle: dict[str, Any],
    max_resume_characters: int = 22000,
    max_note_count: int = 5,
    max_note_characters: int = 2500,
) -> dict[str, Any]:
    """
    Build one prompt-ready extraction input from a prepared JobAdder text bundle.

    Parameters
    ----------
    resume_text_bundle : dict[str, Any]
        Bundle returned by the upstream JobAdder ingest flow.

    max_resume_characters : int
        Maximum number of resume characters to include.

    max_note_count : int
        Maximum number of cleaned candidate notes to include.

    max_note_characters : int
        Maximum number of characters to keep from each note.

    Returns
    -------
    dict[str, Any]
        Prompt-ready extraction input.

    Raises
    ------
    ResumeExtractionError
        If the bundle is missing required material.

    Why prompt limits exist
    -----------------------
    Resume text and candidate notes can get very large.

    If we throw everything into the prompt unbounded, we create predictable
    problems:

    - higher cost
    - higher latency
    - more prompt noise
    - more unstable extraction quality

    So this helper makes the prompt input deliberate rather than accidental.

    Example
    -------
    A prompt-ready input might look like:

        {
            "source_system": "jobadder",
            "source_candidate_id": 16496678,
            "candidate_context": {...},
            "latest_resume": {...},
            "cleaned_resume_text": "Roger Campbell\\nSenior Data Scientist...",
            "cleaned_candidate_notes": [...],
        }

    More concretely, the helper should:

    - prefer `extracted_resume_text["cleaned_text"]` over raw text
    - convert the larger candidate payload into a smaller candidate snapshot
    - convert the larger notes payload into smaller prompt-ready note items

    In plain language:

    - take the big upstream bundle
    - keep the pieces the model actually needs
    - keep them bounded so the prompt stays disciplined
    """

    candidate = resume_text_bundle.get("candidate")
    extracted_resume_text = resume_text_bundle.get("extracted_resume_text")
    notes_payload = resume_text_bundle.get("notes", {})
    latest_resume = resume_text_bundle.get("latest_resume")
    downloaded_resume = resume_text_bundle.get("downloaded_resume")

    if not isinstance(candidate, dict):
        raise ResumeExtractionError(
            "The prepared resume bundle is missing candidate data.",
            stage="input_validation",
            details=[],
        )

    if not isinstance(extracted_resume_text, dict):
        raise ResumeExtractionError(
            "The prepared resume bundle is missing extracted resume text.",
            stage="input_validation",
            details=[
                {"candidate_id": candidate.get("candidateId")},
            ],
        )

    cleaned_resume_text = extracted_resume_text.get("cleaned_text")
    raw_resume_text = extracted_resume_text.get("text")

    # Prefer cleaned resume text first, because the cleaning layer exists to
    # remove exactly the kind of formatting and encoding noise that would
    # otherwise distract the extraction model.
    #
    # Fall back to raw extracted text only so one missing `cleaned_text` key
    # does not break the whole flow unnecessarily.
    resume_text_for_prompt = cleaned_resume_text or raw_resume_text

    if not isinstance(resume_text_for_prompt, str) or resume_text_for_prompt.strip() == "":
        raise ResumeExtractionError(
            "The prepared resume bundle does not contain usable resume text.",
            stage="input_validation",
            details=[
                {"candidate_id": candidate.get("candidateId")},
                {"file_name": extracted_resume_text.get("file_name")},
            ],
        )

    # The notes payload may contain both:
    # - raw source note items
    # - cleaned prompt-facing note items
    #
    # At this stage we want the cleaned form. The extraction layer should not
    # have to repeat note-cleaning work that the ingest layer already did.
    cleaned_note_items = notes_payload.get("cleaned_items", [])
    prompt_ready_notes = _build_prompt_ready_candidate_notes(
        note_items=cleaned_note_items,
        max_note_count=max_note_count,
        max_note_characters=max_note_characters,
    )

    return {
        "source_system": resume_text_bundle.get("source_system", "jobadder"),
        "source_candidate_id": resume_text_bundle.get("source_candidate_id"),
        "jobadder_account": resume_text_bundle.get("jobadder_account"),
        "candidate_context": _build_candidate_context_snapshot(candidate),
        "latest_resume": _build_resume_context_snapshot(
            latest_resume=latest_resume,
            downloaded_resume=downloaded_resume,
            extracted_resume_text=extracted_resume_text,
        ),
        "cleaned_resume_text": _truncate_text(
            resume_text_for_prompt,
            max_characters=max_resume_characters,
        ),
        "cleaned_candidate_notes": prompt_ready_notes,
    }


def build_resume_extraction_prompt(
    *,
    extraction_input: dict[str, Any],
) -> dict[str, str]:
    """
    Build the system and user prompts for structured resume extraction.

    Parameters
    ----------
    extraction_input : dict[str, Any]
        Prompt-ready extraction input.

    Returns
    -------
    dict[str, str]
        Dictionary containing:

        - `system_prompt`
        - `user_prompt`

    Raises
    ------
    ResumeExtractionError
        If required prompt material is missing.

    Notes
    -----
    - The system prompt sets the extraction rules.
    - The user prompt supplies the actual candidate data and source text.
    - This split maps cleanly onto LangChain chat prompts.

    Example
    -------
    A successful result looks like:

        {
            "system_prompt": "You are a careful recruitment data-extraction assistant....",
            "user_prompt": "Extract a structured candidate-enrichment object from the following material....",
        }

    More concretely:

    - the `system_prompt` should contain the extraction rules and quality bar
    - the `user_prompt` should contain the actual candidate context, resume
      context, cleaned notes, and cleaned resume text

    In plain language:

    - one prompt explains the rules
    - the other prompt carries the candidate-specific source material
    """

    candidate_context = extraction_input.get("candidate_context")
    latest_resume = extraction_input.get("latest_resume")
    cleaned_resume_text = extraction_input.get("cleaned_resume_text")
    cleaned_candidate_notes = extraction_input.get("cleaned_candidate_notes", [])

    if not isinstance(candidate_context, dict):
        raise ResumeExtractionError(
            "The extraction input is missing candidate context.",
            stage="prompt_build",
            details=[],
        )

    if not isinstance(latest_resume, dict):
        raise ResumeExtractionError(
            "The extraction input is missing resume context.",
            stage="prompt_build",
            details=[],
        )

    if not isinstance(cleaned_resume_text, str) or cleaned_resume_text.strip() == "":
        raise ResumeExtractionError(
            "The extraction input is missing cleaned resume text.",
            stage="prompt_build",
            details=[],
        )

    system_prompt = """
You are a careful recruitment data-extraction assistant.

Your job is to read:
- structured candidate metadata from JobAdder
- cleaned resume text
- cleaned recruiter/candidate note text

and return one structured extraction object.

Rules:
1. Be conservative.
2. Prefer factual extraction over guesswork.
3. Use null when a field is genuinely unclear.
4. Do not invent employers, titles, dates, qualifications, or contact details.
5. Skills should be concise, deduplicated, and practically useful.
6. Employment history should be ordered from most recent to oldest when possible.
7. Education should include only entries reasonably supported by the source.
8. Evidence notes should explain what source material supports the extraction.
9. Ambiguity notes should explain uncertainty, contradictions, or missing context.
10. Return data that matches the requested schema exactly.
""".strip()

    # The user prompt is intentionally structured instead of conversational.
    #
    # This is backend extraction work, not a chat UI. We want the model to see
    # stable, explicit source material so the output is easier to:
    # - validate
    # - compare across runs
    # - debug when extraction quality is weak
    #
    # In other words, the prompt should read more like a disciplined work
    # packet than a chat message.
    user_prompt = f"""
Extract a structured candidate-enrichment object from the following material.

Candidate context
-----------------
{json.dumps(candidate_context, indent=2, ensure_ascii=False)}

Resume context
--------------
{json.dumps(latest_resume, indent=2, ensure_ascii=False)}

Cleaned candidate notes
-----------------------
{json.dumps(cleaned_candidate_notes, indent=2, ensure_ascii=False)}

Cleaned resume text
-------------------
{cleaned_resume_text}
""".strip()

    return {
        "system_prompt": system_prompt,
        "user_prompt": user_prompt,
    }


def _build_langchain_resume_extraction_chain(
    *,
    chat_model: Any,
    system_prompt: str,
    user_prompt: str,
) -> Any:
    """
    Build the LangChain extraction chain.

    Parameters
    ----------
    chat_model : Any
        LangChain-compatible chat model.

    system_prompt : str
        System prompt text.

    user_prompt : str
        User prompt text.

    Returns
    -------
    Any
        LangChain runnable chain.

    Notes
    -----
    The important contract here is that the supplied `chat_model` should
    support `with_structured_output(...)`.

    That gives us a robust first extraction boundary because:
    - the model is explicitly told the output schema
    - LangChain handles the structured-output wrapper
    - this service still validates the returned object before trusting it

    Example
    -------
    The resulting chain conceptually behaves like:

        prompt -> structured model -> validated object

    More concretely, the chain is built from:

        ChatPromptTemplate.from_messages([...])
        chat_model.with_structured_output(ResumeStructuredExtraction)

    In plain language:

    - format the messages
    - call the model
    - ask for a schema-shaped response
    """

    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", system_prompt),
            ("human", user_prompt),
        ]
    )

    # This is the key LangChain feature we actually care about here:
    # provider-backed structured output.
    #
    # We are not using LangChain just for the sake of it. We are using the
    # smallest part that materially improves the extraction boundary:
    # - schema-aware model invocation
    # - cleaner prompt + model composition
    #
    # The important design point is that the rest of this service does not need
    # to know the provider-specific mechanics of how structured output is
    # requested. It only needs a runnable chain that honors the schema.
    structured_model = chat_model.with_structured_output(ResumeStructuredExtraction)

    return prompt | structured_model


def _build_candidate_context_snapshot(candidate: dict[str, Any]) -> dict[str, Any]:
    """
    Build a compact structured snapshot of the JobAdder candidate metadata.

    Notes
    -----
    The full JobAdder payload is useful to keep in storage and debugging flows,
    but it is not the right shape to dump into the first extraction prompt
    wholesale.

    This helper deliberately selects the fields most likely to help extraction:
    - identity basics
    - contact hints
    - status
    - skill tags
    - timestamps

    That keeps the prompt focused and more explainable.

    Example
    -------
    A compact candidate snapshot might look like:

        {
            "candidate_id": 16496678,
            "first_name": "Roger",
            "last_name": "Campbell",
            "email": "the_rfc@hotmail.co.uk",
            "mobile": "07934 890 708",
            "location": "London",
            "status": "Active",
            "skill_tags": ["machine learning", "NLP"],
            "created_at": "2025-07-10T16:01:10Z",
            "updated_at": "2026-04-20T10:02:24Z",
        }

    This is intentionally smaller than the full JobAdder candidate object. The
    model does not need every upstream field just to extract employer, title,
    skills, and history.
    """

    return {
        "candidate_id": candidate.get("candidateId"),
        "first_name": candidate.get("firstName"),
        "last_name": candidate.get("lastName"),
        "email": candidate.get("email"),
        "mobile": candidate.get("mobile"),
        "location": candidate.get("location"),
        "status": candidate.get("status"),
        "skill_tags": candidate.get("skillTags", []),
        "created_at": candidate.get("createdAt"),
        "updated_at": candidate.get("updatedAt"),
    }


def _build_resume_context_snapshot(
    *,
    latest_resume: dict[str, Any] | None,
    downloaded_resume: dict[str, Any] | None,
    extracted_resume_text: dict[str, Any] | None,
) -> dict[str, Any]:
    """
    Build a compact structured snapshot of the selected resume.

    Notes
    -----
    The model does not need:
    - raw bytes
    - transport details
    - every upstream field

    It does benefit from:
    - file name
    - mime type
    - page count
    - character count

    because those help later debugging and evaluation.

    Example
    -------
    A compact resume snapshot might look like:

        {
            "attachment_id": 21091489,
            "file_name": "Roger Campbell - CV 2025.pdf",
            "mime_type": "application/pdf",
            "created_at": "2026-04-20T10:00:00Z",
            "page_count": 2,
            "character_count": 5120,
            "extractor": "pypdf",
        }

    This is enough to give the model document context without leaking raw bytes
    or lower-level transport details into the prompt layer.
    """

    latest_resume = latest_resume or {}
    downloaded_resume = downloaded_resume or {}
    extracted_resume_text = extracted_resume_text or {}

    return {
        "attachment_id": latest_resume.get("attachmentId"),
        "file_name": downloaded_resume.get("file_name") or latest_resume.get("fileName"),
        "mime_type": downloaded_resume.get("content_type") or latest_resume.get("fileType"),
        "created_at": latest_resume.get("createdAt"),
        "page_count": extracted_resume_text.get("page_count"),
        "character_count": extracted_resume_text.get("character_count"),
        "extractor": extracted_resume_text.get("extractor"),
    }


def _build_prompt_ready_candidate_notes(
    *,
    note_items: list[dict[str, Any]],
    max_note_count: int,
    max_note_characters: int,
) -> list[dict[str, Any]]:
    """
    Build a bounded list of cleaned candidate notes for prompt use.

    Notes
    -----
    Candidate notes are useful because they often contain:
    - recruiter context
    - relationship history
    - job-process context
    - hints about current status or intent

    But they can also become prompt bloat very quickly, especially when they
    contain long email threads and disclaimers.

    This helper therefore makes a controlled tradeoff:
    - keep a small number of notes
    - keep the most useful metadata
    - truncate oversized note bodies

    Example
    -------
    A prompt-ready note item might look like:

        {
            "note_id": "79d7b82f-3d11-4e2a-86bd-d68efdc09e0a",
            "type": "Email Reply",
            "created_at": "2026-04-06T08:51:06Z",
            "updated_at": "2026-04-06T08:51:06Z",
            "cleaned_text": "Hi Roger, Great to hear from you....",
        }

    That is intentionally smaller than the full upstream notes payload. The
    model mainly needs:

    - note type
    - timestamps
    - cleaned note text
    """

    prompt_ready_notes: list[dict[str, Any]] = []

    # Limit first, then cleanly project each kept note into the smaller prompt
    # shape. That keeps the transformation easy to read and makes it obvious
    # where note-count control happens.
    for note in note_items[:max_note_count]:
        note_text = note.get("cleaned_text") or note.get("text") or ""

        if not isinstance(note_text, str) or note_text.strip() == "":
            continue

        prompt_ready_notes.append(
            {
                "note_id": note.get("note_id"),
                "type": note.get("type"),
                "created_at": note.get("created_at"),
                "updated_at": note.get("updated_at"),
                "cleaned_text": _truncate_text(
                    note_text,
                    max_characters=max_note_characters,
                ),
            }
        )

    return prompt_ready_notes


def _truncate_text(text: str, *, max_characters: int) -> str:
    """
    Truncate text conservatively for prompt use.

    Notes
    -----
    The goal is not to hide information or to rewrite meaning.

    The goal is simply to stop:
    - giant CV bodies
    - giant note chains
    - unbounded prompt payloads

    from growing without control in the first extraction implementation.

    Example
    -------
    If `max_characters` is `20`, then:

        _truncate_text("abcdefghijklmnopqrstuvwxyz", max_characters=20)

    returns a shortened string ending with:

        "[TRUNCATED FOR PROMPT]"

    The returned marker is intentional. It makes later debugging easier because
    a reader can tell the text was deliberately shortened rather than assuming
    the source document simply ended there.
    """

    if len(text) <= max_characters:
        return text

    return text[: max_characters - 21].rstrip() + "\n\n[TRUNCATED FOR PROMPT]"


def _serialise_model_profile(profile: ModelProfile) -> dict[str, Any]:
    """
    Convert a `ModelProfile` into a plain dictionary.

    Notes
    -----
    Returning plain serialisable data is useful because later:
    - tests
    - logs
    - route handlers
    - background jobs

    can all consume the same shape without dataclass-specific handling.

    Example
    -------
    A serialised profile looks like:

        {
            "provider": "openai",
            "model_name": "gpt-5.4",
            "purpose": "extraction",
            "temperature": 0.0,
            "max_output_tokens": 2200,
        }

    That plain dictionary can then be:

    - returned from a route
    - logged
    - asserted in tests
    """

    return asdict(profile)


__all__ = [
    "DEFAULT_RESUME_EXTRACTION_MODEL_PROFILE",
    "EducationHistoryItem",
    "EmploymentHistoryItem",
    "ResumeExtractionError",
    "ResumeStructuredExtraction",
    "build_default_openai_resume_extraction_chat_model",
    "build_resume_extraction_input_from_jobadder_bundle",
    "build_resume_extraction_prompt",
    "extract_jobadder_candidate_resume_profile",
    "extract_structured_candidate_profile_from_resume_bundle",
]
