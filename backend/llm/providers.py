"""
LLM provider helpers for the intelligence backend.

This module is the bridge between:

- local model descriptions in `backend.llm.models`, and
- real LangChain chat-model clients that can make provider calls

Why this module exists
----------------------
The repository already has typed model descriptions in `backend.llm.models`.

Those model descriptions are useful because they give the rest of the backend a
stable way to talk about:

- provider
- model name
- purpose
- temperature
- token limits

But a `ModelProfile` is only data. It does not actually create a usable model
client.

The next problem is different:

    "Given one local `ModelProfile`, how does the backend build a real
    provider-backed LangChain chat model?"

This is what this module is for.

Why this matters
----------------
As the backend grows, more than one feature will want model access, for example:

- resume extraction
- candidate/job matching
- note summarisation
- outreach drafting
- later graph/workflow nodes

If each of those modules starts building its own provider client directly, the
codebase will drift into avoidable duplication:

- repeated provider checks
- repeated model-profile validation
- repeated timeout configuration
- repeated API-key assumptions
- repeated error handling

This module centralises those concerns so the rest of the backend can ask for:

    "a chat model for this profile"

without needing to know the provider-specific wiring details.

Current scope
-------------
This first version is intentionally modest.

It does:

- validate local `ModelProfile` calues before client creation
- dispatch by provider
- build a `ChatOpenAI` client for OpenAI-backed profiles
- fail clearly for providers that are described locally but not implemented yet

It does not:

- choose models automatically
- implement retries
- implement rate-limit handling
- implement cost tracking
- implement OpenRouter transport yet
- implement Nemotron transport yet
- implement Perplexity transport yet

That boundary is deliberate. The immediate goal is clean, reliable provider
factory, not a full multi-provider routing layer.

Example
-------
A service module can call:

    from backend.llm.models import ModelProfile, ModelProvider, ModelPurpose
    from backend.llm.providers import build_langchain_chat_model

    profile = ModelProfile(
        provider=ModelProvider.OPENAI,
        model_name="gpt-5.4",
        purpose=ModelPurpose.EXTRACTION,
        temperature=0.0,
        max_output_tokens=2200,
    )

    chat_model = build_langchain_chat_model(profile=profile)

and receive a real LangChain chat model that can later be used by code such as:

    structured_model = chat_model.with_structured_output(MySchema)

In plain language:

- start with a local model profile
- validate it
- turn it into a real chat-model client
- hand that client to the service that needs it
"""

from typing import Any

from langchain_openai import ChatOpenAI

from backend.llm.models import ModelProfile, ModelProvider

class LLMProviderConfigurationError(RuntimeError):
    """
    Raised when the backend cannot build a useable LLM provider client.

    Attributes
    ----------
    message : str
        Safe human-readble label describing the failed configuration stage.

        Common values in this module include:

        - `profile_validation`
        - `provider_dispatch`
        - `provider_configuration`

    details : list[dict[str, Any]]
        Small structured metadata that helps explain the failure without
        carrying secrets.

    Notes
    -----
    - This exception is for backend control flow.
    - It deliberately avoids carrying API keys or secret tokens.
    - It is the provider-layer equivalent of the local service exceptions used
      elsewhere in the backend.

    Example
    -------
    A caller may catch this exception and inspect:

        error.stage
        error.details

    to distinguish between:

    - an invalid local `ModelProfile`
    - an unsupported provider
    - a missing/invalid configuration needed to build the provider client

    In plain language:

    - one exception family for provider-factory failures
    - stage labels explain where the failure came from
    - details helps tests and callers reason about the failure
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

        returns just the safe main explanation, while richer structured context
        remains on:

        - `error.stage`
        - `error.details`
        """

        return self.message
    
