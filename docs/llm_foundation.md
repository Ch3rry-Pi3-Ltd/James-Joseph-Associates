# LLM Foundation

This document records the first LLM foundation work in the backend.

It is a status and explanation document, not a provider integration guide.

In plain language:

- the backend can now describe model choices locally
- no real model provider is called yet
- no API keys are required for this layer
- the model profile layer is tested
- provider-specific LangChain clients are intentionally deferred

## What Exists Now

Current files:

```text
backend/llm/models.py
tests/unit/test_llm_models.py
```

These files define and test a local model-description layer.

The current layer can describe:

- model provider
- model name
- model purpose
- temperature
- max output tokens
- whether a profile is deterministic-style

## Current Model Concepts

### Model Provider

`ModelProvider` describes who supplies the model.

Current provider identifiers:

```text
openai
openrouter
nemotron
perplexity
```

In plain language:

- provider = where the model comes from
- model name = which model from that provider

### Model Purpose

`ModelPurpose` describes why the backend would use a model.

Current purpose identifiers:

```text
reasoning
extraction
summarisation
classification
utility
```

In plain language:

- purpose = what job the model is meant to do

Examples:

- reasoning for harder judgement tasks
- extraction for pulling structured fields from text
- summarisation for shortening notes or documents
- classification for assigning labels
- utility for small helper tasks

### Model Profile

`ModelProfile` describes one local model configuration.

It includes:

```python
provider: ModelProvider
model_name: str
purpose: ModelPurpose
temperature: float
max_output_tokens: int
```

It is a frozen dataclass.

That means profiles are not meant to be changed in place.

Instead of mutating a shared profile, future code should create a new profile if
it needs different values.

## Current Defaults

The current default utility profile is:

```python
DEFAULT_UTILITY_MODEL_PROFILE = ModelProfile(
    provider=ModelProvider.OPENAI,
    model_name="gpt-5.4-mini",
    purpose=ModelPurpose.UTILITY,
    temperature=0.0,
    max_output_tokens=500,
)
```

The current default reasoning profile is:

```python
DEFAULT_REASONING_MODEL_PROFILE = ModelProfile(
    provider=ModelProvider.OPENAI,
    model_name="gpt-5.4",
    purpose=ModelPurpose.REASONING,
    temperature=0.2,
    max_output_tokens=1200,
)
```

These are placeholders for the foundation layer.

Before real model calls are built, provider choices, model names, cost
assumptions, and API credentials should be confirmed.

## Deterministic-Style Profiles

The helper:

```python
is_deterministic_profile(profile)
```

currently checks whether:

```python
profile.temperature == 0.0
```

In plain language:

- temperature zero means "try to be predictable"
- this is useful for helper tasks and structured outputs
- it does not guarantee perfect provider-level determinism
- it only checks local configuration

## What This Proves

This foundation proves:

- provider strings are constrained
- model purposes are constrained
- default profiles are available
- profiles are immutable
- deterministic-style configuration can be detected locally
- tests can verify model configuration without network calls

## What This Does Not Do Yet

This layer does not:

- call OpenAI
- call OpenRouter
- call Nemotron
- call Perplexity
- create LangChain chat model clients
- read API keys
- stream model output
- parse structured model responses
- run LLMs inside LangGraph nodes
- perform retrieval, matching, or reasoning

That is intentional.

The purpose is to prepare the model configuration layer before real provider
integration.

## Why Provider Clients Are Deferred

Real provider clients should wait until these decisions are clearer:

- which provider is used first
- which model names are current and approved
- where API keys are stored
- how costs are controlled
- which tasks need strong reasoning
- which tasks can use cheaper utility models
- how outputs will be evaluated
- how retries, rate limits, and failures are handled

Until then, `ModelProfile` is only a local description.

## How This Will Evolve

Possible next LLM modules:

```text
backend/llm/providers.py
backend/llm/structured_output.py
backend/llm/prompts.py
```

Possible future responsibilities:

- build LangChain chat model clients from `ModelProfile`
- choose provider/model based on `ModelPurpose`
- validate structured output schemas
- centralise prompt templates
- support provider fallback
- support test doubles for LLM calls

Those should come after provider, key, and cost decisions are clearer.

## Current Development Status

Done:

- local model provider enum
- local model purpose enum
- local model profile dataclass
- default utility model profile
- default reasoning model profile
- deterministic-style profile helper
- unit tests for model configuration

Not done yet:

- real provider factory
- LangChain model client creation
- API key settings for model providers
- real LLM calls
- structured output parsing
- provider fallback
- LLM evaluation harness

Recommended next project step:

- keep this layer as a foundation
- avoid real provider calls until credentials and provider choices are confirmed
- wait for source-system discovery before building recruitment-specific LLM
  workflows

