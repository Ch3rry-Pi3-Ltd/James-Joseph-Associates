"""
Resume extraction helpers.

This module is the first real LLM-facing stage in the candidate-ingestion
pipeline.

Why this module exists
----------------------
By this point in the backend, we can already:

- connect to JobAdder reliably
- refresh JobAdder tokens when needed
- fetch candidate detail
- fetch candidate attachments
- fetch candidate notes
- identify the latest likely resume
- download the selected resume bytes
- extract plain text from the PDF
- clean the extracted resume text
- clean the JobAdder note text

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

In plain language:

- take the prepared JobAdder + CV bundle
- build a careful extraction prompt
- ask the model for structured output
- validate that output before the rest of the backend trusts it
"""

from dataclasses import dataclass
import json
from typing import Any

from langchain_core.prompts import ChatMessagePromptTemplate
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field, ValidationError

from backend.llm.models import ModelProfile, ModelProvider, ModelPurpose
from backend.services.jobadder_ingest import(
    JobAdderIngestPreparationError,
    extract_latest_jobadder_resume_text_for_candidate,
)