def build_langchain_chat_model(
    *,
    profile: ModelProfile,
    api_key: str | None = None,
    timeout_seconds: float = 60.0,
) -> Any:
    """
    Build a LangChain-compatible chat model from one local `ModelProfile`.

    Parameters
    ----------
    profile : ModelProfile
        Local model description that identifies the provider, model name, and
        core generation settings.

    api_key : str | None
        Optional explicit API key.

        If provided, this key is passed directly into the provider client.

        If omitted, the provider SDK is expected to resolve credentials from the
        runtime environment using its normal conventions.

    timeout_seconds : float
        Request timeout to apply to the provider client.

    Returns
    -------
    Any
        LangChain-compatible chat model.

        In the current implementation this will be a `ChatOpenAI` instance for
        OpenAI-backed profiles.

    Raises
    ------
    LLMProviderConfigurationError
        If the profile is invalid or if the provider is not supported by this
        module yet.

    Notes
    -----
    - This is the main provider-dispatch entrypoint in the file.
    - The function validates the profile first, then routes to a
      provider-specific builder.
    - Even though the repo knows about several providers in `ModelProvider`,
      this module only implements the OpenAI transport at the moment.

    Example
    -------
    Build a chat model from a profile:

        chat_model = build_langchain_chat_model(
            profile=ModelProfile(
                provider=ModelProvider.OPENAI,
                model_name="gpt-5.4",
                purpose=ModelPurpose.EXTRACTION,
                temperature=0.0,
                max_output_tokens=2200,
            )
        )

    A later service can then do something like:

        chain = prompt | chat_model.with_structured_output(MySchema)

    In plain language:

    - validate the profile
    - route by provider
    - return a real chat-model client
    """

    _validate_model_profile_for_provider_client(profile)

    # Dispatch by provider in one place rather than letting every service
    # recreate provider checks independently.
    #
    # This matters because once multiple services start building model clients,
    # duplicated provider-routing logic becomes a maintenance trap:
    # - different timeout defaults
    # - different validation standards
    # - different error shapes
    #
    # A single dispatch function makes that behaviour consistent.
    if profile.provider == ModelProvider.OPENAI:
        return build_openai_chat_model(
            profile=profile,
            api_key=api_key,
            timeout_seconds=timeout_seconds,
        )

    # Be explicit rather than pretending unsupported providers are "almost"
    # available.
    #
    # The repo already has provider identifiers for future use, but this module
    # should fail clearly until each provider has a real implementation.
    raise LLMProviderConfigurationError(
        "The requested LLM provider is not implemented yet.",
        stage="provider_dispatch",
        details=[
            {"provider": profile.provider},
            {"model_name": profile.model_name},
        ],
    )

def build_openai_chat_model(
    *,
    profile: ModelProfile,
    api_key: str | None = None,
    timeout_seconds: float = 60.0,
) -> ChatOpenAI:
    """
    Build a `ChatOpenAI` client from one OpenAI-backed `ModelProfile`.

    Parameters
    ----------
    profile : ModelProfile
        Local model description.

        The profile must use:

        - `provider = ModelProvider.OPENAI`

    api_key : str | None
        Optional explicit OpenAI API key.

        If omitted, `ChatOpenAI` is expected to resolve credentials from the
        environment in the usual SDK-supported way.

    timeout_seconds : float
        Request timeout to apply to the client.

    Returns
    -------
    ChatOpenAI
        Configured LangChain OpenAI chat model.

    Raises
    ------
    LLMProviderConfigurationError
        If the profile does not describe an OpenAI model or if local settings
        are invalid.

    Notes
    -----
    - This helper is intentionally thin.
    - It does not add retries, tracing, or cost tracking yet.
    - Its job is simply to turn one valid OpenAI `ModelProfile` into a real
      `ChatOpenAI` client.

    Example
    -------
    Build an OpenAI chat model explicitly:

        profile = ModelProfile(
            provider=ModelProvider.OPENAI,
            model_name="gpt-5.4-mini",
            purpose=ModelPurpose.UTILITY,
            temperature=0.0,
            max_output_tokens=500,
        )

        chat_model = build_openai_chat_model(profile=profile)

    Or supply an explicit API key:

        chat_model = build_openai_chat_model(
            profile=profile,
            api_key="sk-...",
            timeout_seconds=45.0,
        )

    In plain language:

    - make sure the profile really is for OpenAI
    - pass the profile settings into `ChatOpenAI`
    - return the configured client
    """

    _validate_model_profile_for_provider_client(profile)

    if profile.provider != ModelProvider.OPENAI:
        raise LLMProviderConfigurationError(
            "OpenAI chat-model creation requires an OpenAI-backed model profile.",
            stage="provider_configuration",
            details=[
                {"provider": profile.provider},
                {"model_name": profile.model_name},
            ],
        )

    if timeout_seconds <= 0:
        raise LLMProviderConfigurationError(
            "The provider timeout must be greater than zero seconds.",
            stage="provider_configuration",
            details=[
                {"provider": profile.provider},
                {"model_name": profile.model_name},
                {"timeout_seconds": timeout_seconds},
            ],
        )

    # Build the client arguments explicitly so the behaviour stays easy to read
    # and easy to extend later.
    #
    # Keeping this as a normal dictionary rather than one huge inline constructor
    # makes a future migration easier if you later add:
    # - retries
    # - custom base URLs
    # - organization IDs
    # - observability hooks
    client_kwargs: dict[str, Any] = {
        "model": profile.model_name,
        "temperature": profile.temperature,
        "max_tokens": profile.max_output_tokens,
        "timeout": timeout_seconds,
    }

    # Passing the API key is optional because the SDK can often resolve it from
    # the environment, but an explicit parameter is still useful for:
    # - tests
    # - special runtime wiring
    # - future service containers with nonstandard secret plumbing
    if api_key is not None:
        if not _is_non_empty_string(api_key):
            raise LLMProviderConfigurationError(
                "The supplied OpenAI API key must be a non-empty string.",
                stage="provider_configuration",
                details=[
                    {"provider": profile.provider},
                    {"model_name": profile.model_name},
                ],
            )
        client_kwargs["api_key"] = api_key

    return ChatOpenAI(**client_kwargs)

