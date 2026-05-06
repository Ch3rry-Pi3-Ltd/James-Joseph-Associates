"""
Unit tests for LLM provider helpers.

This module tests the provider-factory layer in `backend.llm.providers`.

Why these tests matter
----------------------
The rest of the backend now has a clear separation between:

- local model descriptions in `backend.llm.models`
- real provider-backed chat-model clients in `backend.llm.providers`

That separation is useful, but it only stays useful if the provider layer is
predictable.

This module therefore tests the next question:

    "Given a local `ModelProfile`, can the backend build the right provider
    client or fail clearly when the profile/configuration is invalid?"

That matters because this provider module is shared infrastructure.

If it becomes loose or inconsistent, the downstream effects spread into every
LLM-using service, such as:

- resume extraction
- candidate/job matching
- summarisation
- drafting
- later graph nodes

So these tests protect the provider boundary before more features start
depending on it.

Scope of these tests
--------------------
These tests intentionally do not:

- call the real OpenAI API
- require a real API key
- make network calls
- test LangChain provider transport behaviour end to end

Instead, they focus on the local backend logic around:

- provider dispatch
- local `ModelProfile` validation
- OpenAI-builder argument handling
- clear failure classification

Example
-------
A typical test in this module proves that a valid OpenAI model profile such as:

    ModelProfile(
        provider=ModelProvider.OPENAI,
        model_name="gpt-5.4-mini",
        purpose=ModelPurpose.UTILITY,
        temperature=0.0,
        max_output_tokens=500,
    )

can be turned into a `ChatOpenAI` client, while invalid profiles fail with
`LLMProviderConfigurationError` and a useful `stage` label.

In plain language:

- build a fake but realistic model profile
- feed it into the provider factory
- confirm the result or failure is exactly what the rest of the backend expects
"""

from typing import Any

import pytest
from langchain_openai import ChatOpenAI

import backend.llm.providers as providers
from backend.llm.models import ModelProfile, ModelProvider, ModelPurpose
from backend.llm.providers import (
    LLMProviderConfigurationError,
    build_langchain_chat_model,
    build_openai_chat_model,
    build_openrouter_chat_model,
)


def _build_openai_test_profile(
    *,
    model_name: str = "gpt-5.4-mini",
    temperature: float = 0.0,
    max_output_tokens: int = 500,
) -> ModelProfile:
    """
    Return a realistic OpenAI-backed `ModelProfile` for provider tests.

    Parameters
    ----------
    model_name : str
        Model name to place on the profile.

    temperature : float
        Temperature value to place on the profile.

    max_output_tokens : int
        Output-token limit to place on the profile.

    Returns
    -------
    ModelProfile
        OpenAI-backed profile for provider tests.

    Notes
    -----
    - This helper keeps the tests concise by centralizing the most common valid
      profile shape.
    - Individual tests can then override only the one field relevant to the
      scenario they are proving.

    Example
    -------
    A test can start from:

        profile = _build_openai_test_profile()

    and then create a broken case such as:

        broken_profile = _build_openai_test_profile(model_name="")

    In plain language:

    - make one good default OpenAI profile
    - let each test tweak only the field it cares about
    """

    return ModelProfile(
        provider=ModelProvider.OPENAI,
        model_name=model_name,
        purpose=ModelPurpose.UTILITY,
        temperature=temperature,
        max_output_tokens=max_output_tokens,
    )


def _build_openrouter_test_profile(
    *,
    model_name: str = "nvidia/nemotron-3-nano-30b-a3b:nitro",
    temperature: float = 0.0,
    max_output_tokens: int = 500,
) -> ModelProfile:
    """
    Return a realistic OpenRouter-backed `ModelProfile` for provider tests.

    Parameters
    ----------
    model_name : str
        Model name to place on the profile.

    temperature : float
        Temperature value to place on the profile.

    max_output_tokens : int
        Output-token limit to place on the profile.

    Returns
    -------
    ModelProfile
        OpenRouter-backed profile for provider tests.

    Example
    -------
    A test can start from:

        profile = _build_openrouter_test_profile()

    and then override only the one field relevant to that test.

    In plain language:

    - make one good default OpenRouter profile
    - let each test tweak only the field it cares about
    """

    return ModelProfile(
        provider=ModelProvider.OPENROUTER,
        model_name=model_name,
        purpose=ModelPurpose.UTILITY,
        temperature=temperature,
        max_output_tokens=max_output_tokens,
    )


