"""
Model configuration types for the intelligence backend.

This module defines small typed objects for describing which LLM provider and
model the backend should use.

It gives the rest of the repository a stable way to talk about:

- model providers
- model names
- temperature
- token limits
- whether a model is intended for reasoning or lightweight utility work
- future provider routing across OpenAI, OpenRouter, Nemotron, and other models

Keeping model configuration in its own module makes the project easier to extend
because:

- `backend.llm` can own model/provider concerns
- LangGraph nodes can receive model configuration without hard-coding provider
  strings
- future LangChain wrappers can build model clients from these typed settings
- tests can validate model configuration without calling real model APIs

In plain language:

- this module answers the question:

    "How should the backend describe an LLM before it actually calls one?"

- it does not call OpenAI
- it does not call OpenRouter
- it does not call Nemotron
- it does not create LangChain model clients yet
- it does not require API keys
- it only defines safe local configuration types

Notes
-----
- This is deliberately not a full model provider implementation.
- Real model clients should be created later in a separate module.
- API keys should come from `backend.settings`, not from this module.
- This module is useful before source-system access exists because it lets us
  prepare the shape of the LLM layer without making real external calls.

Future direction
----------------
Later, this module may be used by code such as:

    backend.llm.providers
    backend.llm.structured_output
    backend.graphs.candidate_job_match
    backend.services.matching_service

A future provider factory might accept a `ModelProfile` and return a LangChain
chat model.

For now, `ModelProfile` is only a typed description.
"""

from dataclasses import dataclass
from enum import StrEnum


class ModelProvider(StrEnum):
    """
    Supported model provider identifiers.

    Attributes
    ----------
    OPENAI : str
        OpenAI model provider.

        This can cover GPT models when we use OpenAI directly.

    OPENROUTER : str
        OpenRouter model provider.

        This can support provider routing and lower-cost model experiments.

    NEMOTRON : str
        Nemotron model provider.

        This is included because the client has mentioned Nemotron as a possible
        lower-cost or high-capability model option.

    PERPLEXITY : str
        Perplexity model provider.

        This is useful for research-style tasks where web-backed citations may
        matter.

    Notes
    -----
    - These are provider identifiers, not model names.
    - A provider can expose many different models.
    - Keeping providers constrained prevents random strings spreading through the
      codebase.

    In plain language:

    - provider = who supplies the model
    - model name = which model from that provider
    """

    OPENAI = "openai"
    OPENROUTER = "openrouter"
    NEMOTRON = "nemotron"
    PERPLEXITY = "perplexity"


class ModelPurpose(StrEnum):
    """
    Intended purpose for a model profile.

    Attributes
    ----------
    REASONING : str
        Model intended for harder reasoning tasks.

        Examples:

        - candidate/job comparison
        - evidence evaluation
        - recommendation explanation
        - workflow decision support

    EXTRACTION : str
        Model intended for structured extraction from text.

        Examples:

        - extracting skills from a CV
        - extracting company names from notes
        - extracting hiring-manager details from emails

    SUMMARISATION : str
        Model intended for summarising text.

        Examples:

        - summarising candidate notes
        - summarising a CV
        - summarising client email threads

    CLASSIFICATION : str
        Model intended for assigning labels or categories.

        Examples:

        - candidate status classification
        - document type classification
        - urgency classification

    UTILITY : str
        Model intended for lightweight helper tasks.

        Examples:

        - formatting
        - simple rewriting
        - small internal helper outputs

    Notes
    -----
    - Purpose is not the same as provider.
    - Purpose helps future code choose the right model for the job.
    - For example, reasoning may use a stronger model while extraction may use a
      cheaper structured-output model.

    In plain language:

    - purpose = why we are using the model
    """

    REASONING = "reasoning"
    EXTRACTION = "extraction"
    SUMMARISATION = "summarisation"
    CLASSIFICATION = "classification"
    UTILITY = "utility"


@dataclass(frozen=True, slots=True)
class ModelProfile:
    """
    Local description of an LLM model configuration.

    Attributes
    ----------
    provider : ModelProvider
        Provider that supplies the model.

        Example:

            ModelProvider.OPENAI

    model_name : str
        Provider-specific model name.

        Example:

            "gpt-5.4"

        This module does not validate whether the model currently exists. That
        should happen later in the provider-specific code or documentation checks.

    purpose : ModelPurpose
        Intended use of the model profile.

        This helps future code select different models for different tasks.

    temperature : float
        Sampling temperature for model output.

        Lower values are more deterministic.
        Higher values are more varied.

        For structured backend workflows, lower values are usually safer.

    max_output_tokens : int
        Maximum number of output tokens the model should produce.

        This is a local configuration value. Provider-specific clients may use
        slightly different parameter names.

    Notes
    -----
    - This class does not create a model client.
    - This class does not make network calls.
    - This class does not know any API keys.
    - It is safe to use in tests because it is only data.

    Example
    -------
    Define a reasoning model profile:

        profile = ModelProfile(
            provider=ModelProvider.OPENAI,
            model_name="gpt-5.4",
            purpose=ModelPurpose.REASONING,
            temperature=0.2,
            max_output_tokens=1200,
        )

    In plain language:

    - choose a provider
    - choose a model name
    - say what the model is for
    - set basic generation controls
    """

    provider: ModelProvider
    model_name: str
    purpose: ModelPurpose
    temperature: float = 0.2
    max_output_tokens: int = 1200

# Default lightweight local profile
#   - This is only a description.
#   - It does not call a provider.
#   - It gives tests and future graph code a stable default to import.
DEFAULT_UTILITY_MODEL_PROFILE = ModelProfile(
    provider=ModelProvider.OPENAI,
    model_name="gpt-5.4-mini",
    purpose=ModelPurpose.UTILITY,
    temperature=0.0,
    max_output_tokens=500,
)

# Default reasoning profile
#   - This is a placeholder for harder future workflows.
#   - It can be changed later once provider choices and cost assumptions are
#     agreed.
DEFAULT_REASONING_MODEL_PROFILE = ModelProfile(
    provider=ModelProvider.OPENAI,
    model_name="gpt-5.4",
    purpose=ModelPurpose.REASONING,
    temperature=0.2,
    max_output_tokens=1200,
)


def is_deterministic_profile(profile: ModelProfile) -> bool:
    """
    Return whether a model profile is configured for deterministic-style output.

    Parameters
    ----------
    profile : ModelProfile
        Model profile to inspect.

    Returns
    -------
    bool
        `True` when the profile temperature is zero.

        `False` otherwise.

    Notes
    -----
    - Temperature `0.0` is commonly used when we want stable, repeatable output.
    - Some providers may still have small nondeterminism even at temperature zero.
    - This helper only checks local configuration.
    - It does not make provider-specific guarantees.

    Example
    -------
    This profile is deterministic-style:

        ModelProfile(
            provider=ModelProvider.OPENAI,
            model_name="gpt-5.4-mini",
            purpose=ModelPurpose.UTILITY,
            temperature=0.0,
            max_output_tokens=500,
        )

    This profile is not:

        ModelProfile(
            provider=ModelProvider.OPENAI,
            model_name="gpt-5.4",
            purpose=ModelPurpose.REASONING,
            temperature=0.2,
            max_output_tokens=1200,
        )

    In plain language:

    - temperature zero means "try to be predictable"
    """

    return profile.temperature == 0.0


__all__ = [
    "DEFAULT_REASONING_MODEL_PROFILE",
    "DEFAULT_UTILITY_MODEL_PROFILE",
    "ModelProfile",
    "ModelProvider",
    "ModelPurpose",
    "is_deterministic_profile",
]