def _validate_model_profile_for_provider_client(profile: ModelProfile) -> None:
    """
    Validate that one local `ModelProfile` is usable for provider-client
    construction.

    Parameters
    ----------
    profile : ModelProfile
        Model profile to validate.

    Raises
    ------
    LLMProviderConfigurationError
        If the profile contains obviously invalid local values.

    Notes
    -----
    This helper checks the parts of the profile that should be provider-agnostic
    and obviously valid before any client is created, for example:

    - provider present
    - model name non-empty
    - temperature not negative
    - output-token limit positive

    That keeps validation consistent across all provider builders.

    Example
    -------
    This should pass validation:

        _validate_model_profile_for_provider_client(
            ModelProfile(
                provider=ModelProvider.OPENAI,
                model_name="gpt-5.4",
                purpose=ModelPurpose.EXTRACTION,
                temperature=0.0,
                max_output_tokens=2200,
            )
        )

    This should fail:

        _validate_model_profile_for_provider_client(
            ModelProfile(
                provider=ModelProvider.OPENAI,
                model_name="",
                purpose=ModelPurpose.EXTRACTION,
                temperature=0.0,
                max_output_tokens=2200,
            )
        )

    In plain language:

    - reject obviously broken model profiles early
    - keep provider builders focused on provider-specific concerns
    """

    if not isinstance(profile, ModelProfile):
        raise LLMProviderConfigurationError(
            "A valid ModelProfile instance is required to build a provider client.",
            stage="profile_validation",
            details=[],
        )

    if not _is_non_empty_string(profile.model_name):
        raise LLMProviderConfigurationError(
            "The model profile is missing a usable model name.",
            stage="profile_validation",
            details=[
                {"provider": profile.provider},
            ],
        )

    if profile.temperature < 0:
        raise LLMProviderConfigurationError(
            "The model profile temperature must be zero or greater.",
            stage="profile_validation",
            details=[
                {"provider": profile.provider},
                {"model_name": profile.model_name},
                {"temperature": profile.temperature},
            ],
        )

    if profile.max_output_tokens < 1:
        raise LLMProviderConfigurationError(
            "The model profile must allow at least one output token.",
            stage="profile_validation",
            details=[
                {"provider": profile.provider},
                {"model_name": profile.model_name},
                {"max_output_tokens": profile.max_output_tokens},
            ],
        )


def _is_non_empty_string(value: Any) -> bool:
    """
    Return whether `value` is a non-empty string after trimming whitespace.

    Parameters
    ----------
    value : Any
        Value to inspect.

    Returns
    -------
    bool
        `True` when `value` is a non-empty string after stripping whitespace.

        `False` otherwise.

    Notes
    -----
    This helper exists because provider configuration often depends on strings
    that are technically present but practically unusable, for example:

    - `""`
    - `"   "`
    - `None`
    - non-string objects

    Example
    -------
    These values are usable:

        _is_non_empty_string("gpt-5.4")
        _is_non_empty_string(" sk-test ")

    These are not:

        _is_non_empty_string("")
        _is_non_empty_string("   ")
        _is_non_empty_string(None)

    In plain language:

    - check that the value is really a usable string
    - not just "something truthy-looking"
    """

    return isinstance(value, str) and value.strip() != ""


__all__ = [
    "LLMProviderConfigurationError",
    "build_langchain_chat_model",
    "build_openai_chat_model",
]