def test_build_openai_chat_model_returns_chatopenai_for_valid_profile() -> None:
    """
    Verify that the explicit OpenAI builder returns a `ChatOpenAI` instance when
    given a valid OpenAI-backed profile.

    Notes
    -----
    - This is the basic "happy path" for the OpenAI-specific helper.
    - The test does not need to call the real provider.
    - It only needs to prove that the local configuration path produces the
      expected LangChain client type.
    - `ChatOpenAI` validates that credentials exist even before any real model
      call happens, so this test supplies a dummy explicit API key rather than
      depending on the outer shell environment.

    Example
    -------
    Starting from a valid profile such as:

        ModelProfile(
            provider=ModelProvider.OPENAI,
            model_name="gpt-5.4-mini",
            purpose=ModelPurpose.UTILITY,
            temperature=0.0,
            max_output_tokens=500,
        )

    the helper should return a `ChatOpenAI`.

    In this test we pass:

        api_key="sk-test-value"

    because the provider client constructor requires either:

    - an explicit key
    - or a real `OPENAI_API_KEY` environment variable

    In plain language:

    - pass in one good OpenAI profile
    - confirm the builder gives back the right client type
    """

    profile = _build_openai_test_profile()

    result = build_openai_chat_model(
        profile=profile,
        api_key="sk-test-value",
        timeout_seconds=30.0,
    )

    assert isinstance(result, ChatOpenAI)


def test_build_openai_chat_model_uses_environment_api_key_when_explicit_key_is_omitted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    Verify that the OpenAI-specific builder can rely on `OPENAI_API_KEY` from
    the environment when no explicit API key is supplied.

    Notes
    -----
    - The production helper intentionally allows the SDK to resolve credentials
      from the environment.
    - That behaviour is worth testing directly so the provider layer does not
      silently drift into "explicit key only" behaviour later.
    - This still does not make a real provider call. It only proves that local
      client construction succeeds when the expected environment variable is
      present.

    Example
    -------
    We set:

        OPENAI_API_KEY="sk-env-test-value"

    then call:

        build_openai_chat_model(profile=profile)

    and expect a `ChatOpenAI` client back.

    In plain language:

    - simulate the normal env-var credential path
    - omit the explicit key on purpose
    - confirm the builder still works
    """

    profile = _build_openai_test_profile()

    # Simulate the normal SDK credential path. This keeps the test honest about
    # the builder's documented behaviour without requiring a real secret.
    monkeypatch.setenv("OPENAI_API_KEY", "sk-env-test-value")

    result = build_openai_chat_model(profile=profile)

    assert isinstance(result, ChatOpenAI)


def test_build_openai_chat_model_accepts_explicit_api_key() -> None:
    """
    Verify that the explicit OpenAI builder accepts a non-empty explicit API
    key and still builds a usable `ChatOpenAI` client.

    Notes
    -----
    - This test is not proving that the API key works against the real OpenAI
      API.
    - It is only proving that the local provider helper accepts a usable
      explicit key and passes local validation.

    Example
    -------
    A caller may want to do:

        build_openai_chat_model(
            profile=profile,
            api_key="sk-test-value",
            timeout_seconds=45.0,
        )

    and receive a `ChatOpenAI` client.

    In plain language:

    - give the builder a valid explicit key
    - confirm that still builds cleanly
    """

    profile = _build_openai_test_profile()

    result = build_openai_chat_model(
        profile=profile,
        api_key="sk-test-value",
        timeout_seconds=45.0,
    )

    assert isinstance(result, ChatOpenAI)


def test_build_openai_chat_model_uses_settings_fallbacks_when_arguments_are_omitted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    Verify that the OpenAI-specific builder falls back to backend settings when
    the caller omits both `api_key` and `timeout_seconds`.

    Notes
    -----
    - This test is about the provider layer's own fallback logic, not about the
      real `ChatOpenAI` constructor.
    - So it replaces both:
        - `get_settings()`
        - `ChatOpenAI`
      with small fakes.
    - That keeps the test focused on one question:
        - did the provider helper resolve the right values before constructing
          the client?

    Example
    -------
    We fake backend settings like:

        openai_api_key = "sk-from-settings"
        llm_timeout_seconds = 33.0

    then call:

        build_openai_chat_model(profile=profile)

    and confirm those settings-backed values are passed into the client
    constructor.

    In plain language:

    - omit the explicit arguments on purpose
    - fake the settings object
    - prove the provider helper uses settings as its fallback path
    """

    profile = _build_openai_test_profile()
    captured_kwargs: dict[str, Any] = {}

    class FakeSettings:
        openai_api_key = "sk-from-settings"
        llm_timeout_seconds = 33.0

    class FakeChatOpenAI:
        def __init__(self, **kwargs: Any) -> None:
            captured_kwargs.update(kwargs)

    monkeypatch.setattr(providers, "get_settings", lambda: FakeSettings())
    monkeypatch.setattr(providers, "ChatOpenAI", FakeChatOpenAI)

    result = build_openai_chat_model(profile=profile)

    assert isinstance(result, FakeChatOpenAI)
    assert captured_kwargs == {
        "model": "gpt-5.4-mini",
        "temperature": 0.0,
        "max_tokens": 500,
        "timeout": 33.0,
        "api_key": "sk-from-settings",
    }


