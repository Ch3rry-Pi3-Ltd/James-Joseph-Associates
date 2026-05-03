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