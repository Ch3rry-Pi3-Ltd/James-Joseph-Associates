"""
Unit tests for local LLM model configuration types.

These tests verify the small model-description layer before the backend starts
creating real LangChain model clients.

They focus on:

- stable provider identifiers
- stable model-purpose identifiers
- default utility model configuration
- default reasoning model configuration
- deterministic-style profile detection
- immutable model profile objects

The important question is:

    "Can the backend describe model choices safely without making real model API
    calls?"

This is different from future LLM integration tests.

Future LLM tests may check:

- LangChain chat model creation
- provider-specific API clients
- structured output parsing
- model fallback routing
- LangGraph node behaviour with real or mocked model calls

These tests do not do any of that yet.

This unit test checks the smaller foundation pieces directly:

    ModelProvider
        -> stable provider strings

    ModelPurpose
        -> stable purpose strings

    ModelProfile
        -> local typed model description

    is_deterministic_profile(...)
        -> local temperature check

In plain language:

- no API keys
- no network calls
- no LLM calls
- just local model configuration behaviour
"""

from dataclasses import FrozenInstanceError

import pytest

from backend.llm.models import (
    DEFAULT_REASONING_MODEL_PROFILE,
    DEFAULT_UTILITY_MODEL_PROFILE,
    ModelProfile,
    ModelProvider,
    ModelPurpose,
    is_deterministic_profile,
)


def test_model_provider_values_are_stable() -> None:
    """
    Verify that model provider enum values are stable.

    Notes
    -----
    - These values may be used in settings, logs, tests, and future routing code.
    - If a provider string changes accidentally, configuration can become harder
      to reason about.
    - The enum keeps provider identifiers constrained.

    Expected values
    ---------------
    The current provider identifiers are:

        openai
        openrouter
        nemotron
        perplexity

    In plain language:

    - provider values should be predictable strings
    """

    assert ModelProvider.OPENAI == "openai"
    assert ModelProvider.OPENROUTER == "openrouter"
    assert ModelProvider.NEMOTRON == "nemotron"
    assert ModelProvider.PERPLEXITY == "perplexity"


def test_model_purpose_values_are_stable() -> None:
    """
    Verify that model purpose enum values are stable.

    Notes
    -----
    - Purpose values describe why the backend would use a model.
    - They are separate from provider names.
    - This lets future code choose different models for different jobs.

    Expected values
    ---------------
    The current purpose identifiers are:

        reasoning
        extraction
        summarisation
        classification
        utility

    In plain language:

    - purpose values should be predictable strings
    """

    assert ModelPurpose.REASONING == "reasoning"
    assert ModelPurpose.EXTRACTION == "extraction"
    assert ModelPurpose.SUMMARISATION == "summarisation"
    assert ModelPurpose.CLASSIFICATION == "classification"
    assert ModelPurpose.UTILITY == "utility"


def test_default_utility_model_profile_is_configured_for_lightweight_work() -> None:
    """
    Verify the default utility model profile.

    Notes
    -----
    - The utility profile is meant for small helper tasks.
    - It uses a low temperature for predictable output.
    - It is only a local description, not a real model client.

    Expected profile
    ----------------
    The default utility profile should use:

        provider: openai
        model_name: gpt-5.4-mini
        purpose: utility
        temperature: 0.0
        max_output_tokens: 500

    In plain language:

    - this is the cheap/simple/default helper model description
    """

    assert DEFAULT_UTILITY_MODEL_PROFILE == ModelProfile(
        provider=ModelProvider.OPENAI,
        model_name="gpt-5.4-mini",
        purpose=ModelPurpose.UTILITY,
        temperature=0.0,
        max_output_tokens=500,
    )


def test_default_reasoning_model_profile_is_configured_for_reasoning_work() -> None:
    """
    Verify the default reasoning model profile.

    Notes
    -----
    - The reasoning profile is intended for harder future workflows.
    - It uses a slightly higher temperature than the utility profile.
    - It is still only a local description, not a real model client.

    Expected profile
    ----------------
    The default reasoning profile should use:

        provider: openai
        model_name: gpt-5.4
        purpose: reasoning
        temperature: 0.2
        max_output_tokens: 1200

    In plain language:

    - this is the stronger default reasoning model description
    """

    assert DEFAULT_REASONING_MODEL_PROFILE == ModelProfile(
        provider=ModelProvider.OPENAI,
        model_name="gpt-5.4",
        purpose=ModelPurpose.REASONING,
        temperature=0.2,
        max_output_tokens=1200,
    )