def test_build_openai_chat_model_prefers_explicit_arguments_over_settings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    Verify that explicit runtime arguments override backend settings when both
    are available.

    Notes
    -----
    - This precedence rule is important because services and tests sometimes
      need to supply one-off values without mutating global settings.
    - If explicit values did not win, the provider layer would be much harder
      to reason about in integration code.

    Example
    -------
    We fake backend settings with:

        openai_api_key = "sk-from-settings"
        llm_timeout_seconds = 99.0

    then call:

        build_openai_chat_model(
            profile=profile,
            api_key="sk-explicit",
            timeout_seconds=12.5,
        )

    and confirm the explicit values are the ones passed into the client
    constructor.

    In plain language:

    - provide both settings and explicit arguments
    - confirm the explicit arguments win
    """

    profile = _build_openai_test_profile()
    captured_kwargs: dict[str, Any] = {}

    class FakeSettings:
        openai_api_key = "sk-from-settings"
        llm_timeout_seconds = 99.0

    class FakeChatOpenAI:
        def __init__(self, **kwargs: Any) -> None:
            captured_kwargs.update(kwargs)

    monkeypatch.setattr(providers, "get_settings", lambda: FakeSettings())
    monkeypatch.setattr(providers, "ChatOpenAI", FakeChatOpenAI)

    result = build_openai_chat_model(
        profile=profile,
        api_key="sk-explicit",
        timeout_seconds=12.5,
    )

    assert isinstance(result, FakeChatOpenAI)
    assert captured_kwargs == {
        "model": "gpt-5.4-mini",
        "temperature": 0.0,
        "max_tokens": 500,
        "timeout": 12.5,
        "api_key": "sk-explicit",
    }


def test_build_openrouter_chat_model_uses_settings_fallbacks_when_arguments_are_omitted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    Verify that the OpenRouter-specific builder falls back to backend settings
    when the caller omits both `api_key` and `timeout_seconds`.

    Notes
    -----
    - OpenRouter uses an OpenAI-compatible endpoint in this backend.
    - This test therefore focuses on one question:
        - did the provider helper resolve the right key, timeout, and base URL
          before constructing the client?

    Example
    -------
    We fake backend settings like:

        openrouter_api_key = "sk-or-test"
        openrouter_base_url = "https://openrouter.ai/api/v1"
        llm_timeout_seconds = 22.0

    then call:

        build_openrouter_chat_model(profile=profile)

    and confirm those values are passed into the client constructor.
    """

    profile = _build_openrouter_test_profile()
    captured_kwargs: dict[str, Any] = {}

    class FakeSettings:
        openrouter_api_key = "sk-or-test"
        openrouter_base_url = "https://openrouter.ai/api/v1"
        llm_timeout_seconds = 22.0

    class FakeChatOpenAI:
        def __init__(self, **kwargs: Any) -> None:
            captured_kwargs.update(kwargs)

    monkeypatch.setattr(providers, "get_settings", lambda: FakeSettings())
    monkeypatch.setattr(providers, "ChatOpenAI", FakeChatOpenAI)

    result = build_openrouter_chat_model(profile=profile)

    assert isinstance(result, FakeChatOpenAI)
    assert captured_kwargs == {
        "model": "nvidia/nemotron-3-nano-30b-a3b:nitro",
        "temperature": 0.0,
        "max_tokens": 500,
        "timeout": 22.0,
        "api_key": "sk-or-test",
        "base_url": "https://openrouter.ai/api/v1",
        "extra_body": {
            "reasoning": {
                "effort": "none",
                "exclude": True,
            },
            "chat_template_kwargs": {
                "thinking": False,
            },
        },
    }


def test_build_openrouter_chat_model_prefers_explicit_arguments_over_settings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    Verify that explicit runtime arguments override backend settings for the
    OpenRouter-specific builder.
    """

    profile = _build_openrouter_test_profile()
    captured_kwargs: dict[str, Any] = {}

    class FakeSettings:
        openrouter_api_key = "sk-or-from-settings"
        openrouter_base_url = "https://openrouter.ai/api/v1"
        llm_timeout_seconds = 99.0

    class FakeChatOpenAI:
        def __init__(self, **kwargs: Any) -> None:
            captured_kwargs.update(kwargs)

    monkeypatch.setattr(providers, "get_settings", lambda: FakeSettings())
    monkeypatch.setattr(providers, "ChatOpenAI", FakeChatOpenAI)

    result = build_openrouter_chat_model(
        profile=profile,
        api_key="sk-or-explicit",
        timeout_seconds=12.5,
    )

    assert isinstance(result, FakeChatOpenAI)
    assert captured_kwargs == {
        "model": "nvidia/nemotron-3-nano-30b-a3b:nitro",
        "temperature": 0.0,
        "max_tokens": 500,
        "timeout": 12.5,
        "api_key": "sk-or-explicit",
        "base_url": "https://openrouter.ai/api/v1",
        "extra_body": {
            "reasoning": {
                "effort": "none",
                "exclude": True,
            },
            "chat_template_kwargs": {
                "thinking": False,
            },
        },
    }


def test_build_langchain_chat_model_dispatches_openai_profile_to_openai_builder(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    Verify that the generic provider-dispatch entrypoint routes an OpenAI-backed
    profile into the OpenAI-specific builder.

    Notes
    -----
    - This test is about dispatch logic, not about the `ChatOpenAI` constructor.
    - So we replace the real OpenAI builder with a fake function that records
      what it was called with.
    - That lets the test prove the dispatch layer itself is wired correctly.

    Example
    -------
    We replace `build_openai_chat_model(...)` with a fake function and confirm
    that:

    - the same profile object is forwarded
    - the explicit API key is forwarded
    - the timeout is forwarded

    In plain language:

    - patch the OpenAI-specific builder
    - call the generic provider entrypoint
    - prove the call was routed to the correct builder
    """

    profile = _build_openai_test_profile()
    captured_call: dict[str, Any] = {}

    def fake_build_openai_chat_model(
        *,
        profile: ModelProfile,
        api_key: str | None,
        timeout_seconds: float,
    ) -> str:
        captured_call["profile"] = profile
        captured_call["api_key"] = api_key
        captured_call["timeout_seconds"] = timeout_seconds
        return "fake-openai-client"

    # Replace the real OpenAI builder so this test can focus on provider
    # dispatch rather than on the details of ChatOpenAI construction.
    monkeypatch.setattr(
        providers,
        "build_openai_chat_model",
        fake_build_openai_chat_model,
    )

    result = build_langchain_chat_model(
        profile=profile,
        api_key="sk-test-value",
        timeout_seconds=12.5,
    )

    assert result == "fake-openai-client"
    assert captured_call == {
        "profile": profile,
        "api_key": "sk-test-value",
        "timeout_seconds": 12.5,
    }