def test_is_deterministic_profile_returns_true_for_temperature_zero() -> None:
    """
    Verify that temperature zero is treated as deterministic-style configuration.

    Notes
    -----
    - This does not guarantee perfect provider-level determinism.
    - It only checks local configuration.
    - Temperature zero is still the normal signal for "try to be predictable".

    In plain language:

    - temperature 0 means deterministic-style
    """

    profile = ModelProfile(
        provider=ModelProvider.OPENAI,
        model_name="gpt-5.4-mini",
        purpose=ModelPurpose.UTILITY,
        temperature=0.0,
        max_output_tokens=500,
    )

    assert is_deterministic_profile(profile) is True


def test_is_deterministic_profile_returns_false_for_non_zero_temperature() -> None:
    """
    Verify that non-zero temperature is not treated as deterministic-style.

    Notes
    -----
    - Reasoning models may use non-zero temperature.
    - That can allow slightly more varied outputs.
    - The helper should return `False` for those profiles.

    In plain language:

    - temperature above zero means not deterministic-style
    """

    profile = ModelProfile(
        provider=ModelProvider.OPENAI,
        model_name="gpt-5.4",
        purpose=ModelPurpose.REASONING,
        temperature=0.2,
        max_output_tokens=1200,
    )

    assert is_deterministic_profile(profile) is False


def test_default_utility_profile_is_deterministic() -> None:
    """
    Verify that the default utility profile is deterministic-style.

    Notes
    -----
    - Utility tasks should usually be stable and predictable.
    - The default utility profile has `temperature=0.0`.
    - The helper should therefore return `True`.

    In plain language:

    - the helper model is configured for predictable output
    """

    assert is_deterministic_profile(DEFAULT_UTILITY_MODEL_PROFILE) is True


def test_default_reasoning_profile_is_not_deterministic() -> None:
    """
    Verify that the default reasoning profile is not deterministic-style.

    Notes
    -----
    - The reasoning profile currently uses `temperature=0.2`.
    - That means it is not strict deterministic-style configuration.
    - This can be adjusted later if we want stricter repeatability.

    In plain language:

    - the reasoning model has some room for variation
    """

    assert is_deterministic_profile(DEFAULT_REASONING_MODEL_PROFILE) is False


def test_model_profile_is_immutable() -> None:
    """
    Verify that model profiles cannot be mutated after creation.

    Notes
    -----
    - `ModelProfile` uses `@dataclass(frozen=True, slots=True)`.
    - `frozen=True` means existing attributes cannot be reassigned.
    - This prevents accidental runtime mutation of shared default profiles.

    Example
    -------
    This should fail:

        profile.temperature = 0.9

    In plain language:

    - once a profile is created, do not change it in place
    - create a new profile instead
    """

    profile = ModelProfile(
        provider=ModelProvider.OPENAI,
        model_name="gpt-5.4-mini",
        purpose=ModelPurpose.UTILITY,
        temperature=0.0,
        max_output_tokens=500,
    )

    # Mutating a frozen dataclass should raise an error.
    #   - We use `pytest.raises` to prove the mutation is blocked.
    with pytest.raises(FrozenInstanceError):
        profile.temperature = 0.9


def test_model_profile_can_describe_non_openai_provider() -> None:
    """
    Verify that model profiles can describe non-OpenAI providers.

    Notes
    -----
    - The project may later route some calls through OpenRouter, Nemotron, or
      Perplexity.
    - This test proves `ModelProfile` is not hard-coded to OpenAI.
    - It still does not create a real model client.

    In plain language:

    - the profile can describe another provider
    - but it still only stores local configuration
    """

    profile = ModelProfile(
        provider=ModelProvider.OPENROUTER,
        model_name="example-router-model",
        purpose=ModelPurpose.REASONING,
        temperature=0.1,
        max_output_tokens=800,
    )

    assert profile.provider == ModelProvider.OPENROUTER
    assert profile.model_name == "example-router-model"
    assert profile.purpose == ModelPurpose.REASONING
    assert profile.temperature == 0.1
    assert profile.max_output_tokens == 800