def test_build_langchain_chat_model_dispatches_openrouter_profile_to_openrouter_builder(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    Verify that the generic provider-dispatch entrypoint routes an
    OpenRouter-backed profile into the OpenRouter-specific builder.
    """

    profile = _build_openrouter_test_profile()
    captured_call: dict[str, Any] = {}

    def fake_build_openrouter_chat_model(
        *,
        profile: ModelProfile,
        api_key: str | None,
        timeout_seconds: float,
    ) -> str:
        captured_call["profile"] = profile
        captured_call["api_key"] = api_key
        captured_call["timeout_seconds"] = timeout_seconds
        return "fake-openrouter-client"

    monkeypatch.setattr(
        providers,
        "build_openrouter_chat_model",
        fake_build_openrouter_chat_model,
    )

    result = build_langchain_chat_model(
        profile=profile,
        api_key="sk-or-test-value",
        timeout_seconds=18.0,
    )

    assert result == "fake-openrouter-client"
    assert captured_call == {
        "profile": profile,
        "api_key": "sk-or-test-value",
        "timeout_seconds": 18.0,
    }


def test_build_langchain_chat_model_raises_for_unsupported_provider() -> None:
    """
    Verify that the generic provider-dispatch entrypoint fails clearly when the
    requested provider is known locally but not implemented in this module yet.

    Notes
    -----
    - This is an important future-proofing test.
    - The backend already has provider identifiers beyond OpenAI.
    - That does not mean each provider is safe to use yet.
    - The provider layer should therefore fail explicitly rather than pretending
      an unimplemented provider is "almost supported".

    Example
    -------
    A profile such as:

        ModelProfile(
            provider=ModelProvider.NEMOTRON,
            model_name="nemotron/some-model",
            purpose=ModelPurpose.UTILITY,
            temperature=0.0,
            max_output_tokens=500,
        )

    should raise `LLMProviderConfigurationError` with:

    - `stage == "provider_dispatch"`

    In plain language:

    - ask for a provider we know by name but have not implemented
    - confirm the provider factory refuses clearly
    """

    profile = ModelProfile(
        provider=ModelProvider.NEMOTRON,
        model_name="nemotron/some-model",
        purpose=ModelPurpose.UTILITY,
        temperature=0.0,
        max_output_tokens=500,
    )

    with pytest.raises(LLMProviderConfigurationError) as exc_info:
        build_langchain_chat_model(profile=profile)

    error = exc_info.value

    assert str(error) == "The requested LLM provider is not implemented yet."
    assert error.stage == "provider_dispatch"
    assert error.details == [
        {"provider": ModelProvider.NEMOTRON},
        {"model_name": "nemotron/some-model"},
    ]


def test_build_langchain_chat_model_raises_when_model_name_is_blank() -> None:
    """
    Verify that the generic provider entrypoint rejects a profile with a blank
    model name before any provider-specific client is built.

    Notes
    -----
    - This is provider-agnostic validation.
    - The profile should fail early at the shared validation layer rather than
      letting a lower-level client constructor receive obviously broken values.

    Example
    -------
    A profile built with:

        _build_openai_test_profile(model_name="")

    should raise `LLMProviderConfigurationError` with:

    - `stage == "profile_validation"`

    In plain language:

    - pass in a profile with no usable model name
    - confirm the provider layer rejects it immediately
    """

    profile = _build_openai_test_profile(model_name="")

    with pytest.raises(LLMProviderConfigurationError) as exc_info:
        build_langchain_chat_model(profile=profile)

    error = exc_info.value

    assert str(error) == "The model profile is missing a usable model name."
    assert error.stage == "profile_validation"
    assert error.details == [{"provider": ModelProvider.OPENAI}]


def test_build_langchain_chat_model_raises_when_temperature_is_negative() -> None:
    """
    Verify that the generic provider entrypoint rejects a profile whose
    temperature is negative.

    Notes
    -----
    - Negative temperature is not a meaningful local configuration value for
      this backend.
    - The validation layer should therefore classify it as a profile problem,
      not as a provider-transport problem.

    Example
    -------
    A profile built with:

        _build_openai_test_profile(temperature=-0.1)

    should raise `LLMProviderConfigurationError` at the
    `profile_validation` stage.

    In plain language:

    - give the provider layer a nonsensical temperature
    - confirm it fails as invalid local configuration
    """

    profile = _build_openai_test_profile(temperature=-0.1)

    with pytest.raises(LLMProviderConfigurationError) as exc_info:
        build_langchain_chat_model(profile=profile)

    error = exc_info.value

    assert str(error) == "The model profile temperature must be zero or greater."
    assert error.stage == "profile_validation"
    assert error.details == [
        {"provider": ModelProvider.OPENAI},
        {"model_name": "gpt-5.4-mini"},
        {"temperature": -0.1},
    ]


def test_build_langchain_chat_model_raises_when_max_output_tokens_is_not_positive() -> None:
    """
    Verify that the generic provider entrypoint rejects a profile whose output
    token limit is zero.

    Notes
    -----
    - A model profile that allows zero output tokens is not usable for a real
      chat-model call.
    - This should therefore fail at shared profile validation.

    Example
    -------
    A profile built with:

        _build_openai_test_profile(max_output_tokens=0)

    should raise `LLMProviderConfigurationError` at the
    `profile_validation` stage.

    In plain language:

    - give the provider layer a useless token limit
    - confirm it fails before client creation
    """

    profile = _build_openai_test_profile(max_output_tokens=0)

    with pytest.raises(LLMProviderConfigurationError) as exc_info:
        build_langchain_chat_model(profile=profile)

    error = exc_info.value

    assert str(error) == "The model profile must allow at least one output token."
    assert error.stage == "profile_validation"
    assert error.details == [
        {"provider": ModelProvider.OPENAI},
        {"model_name": "gpt-5.4-mini"},
        {"max_output_tokens": 0},
    ]


def test_build_openai_chat_model_raises_when_timeout_is_not_positive() -> None:
    """
    Verify that the OpenAI-specific builder rejects a timeout of zero seconds.

    Notes
    -----
    - Timeout validation lives at the provider-configuration stage rather than
      the profile-validation stage because timeout is not part of the
      `ModelProfile` itself.
    - This test proves that distinction is preserved.

    Example
    -------
    Calling:

        build_openai_chat_model(
            profile=profile,
            timeout_seconds=0.0,
        )

    should raise `LLMProviderConfigurationError` with:

    - `stage == "provider_configuration"`

    In plain language:

    - pass a bad timeout into the OpenAI builder
    - confirm the OpenAI builder classifies it as provider configuration
    """

    profile = _build_openai_test_profile()

    with pytest.raises(LLMProviderConfigurationError) as exc_info:
        build_openai_chat_model(
            profile=profile,
            timeout_seconds=0.0,
        )

    error = exc_info.value

    assert str(error) == "The provider timeout must be greater than zero seconds."
    assert error.stage == "provider_configuration"
    assert error.details == [
        {"provider": ModelProvider.OPENAI},
        {"model_name": "gpt-5.4-mini"},
        {"timeout_seconds": 0.0},
    ]


def test_build_openai_chat_model_raises_when_explicit_api_key_is_blank() -> None:
    """
    Verify that the OpenAI-specific builder rejects a blank explicit API key.

    Notes
    -----
    - The provider layer is allowed to omit the key entirely and let the SDK
      resolve it from the environment.
    - But if a caller explicitly supplies a key, it should be a usable string.
    - A blank explicit key is therefore a configuration error.

    Example
    -------
    Calling:

        build_openai_chat_model(
            profile=profile,
            api_key="   ",
        )

    should raise `LLMProviderConfigurationError` at the
    `provider_configuration` stage.

    In plain language:

    - explicitly pass a useless key string
    - confirm the OpenAI builder rejects it
    """

    profile = _build_openai_test_profile()

    with pytest.raises(LLMProviderConfigurationError) as exc_info:
        build_openai_chat_model(
            profile=profile,
            api_key="   ",
        )

    error = exc_info.value

    assert str(error) == "The supplied OpenAI API key must be a non-empty string."
    assert error.stage == "provider_configuration"
    assert error.details == [
        {"provider": ModelProvider.OPENAI},
        {"model_name": "gpt-5.4-mini"},
    ]


def test_build_openai_chat_model_raises_when_profile_provider_is_not_openai() -> None:
    """
    Verify that the OpenAI-specific builder rejects a profile whose provider is
    not OpenAI.

    Notes
    -----
    - This is slightly different from the generic dispatch failure path.
    - The generic path checks:
        - "is this provider implemented?"
    - This builder checks:
        - "did you call the OpenAI-specific helper with a non-OpenAI profile?"

    Example
    -------
    A profile such as:

        ModelProfile(
            provider=ModelProvider.NEMOTRON,
            model_name="nemotron-something",
            purpose=ModelPurpose.UTILITY,
            temperature=0.0,
            max_output_tokens=500,
        )

    should be rejected by `build_openai_chat_model(...)`.

    In plain language:

    - call the OpenAI-specific helper with the wrong provider
    - confirm it refuses clearly
    """

    profile = ModelProfile(
        provider=ModelProvider.NEMOTRON,
        model_name="nemotron-something",
        purpose=ModelPurpose.UTILITY,
        temperature=0.0,
        max_output_tokens=500,
    )

    with pytest.raises(LLMProviderConfigurationError) as exc_info:
        build_openai_chat_model(profile=profile)

    error = exc_info.value

    assert str(error) == (
        "OpenAI chat-model creation requires an OpenAI-backed model profile."
    )
    assert error.stage == "provider_configuration"
    assert error.details == [
        {"provider": ModelProvider.NEMOTRON},
        {"model_name": "nemotron-something"},
    ]


def test_build_openrouter_chat_model_raises_when_settings_key_is_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    Verify that the OpenRouter-specific builder fails clearly when neither an
    explicit key nor a settings-backed key is available.
    """

    profile = _build_openrouter_test_profile()

    class FakeSettings:
        openrouter_api_key = ""
        openrouter_base_url = "https://openrouter.ai/api/v1"
        llm_timeout_seconds = 30.0

    monkeypatch.setattr(providers, "get_settings", lambda: FakeSettings())

    with pytest.raises(LLMProviderConfigurationError) as exc_info:
        build_openrouter_chat_model(profile=profile)

    error = exc_info.value

    assert str(error) == (
        "The OpenRouter API key must be configured either explicitly or in settings."
    )
    assert error.stage == "provider_configuration"
    assert error.details == [
        {"provider": ModelProvider.OPENROUTER},
        {"model_name": "nvidia/nemotron-3-nano-30b-a3b:nitro"},
    ]


def test_is_non_empty_string_returns_true_only_for_usable_strings() -> None:
    """
    Verify that the small shared string-utility helper accepts only genuinely
    usable strings.

    Notes
    -----
    - This helper looks small, but it is part of the provider validation path.
    - It therefore deserves direct coverage so that string validation does not
      quietly loosen later.

    Example
    -------
    These values should be accepted:

        "gpt-5.4"
        " sk-test-value "

    These should be rejected:

        ""
        "   "
        None
        123

    In plain language:

    - pass in a mix of valid and invalid values
    - confirm only real non-empty strings return `True`
    """

    assert providers._is_non_empty_string("gpt-5.4") is True
    assert providers._is_non_empty_string(" sk-test-value ") is True

    assert providers._is_non_empty_string("") is False
    assert providers._is_non_empty_string("   ") is False
    assert providers._is_non_empty_string(None) is False
    assert providers._is_non_empty_string(123) is False
